import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from dotenv import load_dotenv

"""
    model 配置
"""

_AGENT_ROOT = Path(__file__).resolve().parents[3]


# 模型配置统一从环境变量读取
@dataclass(frozen=True, slots=True)
class DecisionModelConfig:
    model_name: str
    api_key: str = field(repr=False)
    base_url: str
    max_tokens: int
    temperature: float
    top_p: float
    top_k: int
    frequency_penalty: float
    enable_thinking: bool

    @classmethod
    def from_environment(cls) -> "DecisionModelConfig":
        # 加载本地配置 系统环境变量优先
        load_dotenv(_AGENT_ROOT / ".env", override=False)
        return cls(
            model_name=os.environ["TERRARIAFRIEND_DECISION_MODEL"],
            api_key=os.environ["TERRARIAFRIEND_DECISION_API_KEY"],
            base_url=os.environ["TERRARIAFRIEND_DECISION_BASE_URL"],
            max_tokens=int(os.environ["TERRARIAFRIEND_DECISION_MAX_TOKENS"]),
            temperature=float(os.environ["TERRARIAFRIEND_DECISION_TEMPERATURE"]),
            top_p=float(os.environ["TERRARIAFRIEND_DECISION_TOP_P"]),
            top_k=int(os.environ["TERRARIAFRIEND_DECISION_TOP_K"]),
            frequency_penalty=float(
                os.environ["TERRARIAFRIEND_DECISION_FREQUENCY_PENALTY"]
            ),
            enable_thinking=(
                os.environ["TERRARIAFRIEND_DECISION_ENABLE_THINKING"].lower()
                == "true"
            ),
        )


# 不绑定供应商的结构化模型调用接口
class DecisionModelClient(Protocol):
    @property
    def model_name(self) -> str: ...

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> object: ...

    async def aclose(self) -> None: ...


class SiliconFlowDecisionModelClient:
    def __init__(
        self,
        config: DecisionModelConfig,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = http_client or httpx.AsyncClient(
            base_url=f"{config.base_url.rstrip('/')}/",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30.0,
        )

    @property
    def model_name(self) -> str:
        return self._config.model_name

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> object:
        # 将 Decision 输入和输出约束一起交给模型
        user_content = json.dumps(
            {"input": input_data, "output_schema": output_schema},
            ensure_ascii=False,
        )
        request_body = {
            "model": self._config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
            "top_p": self._config.top_p,
            "top_k": self._config.top_k,
            "frequency_penalty": self._config.frequency_penalty,
            "enable_thinking": self._config.enable_thinking,
            "response_format": {"type": "json_object"},
        }

        response = await self._client.post("chat/completions", json=request_body)
        response.raise_for_status()
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        return json.loads(content)

    async def aclose(self) -> None:
        await self._client.aclose()
