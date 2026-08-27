import json
import logging
import time
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from agent.decision.schema import DecisionAction, DecisionInput
from agent.models.trigger import TriggerRequest
from agent.models.execution import (
    AgentExecutionResult,
    ToolHistoryMetadata,
    select_game_context,
)
from agent.reasoning.context_builder import ContextBuilder
from agent.reasoning.reasoner import Reasoner, ReasonerError
from agent.reasoning.schema import (
    TOOL_CALL_ADAPTER,
    ReasonerResult,
    ReasonerStatus,
)
from agent.reasoning.state import ReasoningRunMetrics, ReasoningState
from agent.reasoning.tools import GameContextTools, ToolExecutor, tool_signature


logger = logging.getLogger("uvicorn.error")

MAX_REASONING_ROUNDS = 4
MAX_TOOL_CALLS = 4


class ReasoningGraphError(RuntimeError):
    pass


class ReasoningGraph:
    def __init__(
        self,
        reasoner: Reasoner,
        *,
        context_builder: ContextBuilder | None = None,
        tools: GameContextTools | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self._reasoner = reasoner
        self._context_builder = context_builder or ContextBuilder()
        if tools is not None and tool_executor is not None:
            raise ValueError("tools 与 tool_executor 不能同时提供")
        self._tool_executor = tool_executor or ToolExecutor(tools)

        builder = StateGraph(ReasoningState)
        builder.add_node("reasoner", self._reasoner_node)
        builder.add_node("tools", self._tool_node)
        builder.add_edge(START, "reasoner")
        builder.add_conditional_edges(
            "reasoner",
            self._route_after_reasoner,
            {"tools": "tools", "end": END},
        )
        builder.add_edge("tools", "reasoner")
        self._graph = builder.compile()

    async def run(
        self,
        trigger: TriggerRequest,
        decision_input: DecisionInput,
        decision_reason: str,
    ) -> AgentExecutionResult:
        if trigger.game_snapshot is None:
            raise ReasoningGraphError("REASON 请求缺少 game_snapshot")

        logger.info(
            "[ReasoningGraph] start\ntrigger=%s\nquery=%s",
            trigger.trigger_type.value,
            trigger.user_query,
        )
        started_at = time.perf_counter()
        run_metrics = ReasoningRunMetrics()
        initial_state: ReasoningState = {
            "trigger": trigger.model_dump(
                mode="json",
                exclude={"game_snapshot"},
                exclude_none=True,
            ),
            "query": trigger.user_query,
            "initial_context": self._context_builder.build(
                trigger,
                decision_input,
                decision_reason,
            ),
            "game_snapshot": trigger.game_snapshot,
            "collected_context": {},
            "tool_history": run_metrics.tool_history,
            "reasoning_messages": [],
            "pending_tool_calls": [],
            "last_status": None,
            "final_answer": None,
            "tool_call_count": 0,
            "reasoning_round": 0,
            "reasoner_total_latency_seconds": 0.0,
            "run_metrics": run_metrics,
        }

        try:
            final_state = await self._graph.ainvoke(
                initial_state,
                config={"recursion_limit": 12},
            )
        except ReasonerError as exception:
            _log_ab_metrics(
                wiki_mcp_enabled=self._tool_executor.wiki_mcp_enabled,
                tool_history=run_metrics.tool_history,
                reasoning_rounds=run_metrics.reasoning_rounds,
                reasoner_latency_seconds=(
                    run_metrics.reasoner_total_latency_seconds
                ),
                total_latency_seconds=time.perf_counter() - started_at,
            )
            raise ReasoningGraphError(str(exception)) from exception
        except Exception as exception:
            _log_ab_metrics(
                wiki_mcp_enabled=self._tool_executor.wiki_mcp_enabled,
                tool_history=run_metrics.tool_history,
                reasoning_rounds=run_metrics.reasoning_rounds,
                reasoner_latency_seconds=(
                    run_metrics.reasoner_total_latency_seconds
                ),
                total_latency_seconds=time.perf_counter() - started_at,
            )
            raise ReasoningGraphError(f"Reasoning Graph 执行失败: {exception}") from exception

        answer = final_state.get("final_answer")
        if not answer:
            raise ReasoningGraphError("Reasoning Graph 未生成最终回复")

        total_latency_seconds = time.perf_counter() - started_at
        logger.info(
            "[ReasoningGraph] end\nrounds=%d\ntool_calls=%d\nlatency=%.2fs",
            final_state["reasoning_round"],
            final_state["tool_call_count"],
            total_latency_seconds,
        )
        _log_ab_metrics(
            wiki_mcp_enabled=self._tool_executor.wiki_mcp_enabled,
            tool_history=run_metrics.tool_history,
            reasoning_rounds=run_metrics.reasoning_rounds,
            reasoner_latency_seconds=run_metrics.reasoner_total_latency_seconds,
            total_latency_seconds=total_latency_seconds,
        )
        return AgentExecutionResult(
            message=answer,
            decision_action=DecisionAction.REASON,
            reasoning_rounds=final_state["reasoning_round"],
            used_game_context=select_game_context(
                final_state["collected_context"]
            ),
            tool_history=[
                ToolHistoryMetadata.model_validate(entry)
                for entry in final_state["tool_history"]
            ],
        )

    async def _reasoner_node(self, state: ReasoningState) -> dict[str, Any]:
        round_number = state["reasoning_round"] + 1
        remaining_tool_calls = MAX_TOOL_CALLS - state["tool_call_count"]
        force_final = (
            round_number >= MAX_REASONING_ROUNDS or remaining_tool_calls <= 0
        )
        run_metrics = state["run_metrics"]
        run_metrics.reasoning_rounds = round_number
        started_at = time.perf_counter()
        try:
            result = await self._reasoner.decide(
                state,
                round_number=round_number,
                remaining_tool_calls=max(remaining_tool_calls, 0),
                force_final=force_final,
            )
        finally:
            run_metrics.reasoner_total_latency_seconds += (
                time.perf_counter() - started_at
            )

        # 达到 Guardrail 后不再允许模型继续请求工具
        if force_final and result.status is ReasonerStatus.NEED_TOOL:
            result = ReasonerResult(
                status=ReasonerStatus.FINAL,
                answer="根据当前能够获取的信息还无法完全确定，建议先确保安全并结合现有进度和装备谨慎行动。",
            )

        tools = [call.name.value for call in result.tool_calls]
        logger.info(
            "[Reasoner]\nround=%d\nstatus=%s\ntools=%s%s",
            round_number,
            result.status.value,
            tools,
            f"\nanswer={result.answer}" if result.answer else "",
        )
        reasoning_messages = [
            *state["reasoning_messages"],
            {
                "round": round_number,
                "status": result.status.value,
                "tools": tools,
            },
        ]
        return {
            "reasoning_round": round_number,
            "last_status": result.status.value,
            "pending_tool_calls": [
                call.model_dump(mode="json") for call in result.tool_calls
            ],
            "final_answer": result.answer,
            "reasoning_messages": reasoning_messages,
            "reasoner_total_latency_seconds": (
                run_metrics.reasoner_total_latency_seconds
            ),
        }

    async def _tool_node(self, state: ReasoningState) -> dict[str, Any]:
        collected_context = dict(state["collected_context"])
        tool_history = list(state["tool_history"])
        tool_call_count = state["tool_call_count"]
        run_metrics = state["run_metrics"]

        for raw_call in state["pending_tool_calls"]:
            call = TOOL_CALL_ADAPTER.validate_python(raw_call)
            arguments = call.arguments_dict()
            signature = tool_signature(call.name.value, arguments)
            previous = next(
                (
                    entry
                    for entry in tool_history
                    if entry.get("signature") == signature
                ),
                None,
            )
            if previous is not None:
                tool_history.append(
                    {
                        "name": call.name.value,
                        "arguments": arguments,
                        "signature": signature,
                        "status": "reused",
                        "original_status": previous.get("status"),
                        "round": state["reasoning_round"],
                    }
                )
                logger.info("[Tool] name=%s reused=true", call.name.value)
                run_metrics.tool_history = tool_history
                continue

            if tool_call_count >= MAX_TOOL_CALLS:
                break

            started_at = time.perf_counter()
            tool_call_count += 1
            try:
                context_key, result = await self._tool_executor.execute_async(
                    DecisionAction.REASON,
                    call.name,
                    arguments,
                    state["game_snapshot"],
                )
                collected_context[context_key] = result
                latency_seconds = time.perf_counter() - started_at
                tool_history.append(
                    {
                        "name": call.name.value,
                        "arguments": arguments,
                        "signature": signature,
                        "status": "success",
                        "success": True,
                        "round": state["reasoning_round"],
                        "latency_ms": latency_seconds * 1000,
                        "cache_hit": _cache_hit(result),
                    }
                )
                logger.info(
                    "[Tool]\nname=%s\nlatency=%.3fs\nresult_summary=%s",
                    call.name.value,
                    latency_seconds,
                    _tool_result_summary(call.name.value, result),
                )
                run_metrics.tool_history = tool_history
            except Exception as exception:
                latency_seconds = time.perf_counter() - started_at
                collected_context.setdefault("tool_errors", []).append(
                    {
                        "tool": call.name.value,
                        "error": str(exception),
                        "round": state["reasoning_round"],
                        "latency_ms": latency_seconds * 1000,
                        "cache_hit": None,
                    }
                )
                tool_history.append(
                    {
                        "name": call.name.value,
                        "arguments": arguments,
                        "signature": signature,
                        "status": "error",
                        "success": False,
                        "error": str(exception),
                        "round": state["reasoning_round"],
                        "latency_ms": latency_seconds * 1000,
                        "cache_hit": None,
                    }
                )
                logger.warning(
                    "[Tool] name=%s success=false latency=%.3fs error=%s round=%d",
                    call.name.value,
                    latency_seconds,
                    exception,
                    state["reasoning_round"],
                )
                run_metrics.tool_history = tool_history

        return {
            "collected_context": collected_context,
            "tool_history": tool_history,
            "tool_call_count": tool_call_count,
            "pending_tool_calls": [],
        }

    @staticmethod
    def _route_after_reasoner(state: ReasoningState) -> Literal["tools", "end"]:
        return "tools" if state["last_status"] == ReasonerStatus.NEED_TOOL.value else "end"


def _summary(result: dict[str, Any], max_length: int = 400) -> str:
    text = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= max_length else f"{text[:max_length]}..."


def _tool_result_summary(name: str, result: dict[str, Any]) -> str:
    if name != "lookup_terraria_knowledge":
        return _summary(result)
    return _summary(
        {
            "title": result.get("title"),
            "resolved_lang": result.get("resolved_lang"),
            "evidence_count": len(result.get("evidence", [])),
        }
    )


def _cache_hit(result: dict[str, Any]) -> bool | None:
    value = result.get("cache_hit")
    if isinstance(value, bool):
        return value
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("cache_hit"), bool):
        return metadata["cache_hit"]
    return None


def _wiki_metrics(
    tool_history: list[dict[str, Any]],
) -> tuple[bool, float, bool | None]:
    entries = [
        entry
        for entry in tool_history
        if entry.get("name") == "lookup_terraria_knowledge"
        and entry.get("status") != "reused"
    ]
    if not entries:
        return False, 0.0, None
    latency_ms = sum(float(entry.get("latency_ms", 0.0)) for entry in entries)
    cache_values = [
        entry.get("cache_hit")
        for entry in entries
        if isinstance(entry.get("cache_hit"), bool)
    ]
    return True, latency_ms, cache_values[-1] if cache_values else None


def _log_ab_metrics(
    *,
    wiki_mcp_enabled: bool,
    tool_history: list[dict[str, Any]],
    reasoning_rounds: int,
    reasoner_latency_seconds: float,
    total_latency_seconds: float,
) -> None:
    wiki_called, wiki_latency_ms, wiki_cache_hit = _wiki_metrics(tool_history)
    if not wiki_mcp_enabled:
        wiki_called = False
        wiki_latency_ms = 0.0
        wiki_cache_hit = None
    logger.info(
        "[ReasoningAB] wiki_mcp_enabled=%s wiki_tool_called=%s "
        "wiki_tool_latency_ms=%.1f wiki_cache_hit=%s reasoner_rounds=%d "
        "reasoner_total_latency_ms=%.1f total_latency_ms=%.1f tool_history=%s",
        str(wiki_mcp_enabled).lower(),
        str(wiki_called).lower(),
        wiki_latency_ms,
        wiki_cache_hit,
        reasoning_rounds,
        reasoner_latency_seconds * 1000,
        total_latency_seconds * 1000,
        _tool_history_summary(tool_history),
    )


def _tool_history_summary(tool_history: list[dict[str, Any]]) -> str:
    return _summary(
        {
            "calls": [
                {
                    "name": entry.get("name"),
                    "status": entry.get("status"),
                    "latency_ms": entry.get("latency_ms"),
                }
                for entry in tool_history
            ]
        }
    )
