import unittest

from fastapi.testclient import TestClient

from agent.decision.schema import DecisionAction, DecisionInput, DecisionResult
from agent.main import (
    app,
    get_decision_node,
    get_reasoning_graph,
    get_response_generator,
)
from agent.reasoning.graph import ReasoningGraph
from agent.reasoning.reasoner import Reasoner
from agent.response.generator import ResponseGenerator
from tests.fakes import ScriptedRoleLLMClient, game_snapshot_payload, user_query_json


class StaticDecisionNode:
    model_name = "pipeline-decision"

    def __init__(self, action: DecisionAction) -> None:
        self.action = action

    async def decide(self, decision_input: DecisionInput) -> DecisionResult:
        return DecisionResult(
            action=self.action,
            reason="pipeline test",
        )


class UnexpectedDecisionNode:
    model_name = "should-not-run"

    async def decide(self, decision_input: DecisionInput) -> DecisionResult:
        raise AssertionError("掉血硬规则不应调用 Decision 模型")


class UnexpectedGraph:
    async def run(self, *args: object) -> str:
        raise AssertionError("RESPOND 不应进入 ReasoningGraph")


class Phase2APipelineTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_user_query_reason_runs_multi_round_tool_loop(self) -> None:
        reasoning_client = ScriptedRoleLLMClient(
            [
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {"name": "get_progress_context", "arguments": {}}
                    ],
                },
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {"name": "get_inventory_context", "arguments": {}},
                        {"name": "get_scene_context", "arguments": {}},
                    ],
                },
                {"status": "FINAL", "answer": "先升级装备，再继续探索丛林。"},
            ],
            role="reasoning",
            enable_thinking=True,
        )
        graph = ReasoningGraph(Reasoner(reasoning_client))
        unused_response = ResponseGenerator(
            ScriptedRoleLLMClient(["unused"], role="response")
        )
        app.dependency_overrides[get_decision_node] = lambda: StaticDecisionNode(
            DecisionAction.REASON
        )
        app.dependency_overrides[get_reasoning_graph] = lambda: graph
        app.dependency_overrides[get_response_generator] = lambda: unused_response

        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=user_query_json())

        self.assertEqual("REASON", response.json()["action"])
        self.assertEqual("先升级装备，再继续探索丛林。", response.json()["message"])
        self.assertEqual(3, len(reasoning_client.inputs))

    def test_health_rule_runs_combat_and_inventory_tools(self) -> None:
        reasoning_client = ScriptedRoleLLMClient(
            [
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {"name": "get_combat_context", "arguments": {}},
                        {"name": "get_inventory_context", "arguments": {}},
                    ],
                },
                {
                    "status": "FINAL",
                    "answer": "先远离黄蜂并使用治疗药水，再寻找安全位置。",
                },
            ],
            role="reasoning",
            enable_thinking=True,
        )
        graph = ReasoningGraph(Reasoner(reasoning_client))
        app.dependency_overrides[get_decision_node] = lambda: UnexpectedDecisionNode()
        app.dependency_overrides[get_reasoning_graph] = lambda: graph
        app.dependency_overrides[get_response_generator] = lambda: ResponseGenerator(
            ScriptedRoleLLMClient(["unused"], role="response")
        )

        with TestClient(app) as client:
            response = client.post(
                "/agent/trigger",
                json=user_query_json(hp_delta=-0.15),
            )

        self.assertEqual("REASON", response.json()["action"])
        self.assertIn("治疗药水", response.json()["message"])
        self.assertEqual(
            {"combat", "inventory"},
            set(reasoning_client.inputs[1]["collected_context"]),
        )

    def test_scene_event_respond_uses_response_generator(self) -> None:
        response_client = ScriptedRoleLLMClient(
            [
                {
                    "status": "FINAL",
                    "answer": "你进入蜂巢了，小心黄蜂，并提前留好撤退路线。",
                }
            ],
            role="response",
        )
        app.dependency_overrides[get_decision_node] = lambda: StaticDecisionNode(
            DecisionAction.RESPOND
        )
        app.dependency_overrides[get_response_generator] = lambda: ResponseGenerator(
            response_client
        )
        app.dependency_overrides[get_reasoning_graph] = lambda: UnexpectedGraph()
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
        self.assertIn("蜂巢", response.json()["message"])
        self.assertEqual(1, len(response_client.inputs))
