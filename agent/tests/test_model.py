import json
import os
import unittest
from unittest.mock import patch

import httpx

from agent.llm.client import RoleLLMClient, SiliconFlowClient
from agent.llm.config import AgentLLMSettings, ModelConfig, ProviderConfig


def environment_values() -> dict[str, str]:
    return {
        "TERRARIAFRIEND_LLM_API_KEY": "test-key",
        "TERRARIAFRIEND_LLM_BASE_URL": "https://example.test/v1",
        "TERRARIAFRIEND_DECISION_MODEL": "decision-model",
        "TERRARIAFRIEND_DECISION_TEMPERATURE": "0.2",
        "TERRARIAFRIEND_DECISION_MAX_TOKENS": "256",
        "TERRARIAFRIEND_DECISION_ENABLE_THINKING": "false",
        "TERRARIAFRIEND_DECISION_TOP_P": "1.0",
        "TERRARIAFRIEND_DECISION_TOP_K": "50",
        "TERRARIAFRIEND_DECISION_FREQUENCY_PENALTY": "0.0",
        "TERRARIAFRIEND_RESPONSE_MODEL": "response-model",
        "TERRARIAFRIEND_RESPONSE_TEMPERATURE": "0.5",
        "TERRARIAFRIEND_RESPONSE_MAX_TOKENS": "384",
        "TERRARIAFRIEND_RESPONSE_ENABLE_THINKING": "false",
        "TERRARIAFRIEND_REASONING_MODEL": "reasoning-model",
        "TERRARIAFRIEND_REASONING_TEMPERATURE": "0.6",
        "TERRARIAFRIEND_REASONING_MAX_TOKENS": "1024",
        "TERRARIAFRIEND_REASONING_ENABLE_THINKING": "true",
        "TERRARIAFRIEND_REASONING_EFFORT": "high",
    }


class AgentLLMSettingsTests(unittest.TestCase):
    def test_reads_independent_role_configuration(self) -> None:
        with patch.dict(os.environ, environment_values(), clear=True):
            settings = AgentLLMSettings.from_environment()

        self.assertEqual("test-key", settings.provider.api_key)
        self.assertEqual(0.2, settings.decision.temperature)
        self.assertEqual(384, settings.response.max_tokens)
        self.assertTrue(settings.reasoning.enable_thinking)
        self.assertEqual("high", settings.reasoning.reasoning_effort)

    def test_legacy_decision_credentials_are_shared(self) -> None:
        values = environment_values()
        values["TERRARIAFRIEND_DECISION_API_KEY"] = values.pop(
            "TERRARIAFRIEND_LLM_API_KEY"
        )
        values["TERRARIAFRIEND_DECISION_BASE_URL"] = values.pop(
            "TERRARIAFRIEND_LLM_BASE_URL"
        )

        with patch.dict(os.environ, values, clear=True):
            settings = AgentLLMSettings.from_environment()

        self.assertEqual("test-key", settings.provider.api_key)
        self.assertEqual("https://example.test/v1", settings.provider.base_url)


class SiliconFlowClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_role_parameters_and_reads_usage(self) -> None:
        captured_body: dict[str, object] = {}

        async def handle_request(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"status":"FINAL","answer":"测试"}',
                                "reasoning_content": "internal",
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "prompt_tokens_details": {"cached_tokens": 7},
                        "prompt_cache_hit_tokens": 7,
                        "prompt_cache_miss_tokens": 3,
                        "completion_tokens": 8,
                        "total_tokens": 18,
                        "completion_tokens_details": {"reasoning_tokens": 5},
                    },
                },
            )

        config = ModelConfig(
            role="reasoning",
            model_name="test-model",
            temperature=0.6,
            max_tokens=1024,
            enable_thinking=True,
            reasoning_effort="high",
        )
        transport = httpx.MockTransport(handle_request)
        async with httpx.AsyncClient(
            base_url="https://example.test/v1/",
            transport=transport,
        ) as http_client:
            shared_client = SiliconFlowClient(
                ProviderConfig("test-key", "https://example.test/v1"),
                http_client,
            )
            role_client = RoleLLMClient(shared_client, config)
            completion = await role_client.generate_structured(
                system_prompt="test",
                input_data={"task": "test"},
                output_schema={"type": "object"},
            )

        self.assertEqual("test-model", captured_body["model"])
        self.assertEqual(1024, captured_body["max_tokens"])
        self.assertEqual(0.6, captured_body["temperature"])
        self.assertTrue(captured_body["enable_thinking"])
        self.assertEqual("high", captured_body["reasoning_effort"])
        self.assertEqual({"type": "json_object"}, captured_body["response_format"])
        self.assertEqual(7, completion.usage.cached_tokens)
        self.assertEqual(7, completion.usage.cache_hit_tokens)
        self.assertEqual(3, completion.usage.cache_miss_tokens)
        self.assertEqual(5, completion.usage.reasoning_tokens)
        self.assertEqual("internal", completion.reasoning_content)

    async def test_missing_cache_usage_fields_are_none(self) -> None:
        async def handle_request(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 2,
                        "total_tokens": 6,
                    },
                },
            )

        transport = httpx.MockTransport(handle_request)
        async with httpx.AsyncClient(
            base_url="https://example.test/v1/",
            transport=transport,
        ) as http_client:
            shared_client = SiliconFlowClient(
                ProviderConfig("test-key", "https://example.test/v1"),
                http_client,
            )
            role_client = RoleLLMClient(
                shared_client,
                ModelConfig(
                    role="response",
                    model_name="response-model",
                    temperature=0.5,
                    max_tokens=384,
                    enable_thinking=False,
                ),
            )
            completion = await role_client.generate_text(
                system_prompt="test",
                input_data={"query": "hello"},
            )

        self.assertIsNone(completion.usage.cached_tokens)
        self.assertIsNone(completion.usage.cache_hit_tokens)
        self.assertIsNone(completion.usage.cache_miss_tokens)
