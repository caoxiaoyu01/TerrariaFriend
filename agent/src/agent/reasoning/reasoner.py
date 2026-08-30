import logging
from typing import Any

from pydantic import ValidationError

from agent.decision.schema import DecisionAction
from agent.llm.client import (
    RoleLLMClient,
    log_model_completion,
    parse_json_object,
)
from agent.reasoning.prompt import REASONING_SYSTEM_PROMPT
from agent.reasoning.schema import ReasonerResult
from agent.reasoning.state import ReasoningState
from agent.reasoning.tools import ToolExecutor


logger = logging.getLogger("uvicorn.error")


class ReasonerError(RuntimeError):
    pass


class Reasoner:
    def __init__(
        self,
        model_client: RoleLLMClient,
        *,
        available_tools: dict[str, object] | None = None,
    ) -> None:
        self._model_client = model_client
        self._available_tools = available_tools or ToolExecutor().available_tool_specs(
            DecisionAction.REASON
        )

    async def decide(
        self,
        state: ReasoningState,
        *,
        round_number: int,
        remaining_tool_calls: int,
        force_final: bool,
    ) -> ReasonerResult:
        # 稳定的工具定义放在动态状态前 提高前缀缓存命中率
        input_data: dict[str, Any] = {
            "available_tools": self._available_tools,
            "task": state["initial_context"],
            "collected_context": state["collected_context"],
            "tool_history": state["tool_history"],
            "limits": {
                "reasoning_round": round_number,
                "remaining_tool_calls": remaining_tool_calls,
                "must_return_final": force_final,
            },
        }

        last_error: Exception | None = None
        for attempt in range(2):
            if attempt == 1:
                input_data["repair_instruction"] = (
                    "上一次输出不是有效的约定 JSON，请严格按 output_schema 重新输出一次"
                )
            try:
                completion = await self._model_client.generate_structured(
                    system_prompt=REASONING_SYSTEM_PROMPT,
                    input_data=input_data,
                    output_schema=ReasonerResult.model_json_schema(),
                )
                log_model_completion(
                    logger,
                    "Reasoner",
                    self._model_client,
                    completion,
                )
                raw_result = parse_json_object(completion.content)
                logger.debug("[Reasoner] model_response=%s", raw_result)
                return ReasonerResult.model_validate(raw_result)
            except (ValueError, ValidationError) as exception:
                last_error = exception
                logger.warning(
                    "[Reasoner] invalid structured output attempt=%d error=%s",
                    attempt + 1,
                    exception,
                )
            except Exception as exception:
                detail = str(exception).strip() or repr(exception)
                raise ReasonerError(
                    f"Reasoning 模型调用失败: {type(exception).__name__}: {detail}"
                ) from exception

        raise ReasonerError("Reasoning 模型连续两次返回无效结构") from last_error
