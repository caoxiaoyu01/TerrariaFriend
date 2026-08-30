import json
import logging
import os
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
from agent.memory.formation import MemoryExtractor
from agent.memory.formation.runtime import MemoryFormationRuntime
from agent.memory.formation.store import FormationCheckpointStore, FormationOutboxStore
from agent.memory.retrieval import (
    LongTermMemoryRetriever,
    MemoryContextTool,
    RecentMemoryRetriever,
    world_memory_group_id,
)
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
from agent.reasoning.tools import ToolExecutor
from agent.response.generator import ResponseGenerator, ResponseGeneratorError
from agent.trace.config import formation_outbox_path, formation_state_path, trace_state_path
from agent.trace.relevance import is_related_to_close_context
from agent.trace.runtime import TraceRuntime
from agent.trace.store import LocalTraceStore
from agent.world_context import current_world_id, require_current_world_id


logger = logging.getLogger("uvicorn.error")
HP_DROP_REASON_THRESHOLD = -0.10

# 三个模型角色共用同一套网络连接和密钥
llm_settings = AgentLLMSettings.from_environment()
llm_client = OpenAICompatibleClient(llm_settings.provider)
decision_node = DecisionNode(RoleLLMClient(llm_client, llm_settings.decision))
response_role_client = RoleLLMClient(llm_client, llm_settings.response)
reasoning_role_client = RoleLLMClient(llm_client, llm_settings.reasoning)
wiki_mcp_client = None
if llm_settings.wiki_mcp_enabled:
    try:
        from agent.mcp_clients import create_terraria_wiki_mcp_client

        wiki_mcp_client = create_terraria_wiki_mcp_client(True)
    except Exception as exception:
        logger.warning("[WikiMCP] status=disabled error=%s", exception)

long_term_memory_enabled = (
    os.getenv("LONG_TERM_MEMORY_ENABLED", "false").lower() == "true"
)
graphiti_backend = None
memory_formation_runtime = None
long_term_retriever = None
if long_term_memory_enabled:
    try:
        from agent.memory.graphiti import GraphitiMemoryWriter
        from agent.memory.graphiti.backend import GraphitiMemoryBackend

        graphiti_backend = GraphitiMemoryBackend()
        long_term_retriever = LongTermMemoryRetriever(
            graphiti_backend,
            group_id_provider=lambda: world_memory_group_id(
                require_current_world_id()
            ),
        )
        memory_formation_runtime = MemoryFormationRuntime(
            MemoryExtractor(reasoning_role_client),
            GraphitiMemoryWriter(graphiti_backend),
            FormationCheckpointStore(formation_state_path()),
            FormationOutboxStore(formation_outbox_path()),
            group_id_factory=world_memory_group_id,
            initialize_backend=graphiti_backend.initialize,
        )
    except Exception as exception:
        long_term_memory_enabled = False
        graphiti_backend = None
        memory_formation_runtime = None
        long_term_retriever = None
        logger.warning("[LongTermMemory] status=disabled error=%s", exception)
trace_store = LocalTraceStore(trace_state_path())
memory_context_tool = MemoryContextTool(
    RecentMemoryRetriever(
        trace_store,
        response_role_client,
        world_id_provider=require_current_world_id,
    ),
    long_term_retriever,
)
tool_executor = ToolExecutor(
    wiki_client=wiki_mcp_client,
    memory_tool=memory_context_tool,
)
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


async def _check_trace_relatedness(close_context, user_query):
    return await is_related_to_close_context(
        close_context,
        user_query,
        model_client=response_role_client,
    )


trace_runtime = TraceRuntime(
    trace_store,
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
            # 维基暂时不可用时仍允许智能体启动
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
                if (
                    memory_formation_runtime is not None
                    and graphiti_backend is not None
                    and memory_formation_runtime.backend_initialized
                ):
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
        # 记录记忆失败时仍正常返回回复
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
    """接收游戏触发并按决策结果执行对应流程"""
    current_world_id.set(trigger.world_id)
    if not await runtime.activate_context(trigger.world_id, trigger.session_id):
        return AgentResponse(
            action=DecisionAction.IGNORE.value,
            message=None,
            decision_reason="Session 已结束",
            success=True,
            error=None,
        )
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
        # 这里仅整理输入并调用对应处理流程
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
        # 模型输出无效时返回错误信息 保持服务继续运行
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
    """离开世界时立即保存当前记忆 不经过普通事件队列"""

    await runtime.handle_world_session_ended(
        request.occurred_at,
        world_id=request.world_id,
        session_id=request.session_id,
    )
