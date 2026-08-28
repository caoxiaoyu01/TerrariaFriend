import logging

from pydantic import ValidationError

from agent.decision.prompt import DECISION_SYSTEM_PROMPT
from agent.decision.schema import DecisionInput, DecisionResult
from agent.llm.client import (
    RoleLLMClient,
    log_model_completion,
    parse_json_object,
)

logger = logging.getLogger("uvicorn.error")


class DecisionNodeError(RuntimeError):
    pass


# 负责调用决策模型并检查返回结果
class DecisionNode:
    def __init__(self, model_client: RoleLLMClient) -> None:
        self._model_client = model_client

    @property
    def model_name(self) -> str:
        return self._model_client.model_name

    async def decide(self, decision_input: DecisionInput) -> DecisionResult:
        try:
            # 固定规则和本次输入分开发送
            completion = await self._model_client.generate_structured(
                system_prompt=DECISION_SYSTEM_PROMPT,
                input_data=decision_input.to_prompt_payload(),
                output_schema=DecisionResult.model_json_schema(),
                include_output_schema=False,
            )
            log_model_completion(logger, "DecisionNode", self._model_client, completion)
            raw_result = parse_json_object(completion.content)
            logger.debug("[DecisionNode] model_response=%s", raw_result)
            return DecisionResult.model_validate(raw_result)

        except ValidationError as exception:
            raise DecisionNodeError("Decision 模型返回了无效结构") from exception
        except Exception as exception:
            raise DecisionNodeError(f"Decision 模型调用失败: {exception}") from exception
