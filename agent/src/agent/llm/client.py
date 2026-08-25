import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from agent.llm.config import ModelConfig, ProviderConfig


@dataclass(frozen=True, slots=True)
class LLMUsage:
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    cache_hit_tokens: int | None = None
    cache_miss_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class LLMCompletion:
    content: str
    reasoning_content: str | None
    usage: LLMUsage
    latency_seconds: float


class SiliconFlowClient:
    def __init__(
        self,
        config: ProviderConfig,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=f"{config.base_url.rstrip('/')}/",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=config.timeout_seconds,
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        config: ModelConfig,
        *,
        json_output: bool,
    ) -> LLMCompletion:
        request_body: dict[str, Any] = {
            "model": config.model_name,
            "messages": messages,
            "stream": False,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "enable_thinking": config.enable_thinking,
        }
        if config.reasoning_effort is not None:
            request_body["reasoning_effort"] = config.reasoning_effort
        if config.top_p is not None:
            request_body["top_p"] = config.top_p
        if config.top_k is not None:
            request_body["top_k"] = config.top_k
        if config.frequency_penalty is not None:
            request_body["frequency_penalty"] = config.frequency_penalty
        if json_output:
            request_body["response_format"] = {"type": "json_object"}

        started_at = time.perf_counter()
        response = await self._client.post("chat/completions", json=request_body)
        response.raise_for_status()
        response_data = response.json()
        latency = time.perf_counter() - started_at

        message = response_data["choices"][0]["message"]
        usage_data = response_data.get("usage") or {}
        prompt_details = usage_data.get("prompt_tokens_details") or {}
        completion_details = usage_data.get("completion_tokens_details") or {}
        return LLMCompletion(
            content=message.get("content") or "",
            reasoning_content=message.get("reasoning_content"),
            usage=LLMUsage(
                prompt_tokens=usage_data.get("prompt_tokens"),
                cached_tokens=prompt_details.get("cached_tokens"),
                cache_hit_tokens=usage_data.get("prompt_cache_hit_tokens"),
                cache_miss_tokens=usage_data.get("prompt_cache_miss_tokens"),
                completion_tokens=usage_data.get("completion_tokens"),
                reasoning_tokens=completion_details.get("reasoning_tokens"),
                total_tokens=usage_data.get("total_tokens"),
            ),
            latency_seconds=latency,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class RoleLLMClient:
    def __init__(self, client: SiliconFlowClient, config: ModelConfig) -> None:
        self._client = client
        self.config = config

    @property
    def model_name(self) -> str:
        return self.config.model_name

    async def generate_text(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
    ) -> LLMCompletion:
        return await self._client.complete(
            _messages(system_prompt, input_data),
            self.config,
            json_output=False,
        )

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
        include_output_schema: bool = True,
    ) -> LLMCompletion:
        payload = (
            {"input": input_data, "output_schema": output_schema}
            if include_output_schema
            else input_data
        )
        return await self._client.complete(
            _messages(system_prompt, payload),
            self.config,
            json_output=True,
        )


def parse_json_object(content: str) -> object:
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1 :] if first_newline >= 0 else text
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text.strip())


def log_model_completion(
    logger: logging.Logger,
    component: str,
    client: RoleLLMClient,
    completion: LLMCompletion,
) -> None:
    usage = completion.usage
    logger.info(
        "[LLM] component=%s role=%s model=%s thinking=%s reasoning_effort=%s "
        "prompt_tokens=%s cached_tokens=%s cache_hit_tokens=%s "
        "cache_miss_tokens=%s completion_tokens=%s reasoning_tokens=%s "
        "total_tokens=%s latency=%.2fs",
        component,
        client.config.role,
        client.model_name,
        str(client.config.enable_thinking).lower(),
        client.config.reasoning_effort,
        usage.prompt_tokens,
        usage.cached_tokens,
        usage.cache_hit_tokens,
        usage.cache_miss_tokens,
        usage.completion_tokens,
        usage.reasoning_tokens,
        usage.total_tokens,
        completion.latency_seconds,
    )


def _messages(
    system_prompt: str,
    input_data: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(input_data, ensure_ascii=False, separators=(",", ":")),
        },
    ]
