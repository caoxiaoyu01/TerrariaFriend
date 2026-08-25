import unittest

from fastapi.testclient import TestClient

from agent.decision.schema import DecisionAction, DecisionInput, DecisionResult
from agent.main import (
    app,
    get_decision_node,
    get_periodic_gate,
    get_reasoning_graph,
    get_response_generator,
)
from agent.periodic_gate import (
    PERIODIC_MAX_SILENCE_SECONDS,
    PeriodicGate,
)
from tests.fakes import game_snapshot_payload, user_query_json


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FixedDecisionNode:
    model_name = "fixed-decision"

    def __init__(self, action: DecisionAction) -> None:
        self.action = action
        self.calls = 0

    async def decide(self, decision_input: DecisionInput) -> DecisionResult:
        self.calls += 1
        return DecisionResult(action=self.action, reason="periodic gate test")


class VisibleResponseGenerator:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *args: object) -> str:
        self.calls += 1
        return "可见回复"


class VisibleReasoningGraph:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, *args: object) -> str:
        self.calls += 1
        return "推理后的可见回复"


def periodic_json() -> dict[str, object]:
    return {
        "triggerType": "PERIODIC",
        "timestamp": "2026-08-26T12:00:00Z",
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


def game_event_json() -> dict[str, object]:
    return {
        "triggerType": "GAME_EVENT",
        "timestamp": "2026-08-26T12:00:00Z",
        "priority": "NORMAL",
        "vitals": {"hpRatio": 1.0, "hpDelta": 0.0, "inCombat": False},
        "gameEvent": {
            "eventType": "SceneFeatureEntered",
            "subjectId": "SPECIAL_AREA",
            "subjectName": "Pyramid",
        },
        "eventContext": {
            "biomes": ["Desert"],
            "layer": "Surface",
            "specialAreas": ["Pyramid"],
        },
        "gameSnapshot": game_snapshot_payload(),
    }


class PeriodicGateTests(unittest.TestCase):
    def test_random_hit_allows_periodic(self) -> None:
        gate = PeriodicGate(random_source=lambda: 0.05)

        self.assertEqual((True, "random_hit"), gate.should_allow())

    def test_recent_message_and_random_miss_skips_periodic(self) -> None:
        clock = FakeClock()
        gate = PeriodicGate(clock=clock, random_source=lambda: 0.50)
        gate.record_agent_message()
        clock.now = PERIODIC_MAX_SILENCE_SECONDS - 1

        self.assertEqual((False, "random_miss"), gate.should_allow())

    def test_silence_timeout_allows_periodic(self) -> None:
        clock = FakeClock()
        gate = PeriodicGate(clock=clock, random_source=lambda: 0.50)
        gate.record_agent_message()
        clock.now = PERIODIC_MAX_SILENCE_SECONDS

        self.assertEqual((True, "silence_timeout"), gate.should_allow())

    def test_current_periodic_hp_drop_allows_periodic(self) -> None:
        gate = PeriodicGate(random_source=lambda: 0.50)

        self.assertEqual((True, "hp_drop"), gate.should_allow(hp_drop=True))


class PeriodicGateRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.gate = PeriodicGate(clock=self.clock, random_source=lambda: 0.50)
        self.node = FixedDecisionNode(DecisionAction.RESPOND)
        self.generator = VisibleResponseGenerator()
        self.graph = VisibleReasoningGraph()
        app.dependency_overrides[get_periodic_gate] = lambda: self.gate
        app.dependency_overrides[get_decision_node] = lambda: self.node
        app.dependency_overrides[get_response_generator] = lambda: self.generator
        app.dependency_overrides[get_reasoning_graph] = lambda: self.graph

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_user_query_reply_refreshes_last_agent_message(self) -> None:
        self.clock.now = 10.0
        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=user_query_json(query="你好"))

        self.assertEqual("可见回复", response.json()["message"])
        self.assertEqual(10.0, self.gate.last_agent_message_at)

    def test_game_event_reply_refreshes_last_agent_message(self) -> None:
        self.clock.now = 20.0
        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=game_event_json())

        self.assertEqual("可见回复", response.json()["message"])
        self.assertEqual(20.0, self.gate.last_agent_message_at)

    def test_periodic_reply_refreshes_last_agent_message(self) -> None:
        self.clock.now = PERIODIC_MAX_SILENCE_SECONDS
        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=periodic_json())

        self.assertEqual("可见回复", response.json()["message"])
        self.assertEqual(
            PERIODIC_MAX_SILENCE_SECONDS,
            self.gate.last_agent_message_at,
        )

    def test_reason_final_reply_refreshes_last_agent_message(self) -> None:
        self.node.action = DecisionAction.REASON
        self.clock.now = 30.0
        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=user_query_json())

        self.assertEqual("推理后的可见回复", response.json()["message"])
        self.assertEqual(30.0, self.gate.last_agent_message_at)

    def test_rejected_periodic_does_not_call_decision(self) -> None:
        with TestClient(app) as client:
            response = client.post("/agent/trigger", json=periodic_json())

        self.assertEqual("IGNORE", response.json()["action"])
        self.assertEqual(0, self.node.calls)
        self.assertEqual(0, self.generator.calls)
        self.assertEqual(0, self.graph.calls)

    def test_game_event_does_not_allow_next_periodic(self) -> None:
        self.clock.now = 10.0
        with TestClient(app) as client:
            event_response = client.post("/agent/trigger", json=game_event_json())
            self.node.calls = 0
            self.generator.calls = 0

            periodic_response = client.post("/agent/trigger", json=periodic_json())

        self.assertEqual("RESPOND", event_response.json()["action"])
        self.assertEqual("IGNORE", periodic_response.json()["action"])
        self.assertEqual(0, self.node.calls)
        self.assertEqual(0, self.generator.calls)
        self.assertEqual(0, self.graph.calls)
