import json
import logging
import time
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from agent.decision.schema import DecisionAction, DecisionInput
from agent.models.trigger import TriggerRequest
from agent.reasoning.context_builder import ContextBuilder
from agent.reasoning.reasoner import Reasoner, ReasonerError
from agent.reasoning.schema import ReasonerResult, ReasonerStatus, ToolCall
from agent.reasoning.state import ReasoningState
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
    ) -> str:
        if trigger.game_snapshot is None:
            raise ReasoningGraphError("REASON 请求缺少 game_snapshot")

        logger.info(
            "[ReasoningGraph] start\ntrigger=%s\nquery=%s",
            trigger.trigger_type.value,
            trigger.user_query,
        )
        started_at = time.perf_counter()
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
            "tool_history": [],
            "reasoning_messages": [],
            "pending_tool_calls": [],
            "last_status": None,
            "final_answer": None,
            "tool_call_count": 0,
            "reasoning_round": 0,
        }

        try:
            final_state = await self._graph.ainvoke(
                initial_state,
                config={"recursion_limit": 12},
            )
        except ReasonerError as exception:
            raise ReasoningGraphError(str(exception)) from exception
        except Exception as exception:
            raise ReasoningGraphError(f"Reasoning Graph 执行失败: {exception}") from exception

        answer = final_state.get("final_answer")
        if not answer:
            raise ReasoningGraphError("Reasoning Graph 未生成最终回复")

        logger.info(
            "[ReasoningGraph] end\nrounds=%d\ntool_calls=%d\nlatency=%.2fs",
            final_state["reasoning_round"],
            final_state["tool_call_count"],
            time.perf_counter() - started_at,
        )
        return answer

    async def _reasoner_node(self, state: ReasoningState) -> dict[str, Any]:
        round_number = state["reasoning_round"] + 1
        remaining_tool_calls = MAX_TOOL_CALLS - state["tool_call_count"]
        force_final = (
            round_number >= MAX_REASONING_ROUNDS or remaining_tool_calls <= 0
        )
        result = await self._reasoner.decide(
            state,
            round_number=round_number,
            remaining_tool_calls=max(remaining_tool_calls, 0),
            force_final=force_final,
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
        }

    async def _tool_node(self, state: ReasoningState) -> dict[str, Any]:
        collected_context = dict(state["collected_context"])
        tool_history = list(state["tool_history"])
        tool_call_count = state["tool_call_count"]

        for raw_call in state["pending_tool_calls"]:
            call = ToolCall.model_validate(raw_call)
            signature = tool_signature(call.name.value, call.arguments)
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
                        "arguments": call.arguments,
                        "signature": signature,
                        "status": "reused",
                        "original_status": previous.get("status"),
                        "round": state["reasoning_round"],
                    }
                )
                logger.info("[Tool] name=%s reused=true", call.name.value)
                continue

            if tool_call_count >= MAX_TOOL_CALLS:
                break

            started_at = time.perf_counter()
            tool_call_count += 1
            try:
                context_key, result = self._tool_executor.execute(
                    DecisionAction.REASON,
                    call.name,
                    call.arguments,
                    state["game_snapshot"],
                )
                collected_context[context_key] = result
                tool_history.append(
                    {
                        "name": call.name.value,
                        "arguments": call.arguments,
                        "signature": signature,
                        "status": "success",
                        "round": state["reasoning_round"],
                    }
                )
                logger.info(
                    "[Tool]\nname=%s\nlatency=%.3fs\nresult_summary=%s",
                    call.name.value,
                    time.perf_counter() - started_at,
                    _summary(result),
                )
            except Exception as exception:
                collected_context.setdefault("tool_errors", []).append(
                    {
                        "tool": call.name.value,
                        "error": str(exception),
                        "round": state["reasoning_round"],
                    }
                )
                tool_history.append(
                    {
                        "name": call.name.value,
                        "arguments": call.arguments,
                        "signature": signature,
                        "status": "error",
                        "error": str(exception),
                        "round": state["reasoning_round"],
                    }
                )
                logger.warning(
                    "[Tool] name=%s error=%s round=%d",
                    call.name.value,
                    exception,
                    state["reasoning_round"],
                )

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
