import json
import unittest
from typing import Any

import httpx
from fastapi.testclient import TestClient

from agent.decision.node import DecisionNode, DecisionNodeError
from agent.decision.prompt import DECISION_SYSTEM_PROMPT
from agent.decision.schema import DecisionAction, DecisionInput, DecisionResult
from agent.llm.client import RoleLLMClient, SiliconFlowClient
from agent.llm.config import ModelConfig, ProviderConfig
from agent.main import (
    app,
    get_decision_node,
    get_reasoning_graph,
    get_response_generator,
)
from agent.models.trigger import TriggerRequest
from tests.fakes import ScriptedRoleLLMClient, game_snapshot_payload, user_query_json


class FixedDecisionNode:
    model_name = "fixed-decision"

    def __init__(self, action: DecisionAction) -> None:
        self.action = action
        self.calls = 0

    async def decide(self, decision_input: DecisionInput) -> DecisionResult:
        self.calls += 1
        return DecisionResult(
            action=self.action,
            reason="测试路由",
        )


class FailingDecisionNode:
    model_name = "failing-decision"

    async def decide(self, decision_input: DecisionInput) -> DecisionResult:
        raise DecisionNodeError("Decision 模型调用失败: test")


class FakeResponseGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[DecisionInput, str, object]] = []

    async def generate(
        self,
        decision_input: DecisionInput,
        reason: str,
        game_snapshot: object = None,
    ) -> str:
        self.calls.append((decision_input, reason, game_snapshot))
        return "直接回复"


class FakeReasoningGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[TriggerRequest, DecisionInput, str]] = []

    async def run(
        self,
        trigger: TriggerRequest,
        decision_input: DecisionInput,
        reason: str,
    ) -> str:
        self.calls.append((trigger, decision_input, reason))
        return "推理后的回复"


class DecisionNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_prompt_shaped_output_for_all_actions(self) -> None:
        cases = [
            (
                {
                    "action": "RESPOND",
                    "reason": "当前信息足够直接回答",
                },
                DecisionAction.RESPOND,
            ),
            (
                {
                    "action": "REASON",
                    "reason": "需要额外游戏状态",
                },
                DecisionAction.REASON,
            ),
            (
                {
                    "action": "IGNORE",
                    "reason": "当前无需处理",
                },
                DecisionAction.IGNORE,
            ),
        ]
        trigger = TriggerRequest.model_validate(user_query_json())

        for model_output, expected_action in cases:
            with self.subTest(model_output=model_output):
                client = ScriptedRoleLLMClient([model_output], role="decision")
                result = await DecisionNode(client).decide(
                    DecisionInput.from_trigger(trigger)
                )

                self.assertEqual(expected_action, result.action)
                self.assertNotIn("game_snapshot", client.inputs[0])

    def test_dynamic_payload_uses_trigger_specific_compact_shape(self) -> None:
        game_event = TriggerRequest.model_validate(
            {
                "triggerType": "GAME_EVENT",
                "timestamp": "2026-08-25T12:00:00Z",
                "priority": "NORMAL",
                "vitals": {
                    "hpRatio": 0.8,
                    "hpDelta": -0.02,
                    "inCombat": True,
                },
                "gameEvent": {
                    "eventType": "SceneFeatureEntered",
                    "subjectId": "MINI_BIOME",
                    "subjectName": "Bee Hive",
                },
                "eventContext": {
                    "biomes": ["Jungle"],
                    "layer": "Cavern",
                    "miniBiomes": ["Bee Hive"],
                },
            }
        )
        periodic = TriggerRequest.model_validate(
            {
                "triggerType": "PERIODIC",
                "timestamp": "2026-08-25T12:00:00Z",
                "priority": "LOW",
                "vitals": {
                    "hpRatio": 1.0,
                    "hpDelta": 0.0,
                    "inCombat": False,
                },
                "periodicSummary": {
                    "biomes": ["Forest"],
                    "layer": "Surface",
                    "activeBosses": [],
                    "progressionStage": "Pre-Hardmode",
                    "heldItem": "Copper Pickaxe",
                },
            }
        )

        event_payload = DecisionInput.from_trigger(game_event).to_prompt_payload()
        periodic_payload = DecisionInput.from_trigger(periodic).to_prompt_payload()

        self.assertEqual(
            {"trigger_type", "event_type", "payload", "event_context", "vitals"},
            set(event_payload),
        )
        self.assertEqual("SceneFeatureEntered", event_payload["event_type"])
        self.assertEqual("Bee Hive", event_payload["payload"]["feature_name"])
        self.assertEqual(
            {"trigger_type", "summary", "vitals"},
            set(periodic_payload),
        )

    async def test_messages_keep_fixed_system_and_compact_dynamic_user_data(self) -> None:
        captured_body: dict[str, Any] = {}

        async def handle_request(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "action": "RESPOND",
                                        "reason": "简单问候",
                                    },
                                    ensure_ascii=False,
                                )
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
            shared_client = SiliconFlowClient(
                ProviderConfig("test-key", "https://example.test/v1"),
                http_client,
            )
            role_client = RoleLLMClient(
                shared_client,
                ModelConfig(
                    role="decision",
                    model_name="decision-model",
                    temperature=0.2,
                    max_tokens=256,
                    enable_thinking=False,
                ),
            )
            trigger = TriggerRequest.model_validate(
                user_query_json(query="你好")
            )
            decision_input = DecisionInput.from_trigger(trigger)
            await DecisionNode(role_client).decide(decision_input)

        messages = captured_body["messages"]
        self.assertEqual(
            {"role": "system", "content": DECISION_SYSTEM_PROMPT},
            messages[0],
        )
        expected_payload = {
            "trigger_type": "USER_QUERY",
            "query": "你好",
            "vitals": {
                "hp_ratio": 0.38,
                "hp_delta": 0.0,
                "in_combat": True,
            },
        }
        self.assertEqual("user", messages[1]["role"])
        self.assertEqual(expected_payload, json.loads(messages[1]["content"]))
        self.assertEqual(
            json.dumps(expected_payload, ensure_ascii=False, separators=(",", ":")),
            messages[1]["content"],
        )
        self.assertNotIn("你好", messages[0]["content"])
        self.assertNotIn("output_schema", messages[1]["content"])
        self.assertNotIn("game_snapshot", messages[1]["content"])
        for cache_parameter in (
            "cache",
            "prompt_cache",
            "cache_control",
            "cached_prompt",
        ):
            self.assertNotIn(cache_parameter, captured_body)

    async def test_invalid_model_output_is_rejected(self) -> None:
        node = DecisionNode(
            ScriptedRoleLLMClient(
                [
                    {
                        "action": "INVALID",
                        "reason": "",
                    }
                ],
                role="decision",
            )
        )
        trigger = TriggerRequest.model_validate(user_query_json())

        with self.assertRaises(DecisionNodeError):
            await node.decide(DecisionInput.from_trigger(trigger))


class AgentRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def _configure(
        self,
        node: Any,
        generator: FakeResponseGenerator,
        graph: FakeReasoningGraph,
    ) -> None:
        app.dependency_overrides[get_decision_node] = lambda: node
        app.dependency_overrides[get_response_generator] = lambda: generator
        app.dependency_overrides[get_reasoning_graph] = lambda: graph

    def test_respond_uses_response_generator_only(self) -> None:
        node = FixedDecisionNode(DecisionAction.RESPOND)
        generator = FakeResponseGenerator()
        graph = FakeReasoningGraph()
        self._configure(node, generator, graph)

        with TestClient(app) as client:
            response = client.post(
                "/agent/trigger",
                json=user_query_json(query="你好"),
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("RESPOND", response.json()["action"])
        self.assertEqual("直接回复", response.json()["message"])
        self.assertEqual(1, len(generator.calls))
        self.assertFalse(graph.calls)

    def test_fake_llm_hello_routes_to_response_generator(self) -> None:
        node = DecisionNode(
            ScriptedRoleLLMClient(
                [
                    {
                        "action": "RESPOND",
                        "reason": "简单问候可以直接回复",
                    }
                ],
                role="decision",
            )
        )
        generator = FakeResponseGenerator()
        graph = FakeReasoningGraph()
        self._configure(node, generator, graph)

        with TestClient(app) as client:
            response = client.post(
                "/agent/trigger",
                json=user_query_json(query="你好"),
            )

        self.assertEqual("RESPOND", response.json()["action"])
        self.assertEqual(1, len(generator.calls))
        self.assertFalse(graph.calls)

    def test_game_event_respond_uses_response_generator(self) -> None:
        node = FixedDecisionNode(DecisionAction.RESPOND)
        generator = FakeResponseGenerator()
        graph = FakeReasoningGraph()
        self._configure(node, generator, graph)
        request = {
            "triggerType": "GAME_EVENT",
            "timestamp": "2026-08-25T12:00:00Z",
            "priority": "NORMAL",
            "vitals": {"hpRatio": 0.9, "hpDelta": 0.0, "inCombat": False},
            "gameEvent": {
                "eventType": "SceneFeatureEntered",
                "subjectId": "MINI_BIOME",
                "subjectName": "Bee Hive",
            },
            "eventContext": {
                "biomes": ["Jungle"],
                "layer": "Cavern",
                "miniBiomes": ["Bee Hive"],
                "specialAreas": [],
            },
            "gameSnapshot": game_snapshot_payload(),
        }

        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=request)

        self.assertEqual("RESPOND", response.json()["action"])
        decision_input = generator.calls[0][0]
        self.assertEqual("Bee Hive", decision_input.game_event.payload["feature_name"])
        self.assertFalse(graph.calls)

    def test_reason_uses_reasoning_graph_only(self) -> None:
        node = FixedDecisionNode(DecisionAction.REASON)
        generator = FakeResponseGenerator()
        graph = FakeReasoningGraph()
        self._configure(node, generator, graph)

        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=user_query_json())

        self.assertEqual("REASON", response.json()["action"])
        self.assertEqual("推理后的回复", response.json()["message"])
        self.assertEqual(1, len(graph.calls))
        self.assertIsNotNone(graph.calls[0][0].game_snapshot)
        self.assertFalse(generator.calls)

    def test_fake_llm_next_step_routes_to_reasoning_graph(self) -> None:
        node = DecisionNode(
            ScriptedRoleLLMClient(
                [
                    {
                        "action": "REASON",
                        "reason": "需要结合当前进度和装备",
                    }
                ],
                role="decision",
            )
        )
        generator = FakeResponseGenerator()
        graph = FakeReasoningGraph()
        self._configure(node, generator, graph)

        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=user_query_json())

        self.assertEqual("REASON", response.json()["action"])
        self.assertEqual(1, len(graph.calls))
        self.assertFalse(generator.calls)

    def test_hp_drop_forces_reason_without_calling_decision_model(self) -> None:
        node = FixedDecisionNode(DecisionAction.IGNORE)
        generator = FakeResponseGenerator()
        graph = FakeReasoningGraph()
        self._configure(node, generator, graph)

        with TestClient(app) as client:
            response = client.post(
                "/agent/trigger",
                json=user_query_json(hp_delta=-0.15),
            )

        self.assertEqual("REASON", response.json()["action"])
        self.assertIn("近期明显掉血", response.json()["decisionReason"])
        self.assertEqual(0, node.calls)
        self.assertEqual(1, len(graph.calls))

    def test_ignore_finishes_without_response_path(self) -> None:
        node = FixedDecisionNode(DecisionAction.IGNORE)
        generator = FakeResponseGenerator()
        graph = FakeReasoningGraph()
        self._configure(node, generator, graph)

        request = {
            "triggerType": "PERIODIC",
            "timestamp": "2026-08-25T12:00:00Z",
            "priority": "LOW",
            "vitals": {"hpRatio": 1.0, "hpDelta": 0.0, "inCombat": False},
            "periodicSummary": {
                "biomes": ["Forest"],
                "layer": "Surface",
                "activeBosses": [],
                "progressionStage": "Pre-Hardmode",
                "heldItem": "Copper Pickaxe",
            },
            "gameSnapshot": game_snapshot_payload(),
        }
        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=request)

        self.assertEqual("IGNORE", response.json()["action"])
        self.assertIsNone(response.json()["message"])
        self.assertFalse(generator.calls)
        self.assertFalse(graph.calls)

    def test_decision_failure_returns_business_error(self) -> None:
        generator = FakeResponseGenerator()
        graph = FakeReasoningGraph()
        self._configure(FailingDecisionNode(), generator, graph)

        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=user_query_json())

        self.assertFalse(response.json()["success"])
        self.assertEqual("ERROR", response.json()["action"])
