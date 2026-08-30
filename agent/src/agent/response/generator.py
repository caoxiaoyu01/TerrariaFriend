import logging
from typing import Any

from pydantic import BaseModel, field_validator

from agent.decision.schema import DecisionAction, DecisionInput
from agent.llm.client import (
    RoleLLMClient,
    log_model_completion,
    parse_json_object,
)
from agent.models.execution import AgentExecutionResult
from agent.response.prompt import RESPONSE_SYSTEM_PROMPT


logger = logging.getLogger("uvicorn.error")


class ResponseGeneratorError(RuntimeError):
    pass


class ResponseResult(BaseModel):
    answer: str

    @field_validator("answer")
    @classmethod
    def normalize_answer(cls, value: str) -> str:
        answer = value.strip()
        if not answer:
            raise ValueError("answer 不能为空")
        return answer


class ResponseGenerator:
    def __init__(
        self,
        model_client: RoleLLMClient,
    ) -> None:
        self._model_client = model_client

    async def generate(
        self,
        decision_input: DecisionInput,
        decision_reason: str,
        prepared_context: dict[str, dict[str, Any]] | None = None,
    ) -> AgentExecutionResult:
        logger.info(
            "[ResponseGenerator] trigger=%s model=%s thinking=%s",
            decision_input.trigger_type.value,
            self._model_client.model_name,
            str(self._model_client.config.enable_thinking).lower(),
        )
        try:
            result = await self._generate_result(
                {
                    "trigger": decision_input.model_dump(
                        mode="json",
                        exclude_none=True,
                    ),
                    "decision_reason": decision_reason,
                    "game_context": prepared_context or {},
                }
            )
            logger.info("[ResponseGenerator] response=%s", result.answer)
            return AgentExecutionResult(
                message=result.answer,
                decision_action=DecisionAction.RESPOND,
                reasoning_rounds=1,
                used_game_context=prepared_context or {},
            )
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
