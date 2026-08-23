import json
import os
import unittest
from unittest.mock import patch

import httpx

from agent.decision.model import DecisionModelConfig, SiliconFlowDecisionModelClient


def make_config() -> DecisionModelConfig:
    return DecisionModelConfig(
        model_name="test-model",
        api_key="test-key",
        base_url="https://example.test/v1",
        max_tokens=256,
        temperature=0.1,
        top_p=1.0,
        top_k=50,
        frequency_penalty=0.0,
        enable_thinking=False,
    )


class DecisionModelConfigTests(unittest.TestCase):
    def test_reads_decision_parameters_from_environment(self) -> None:
        values = {
            "TERRARIAFRIEND_DECISION_MODEL": "test-model",
            "TERRARIAFRIEND_DECISION_API_KEY": "test-key",
            "TERRARIAFRIEND_DECISION_BASE_URL": "https://example.test/v1",
            "TERRARIAFRIEND_DECISION_MAX_TOKENS": "256",
            "TERRARIAFRIEND_DECISION_TEMPERATURE": "0.1",
            "TERRARIAFRIEND_DECISION_TOP_P": "1.0",
            "TERRARIAFRIEND_DECISION_TOP_K": "50",
            "TERRARIAFRIEND_DECISION_FREQUENCY_PENALTY": "0.0",
            "TERRARIAFRIEND_DECISION_ENABLE_THINKING": "false",
        }

        with patch.dict(os.environ, values, clear=True):
            config = DecisionModelConfig.from_environment()

        self.assertEqual(256, config.max_tokens)
        self.assertEqual(0.1, config.temperature)
        self.assertEqual(1.0, config.top_p)
        self.assertEqual(50, config.top_k)
        self.assertEqual(0.0, config.frequency_penalty)
        self.assertFalse(config.enable_thinking)


class SiliconFlowDecisionModelClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_configured_decision_parameters(self) -> None:
        captured_body: dict[str, object] = {}

        async def handle_request(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"action":"IGNORE","reason":"测试"}'
                            }
                        }
                    ]
                },
            )

        transport = httpx.MockTransport(handle_request)
        async with httpx.AsyncClient(
            base_url="https://example.test/v1/",
            transport=transport,
        ) as http_client:
            client = SiliconFlowDecisionModelClient(make_config(), http_client)
            result = await client.generate_structured(
                system_prompt="test prompt",
                input_data={"trigger_type": "PERIODIC"},
                output_schema={"type": "object"},
            )

        self.assertEqual("IGNORE", result["action"])
        self.assertEqual(256, captured_body["max_tokens"])
        self.assertEqual(0.1, captured_body["temperature"])
        self.assertEqual(1.0, captured_body["top_p"])
        self.assertEqual(50, captured_body["top_k"])
        self.assertEqual(0.0, captured_body["frequency_penalty"])
        self.assertFalse(captured_body["enable_thinking"])
