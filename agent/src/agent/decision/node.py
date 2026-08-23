import logging

from pydantic import ValidationError

from agent.decision.model import (
    DecisionModelClient,
    DecisionModelConfig,
    SiliconFlowDecisionModelClient,
)
from agent.decision.prompt import DECISION_SYSTEM_PROMPT
from agent.decision.schema import DecisionInput, DecisionResult

logger = logging.getLogger("uvicorn.error")


class DecisionNodeError(RuntimeError):
    pass


# 组合 Prompt 模型客户端和输出校验
class DecisionNode:
    def __init__(self, model_client: DecisionModelClient) -> None:
        self._model_client = model_client

    @classmethod
    def from_environment(cls) -> "DecisionNode":
        config = DecisionModelConfig.from_environment()
        return cls(SiliconFlowDecisionModelClient(config))

    @property
    def model_name(self) -> str:
        return self._model_client.model_name

    async def decide(self, decision_input: DecisionInput) -> DecisionResult:
        try:
            # 将 JSON Schema 一并交给模型适配器请求结构化输出
            raw_result = await self._model_client.generate_structured(
                system_prompt=DECISION_SYSTEM_PROMPT,
                input_data=decision_input.model_dump(mode="json", exclude_none=True),
                output_schema=DecisionResult.model_json_schema(),
            )
            logger.debug("[DecisionNode] model_response=%s", raw_result)
            # 本地再次校验
            return DecisionResult.model_validate(raw_result)
        
        except ValidationError as exception:
            raise DecisionNodeError("Decision 模型返回了无效结构") from exception
        except Exception as exception:
            raise DecisionNodeError(f"Decision 模型调用失败: {exception}") from exception

    async def aclose(self) -> None:
        await self._model_client.aclose()
