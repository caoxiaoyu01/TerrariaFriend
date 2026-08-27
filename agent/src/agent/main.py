import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI
from fastapi import Depends
from pydantic import ValidationError

from agent.decision.node import DecisionNode, DecisionNodeError
from agent.decision.schema import DecisionAction, DecisionInput, DecisionResult
from agent.llm.client import OpenAICompatibleClient, RoleLLMClient
from agent.llm.config import AgentLLMSettings
from agent.mcp_clients import create_terraria_wiki_mcp_client
from agent.memory.formation import MemoryExtractor
from agent.memory.formation.runtime import MemoryFormationRuntime
from agent.memory.formation.store import FormationCheckpointStore
from agent.memory.graphiti import GraphitiMemoryWriter
from agent.memory.graphiti.backend import GraphitiMemoryBackend
from agent.memory.graphiti.config import GraphitiSettings
from agent.models.execution import AgentExecutionResult
from agent.models.trigger import (
    AgentResponse,
    TriggerRequest,
    TriggerType,
    WorldSessionEndedRequest,
)
from agent.periodic_gate import PeriodicGate
from agent.reasoning.graph import ReasoningGraph, ReasoningGraphError
from agent.reasoning.reasoner import Reasoner
from agent.reasoning.tool_policy import ToolPolicy
from agent.reasoning.tools import GameContextTools, ToolExecutor
from agent.response.generator import ResponseGenerator, ResponseGeneratorError
from agent.trace.config import formation_state_path, trace_state_path
from agent.trace.relevance import is_related_to_close_context
from agent.trace.runtime import TraceRuntime
from agent.trace.store import LocalTraceStore


logger = logging.getLogger("uvicorn.error")
HP_DROP_REASON_THRESHOLD = -0.10

# 三个角色共用同一个底层 HTTP Client 和 API 凭证
llm_settings = AgentLLMSettings.from_environment()
llm_client = OpenAICompatibleClient(llm_settings.provider)
decision_node = DecisionNode(RoleLLMClient(llm_client, llm_settings.decision))
wiki_mcp_client = create_terraria_wiki_mcp_client(
    llm_settings.wiki_mcp_enabled
)
tool_executor = ToolExecutor(
    GameContextTools(),
    ToolPolicy(wiki_mcp_enabled=llm_settings.wiki_mcp_enabled),
    wiki_client=wiki_mcp_client,
)
response_role_client = RoleLLMClient(llm_client, llm_settings.response)
reasoning_role_client = RoleLLMClient(llm_client, llm_settings.reasoning)
response_generator = ResponseGenerator(
    response_role_client,
    tool_executor=tool_executor,
)
reasoning_graph = ReasoningGraph(
    Reasoner(
        reasoning_role_client,
        available_tools=tool_executor.available_tool_specs(
            DecisionAction.REASON
        ),
    ),
    tool_executor=tool_executor,
)
periodic_gate = PeriodicGate()

graphiti_settings = GraphitiSettings.from_environment()
graphiti_backend = GraphitiMemoryBackend()
memory_formation_runtime = MemoryFormationRuntime(
    MemoryExtractor(reasoning_role_client),
    GraphitiMemoryWriter(graphiti_backend),
    FormationCheckpointStore(formation_state_path()),
    group_id=graphiti_settings.falkordb_database,
    initialize_backend=graphiti_backend.initialize,
)


async def _check_trace_relatedness(close_context, user_query):
    return await is_related_to_close_context(
        close_context,
        user_query,
        model_client=response_role_client,
    )


trace_runtime = TraceRuntime(
    LocalTraceStore(trace_state_path()),
    relatedness_checker=_check_trace_relatedness,
    formation_runtime=memory_formation_runtime,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    trace_runtime.resume_closed_traces()
    if wiki_mcp_client is not None:
        try:
            await wiki_mcp_client.start()
            logger.info("[WikiMCP] enabled=true status=connected")
        except Exception as exception:
            # 维基故障不阻止智能体启动 推理器会收到紧凑工具错误
            logger.warning(
                "[WikiMCP] enabled=true status=unavailable error=%s",
                exception,
            )
    try:
        yield
    finally:
        try:
            await trace_runtime.shutdown()
        finally:
            try:
                if memory_formation_runtime.backend_initialized:
                    await graphiti_backend.close()
            finally:
                try:
                    if wiki_mcp_client is not None:
                        await wiki_mcp_client.aclose()
                finally:
                    await llm_client.aclose()


app = FastAPI(title="TerrariaFriend Agent", lifespan=lifespan)


def get_decision_node() -> DecisionNode:
    return decision_node


def get_response_generator() -> ResponseGenerator:
    return response_generator


def get_reasoning_graph() -> ReasoningGraph:
    return reasoning_graph


def get_periodic_gate() -> PeriodicGate:
    return periodic_gate


def get_trace_runtime() -> TraceRuntime:
    return trace_runtime


async def _record_l1(
    runtime: TraceRuntime,
    trigger: TriggerRequest,
    execution: AgentExecutionResult | None = None,
) -> None:
    try:
        await runtime.record_trigger(
            trigger,
            execution=execution,
            response_occurred_at=(datetime.now(timezone.utc) if execution else None),
        )
    except Exception:
        # 一级记忆持久化不得改变公开响应契约
        logger.exception("[L1Trace] failed to record trigger")


def _as_json(value: object, max_length: int = 600) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= max_length else f"{text[:max_length]}..."


def _log_decision_input(decision_input: DecisionInput) -> None:
    trigger_type = decision_input.trigger_type
    vitals = _as_json(decision_input.vitals.model_dump())
    if trigger_type is TriggerType.USER_QUERY:
        logger.info(
            "[DecisionNode] trigger=%s\nquery: %s\nvitals: %s",
            trigger_type.value,
            decision_input.user_query,
            vitals,
        )
    elif trigger_type is TriggerType.GAME_EVENT:
        game_event = decision_input.game_event
        logger.info(
            "[DecisionNode] trigger=%s\nevent_type: %s\npayload: %s\ncontext: %s\nvitals: %s",
            trigger_type.value,
            game_event.event_type.value,
            _as_json(game_event.payload),
            _as_json(decision_input.event_context.model_dump(exclude_none=True)),
            vitals,
        )
    else:
        logger.info(
            "[DecisionNode] trigger=%s\nsummary: %s\nvitals: %s",
            trigger_type.value,
            _as_json(decision_input.periodic_summary.model_dump(exclude_none=True)),
            vitals,
        )

    logger.debug(
        "[DecisionNode] input=%s",
        _as_json(decision_input.model_dump(mode="json", exclude_none=True), 2000),
    )


def _apply_health_rule(
    decision_input: DecisionInput,
) -> DecisionResult | None:
    hp_delta = decision_input.vitals.hp_delta
    if hp_delta > HP_DROP_REASON_THRESHOLD:
        return None

    logger.info(
        "[DecisionNode] hard_rule=HP_DROP hp_delta=%.3f",
        hp_delta,
    )
    return DecisionResult(
        action=DecisionAction.REASON,
        reason="玩家近期明显掉血，需要获取更多战斗和生存状态分析原因",
    )


@app.post("/agent/trigger", response_model=AgentResponse)
async def handle_trigger(
    trigger: TriggerRequest,
    node: Annotated[DecisionNode, Depends(get_decision_node)],
    generator: Annotated[ResponseGenerator, Depends(get_response_generator)],
    graph: Annotated[ReasoningGraph, Depends(get_reasoning_graph)],
    gate: Annotated[PeriodicGate, Depends(get_periodic_gate)],
    runtime: Annotated[TraceRuntime, Depends(get_trace_runtime)],
) -> AgentResponse:
    """接收 Trigger 并执行 Decision 选择的处理路径"""
    if trigger.trigger_type is TriggerType.PERIODIC:
        allowed, reason = gate.should_allow(
            hp_drop=trigger.vitals.hp_delta <= HP_DROP_REASON_THRESHOLD
        )
        if not allowed:
            return AgentResponse(
                action=DecisionAction.IGNORE.value,
                message=None,
                decision_reason=f"Periodic cheap gate: {reason}",
                success=True,
                error=None,
            )

    try:
        # 路由只负责输入转换和调用编排
        decision_input = DecisionInput.from_trigger(trigger)
        _log_decision_input(decision_input)
        started_at = time.perf_counter()
        result = _apply_health_rule(decision_input)
        if result is None:
            result = await node.decide(decision_input)
            decision_source = node.model_name
        else:
            decision_source = "code:HP_DROP"
    except (DecisionNodeError, ValidationError) as exception:
        # 模型或 Schema 失败时返回业务错误 避免 FastAPI 进程崩溃
        logger.error("Decision Node failed: %s", exception)
        await _record_l1(runtime, trigger)
        return AgentResponse(
            action="ERROR",
            message=None,
            decision_reason=None,
            success=False,
            error=str(exception),
        )

    latency = time.perf_counter() - started_at
    logger.info(
        "[DecisionRoute] result\naction=%s\nreason=%s\nmodel=%s\nlatency=%.2fs",
        result.action.value,
        result.reason,
        decision_source,
        latency,
    )

    try:
        if result.action is DecisionAction.IGNORE:
            execution = None
            message = None
        elif result.action is DecisionAction.RESPOND:
            execution = await generator.generate(
                decision_input,
                result.reason,
                trigger.game_snapshot,
            )
            message = execution.message
        else:
            execution = await graph.run(trigger, decision_input, result.reason)
            message = execution.message
    except (ResponseGeneratorError, ReasoningGraphError) as exception:
        logger.error("Agent response path failed: %s", exception)
        await _record_l1(runtime, trigger)
        return AgentResponse(
            action="ERROR",
            message=None,
            decision_reason=result.reason,
            success=False,
            error=str(exception),
        )

    if message and message.strip():
        gate.record_agent_message()

    await _record_l1(runtime, trigger, execution)

    return AgentResponse(
        action=result.action.value,
        message=message,
        decision_reason=result.reason,
        success=True,
        error=None,
    )


@app.post("/agent/world-session-ended", status_code=204)
async def handle_world_session_ended(
    request: WorldSessionEndedRequest,
    runtime: Annotated[TraceRuntime, Depends(get_trace_runtime)],
) -> None:
    """同步处理卸载信号并与基于队列的触发路由分离"""

    await runtime.handle_world_session_ended(request.occurred_at)
