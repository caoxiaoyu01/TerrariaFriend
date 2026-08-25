import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from agent.decision.schema import DecisionAction, DecisionInput
from agent.llm.client import (
    RoleLLMClient,
    log_model_completion,
    parse_json_object,
)
from agent.models.game_snapshot import GameSnapshot
from agent.reasoning.schema import ToolCall
from agent.reasoning.tools import (
    TOOL_DESCRIPTIONS,
    ToolExecutor,
    ToolPermissionError,
)
from agent.response.prompt import RESPONSE_SYSTEM_PROMPT


logger = logging.getLogger("uvicorn.error")


class ResponseGeneratorError(RuntimeError):
    pass


class ResponseStatus(str, Enum):
    NEED_TOOL = "NEED_TOOL"
    FINAL = "FINAL"


class ResponseResult(BaseModel):
    status: ResponseStatus
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=1)
    answer: str | None = None

    @field_validator("answer")
    @classmethod
    def normalize_answer(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_status_fields(self) -> "ResponseResult":
        if self.status is ResponseStatus.NEED_TOOL:
            if len(self.tool_calls) != 1:
                raise ValueError("NEED_TOOL 必须提供一个 tool_calls 元素")
            if self.answer:
                raise ValueError("NEED_TOOL 不能同时提供 answer")
        else:
            if not self.answer:
                raise ValueError("FINAL 必须提供 answer")
            if self.tool_calls:
                raise ValueError("FINAL 不能提供 tool_calls")
        return self


RESPONSE_FALLBACK = "现有信息不足，暂时无法可靠回答这个问题。"


class ResponseGenerator:
    def __init__(
        self,
        model_client: RoleLLMClient,
        *,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self._model_client = model_client
        self._tool_executor = tool_executor or ToolExecutor()

    async def generate(
        self,
        decision_input: DecisionInput,
        decision_reason: str,
        game_snapshot: GameSnapshot | None = None,
    ) -> str:
        logger.info(
            "[ResponseGenerator] trigger=%s model=%s thinking=%s",
            decision_input.trigger_type.value,
            self._model_client.model_name,
            str(self._model_client.config.enable_thinking).lower(),
        )
        try:
            first_result = await self._generate_result(
                {
                    "trigger": decision_input.model_dump(
                        mode="json",
                        exclude_none=True,
                    ),
                    "decision_reason": decision_reason,
                    "available_tools": TOOL_DESCRIPTIONS,
                    "limits": {
                        "remaining_tool_calls": 1,
                        "must_return_final": False,
                    },
                }
            )
            if first_result.status is ResponseStatus.FINAL:
                logger.info("[ResponseGenerator] tool_calls=0")
                return self._final_answer(first_result)

            call = first_result.tool_calls[0]
            if game_snapshot is None:
                logger.warning(
                    "[ResponseGenerator] tool_calls=0 tool=%s error=missing_snapshot",
                    call.name.value,
                )
                return RESPONSE_FALLBACK

            try:
                context_key, tool_result = self._tool_executor.execute(
                    DecisionAction.RESPOND,
                    call.name,
                    call.arguments,
                    game_snapshot,
                )
            except (ToolPermissionError, ValueError, KeyError) as exception:
                logger.warning(
                    "[ResponseGenerator] tool_calls=0 tool=%s error=%s",
                    call.name.value,
                    exception,
                )
                return RESPONSE_FALLBACK

            logger.info(
                "[ResponseGenerator] tool_calls=1 tool=%s",
                call.name.value,
            )
            final_result = await self._generate_result(
                {
                    "trigger": decision_input.model_dump(
                        mode="json",
                        exclude_none=True,
                    ),
                    "decision_reason": decision_reason,
                    "available_tools": TOOL_DESCRIPTIONS,
                    "tool_observation": {
                        "name": call.name.value,
                        "context_key": context_key,
                        "result": tool_result,
                    },
                    "limits": {
                        "remaining_tool_calls": 0,
                        "must_return_final": True,
                    },
                }
            )
            if final_result.status is ResponseStatus.NEED_TOOL:
                logger.warning(
                    "[ResponseGenerator] second_tool_denied tool=%s",
                    final_result.tool_calls[0].name.value,
                )
                return RESPONSE_FALLBACK
            return self._final_answer(final_result)
        except ResponseGeneratorError:
            raise
        except Exception as exception:
            raise ResponseGeneratorError(
                f"Response 模型调用失败: {exception}"
            ) from exception

    async def _generate_result(self, input_data: dict[str, Any]) -> ResponseResult:
        completion = await self._model_client.generate_structured(
            system_prompt=RESPONSE_SYSTEM_PROMPT,
            input_data=input_data,
            output_schema=ResponseResult.model_json_schema(),
        )
        log_model_completion(
            logger,
            "ResponseGenerator",
            self._model_client,
            completion,
        )
        raw_result = parse_json_object(completion.content)
        logger.debug("[ResponseGenerator] raw_response=%s", raw_result)
        return ResponseResult.model_validate(raw_result)

    @staticmethod
    def _final_answer(result: ResponseResult) -> str:
        if not result.answer:
            raise ResponseGeneratorError("Response 模型返回了空内容")
        logger.info("[ResponseGenerator] response=%s", result.answer)
        return result.answer
