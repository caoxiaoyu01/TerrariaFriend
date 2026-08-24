import unittest
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from agent.decision.node import DecisionNode, DecisionNodeError
from agent.decision.schema import DecisionAction, DecisionGameEvent, DecisionInput
from agent.main import app, get_decision_node
from agent.models.trigger import (
    EventContext,
    GameEventRequest,
    GameEventType,
    PeriodicSummary,
    TriggerPriority,
    TriggerRequest,
    TriggerType,
    VitalsContext,
)


# 使用 Fake Model 验证 Decision 契约 不调用真实模型
class FakeDecisionModelClient:
    model_name = "fake-model"

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> object:
        trigger_type = input_data["trigger_type"]
        if trigger_type == TriggerType.USER_QUERY.value:
            query = input_data["user_query"]
            action = "REASON" if "下一步" in query else "RESPOND"
            return {"action": action, "reason": "用户问题需要对应处理路径"}

        if trigger_type == TriggerType.PERIODIC.value:
            held_item = input_data["periodic_summary"]["held_item"]
            action = "RESPOND" if "Fishing" in held_item else "IGNORE"
            return {"action": action, "reason": "根据轻量周期摘要判断"}

        event_type = input_data["game_event"]["event_type"]
        action = "RESPOND" if event_type == GameEventType.PLAYER_DIED.value else "IGNORE"
        return {"action": action, "reason": "根据游戏事件本身判断"}


class InvalidDecisionModelClient:
    model_name = "invalid-model"

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> object:
        return {"action": "INVALID", "reason": ""}


class FailingDecisionModelClient:
    model_name = "failing-model"

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> object:
        raise RuntimeError("test model unavailable")


class UnexpectedCallDecisionModelClient:
    model_name = "should-not-run"

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> object:
        raise AssertionError("硬规则不应调用模型")


def calm_periodic_summary() -> PeriodicSummary:
    return PeriodicSummary(
        biomes=["Forest"],
        layer="Surface",
        active_bosses=[],
        progression_stage="Pre-Hardmode",
        held_item="Copper Pickaxe",
    )


def calm_vitals(*, hp_ratio: float = 1.0, hp_delta: float = 0.0) -> VitalsContext:
    return VitalsContext(
        hp_ratio=hp_ratio,
        hp_delta=hp_delta,
        in_combat=False,
    )


class DecisionNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_six_trigger_scenarios_return_valid_schema(self) -> None:
        fishing = calm_periodic_summary().model_copy(
            update={"biomes": ["Ocean"], "held_item": "Fiberglass Fishing Pole"}
        )
        cases = [
            (
                DecisionInput(
                    trigger_type=TriggerType.USER_QUERY,
                    vitals=calm_vitals(),
                    user_query="我下一步应该干嘛？",
                ),
                DecisionAction.REASON,
            ),
            (
                DecisionInput(
                    trigger_type=TriggerType.USER_QUERY,
                    vitals=calm_vitals(),
                    user_query="你好",
                ),
                DecisionAction.RESPOND,
            ),
            (
                DecisionInput(
                    trigger_type=TriggerType.PERIODIC,
                    vitals=calm_vitals(),
                    periodic_summary=calm_periodic_summary(),
                ),
                DecisionAction.IGNORE,
            ),
            (
                DecisionInput(
                    trigger_type=TriggerType.PERIODIC,
                    vitals=calm_vitals(),
                    periodic_summary=fishing,
                ),
                DecisionAction.RESPOND,
            ),
            (
                DecisionInput(
                    trigger_type=TriggerType.GAME_EVENT,
                    vitals=calm_vitals(),
                    game_event=DecisionGameEvent(
                        event_type=GameEventType.NEW_AREA_DISCOVERED,
                        payload={"cell_x": 18, "cell_y": 10},
                    ),
                    event_context=EventContext(
                        biomes=["Forest"],
                        layer="Cavern",
                        mini_biomes=[],
                        special_areas=[],
                        previous_biomes=["Forest"],
                        previous_layer="Cavern",
                        previous_mini_biomes=[],
                        previous_special_areas=[],
                    ),
                ),
                DecisionAction.IGNORE,
            ),
            (
                DecisionInput(
                    trigger_type=TriggerType.GAME_EVENT,
                    vitals=calm_vitals(),
                    game_event=DecisionGameEvent(
                        event_type=GameEventType.PLAYER_DIED,
                        payload={"player_name": "Player"},
                    ),
                    event_context=EventContext(
                        biomes=["Forest"],
                        nearby_enemy_count=1,
                        boss_active=False,
                        damage_taken_last_5s=20,
                        last_damage_source="Zombie",
                    ),
                ),
                DecisionAction.RESPOND,
            ),
        ]

        node = DecisionNode(FakeDecisionModelClient())
        for decision_input, expected_action in cases:
            with self.subTest(trigger_type=decision_input.trigger_type):
                result = await node.decide(decision_input)
                self.assertEqual(expected_action, result.action)
                self.assertTrue(result.reason)

    async def test_invalid_model_output_is_rejected(self) -> None:
        node = DecisionNode(InvalidDecisionModelClient())
        decision_input = DecisionInput(
            trigger_type=TriggerType.USER_QUERY,
            vitals=calm_vitals(),
            user_query="你好",
        )

        with self.assertRaises(DecisionNodeError):
            await node.decide(decision_input)

    def test_new_area_coordinates_are_mapped_to_payload(self) -> None:
        trigger = TriggerRequest(
            trigger_type=TriggerType.GAME_EVENT,
            timestamp=datetime.now(timezone.utc),
            priority=TriggerPriority.NORMAL,
            vitals=calm_vitals(),
            game_event=GameEventRequest(
                event_type=GameEventType.NEW_AREA_DISCOVERED,
                cell_x=18,
                cell_y=9,
            ),
            event_context=EventContext(
                progression_stage="Hardmode Unlocked",
                biomes=["Jungle"],
                layer="Cavern",
                mini_biomes=[],
                special_areas=["Jungle Temple"],
                previous_biomes=["Jungle"],
                previous_layer="Cavern",
                previous_mini_biomes=[],
                previous_special_areas=[],
            ),
        )

        decision_input = DecisionInput.from_trigger(trigger)

        self.assertEqual(
            {"cell_x": 18, "cell_y": 9},
            decision_input.game_event.payload,
        )
        self.assertEqual(
            ["Jungle Temple"],
            decision_input.event_context.special_areas,
        )

    def test_scene_feature_subject_is_mapped_to_payload(self) -> None:
        trigger = TriggerRequest(
            trigger_type=TriggerType.GAME_EVENT,
            timestamp=datetime.now(timezone.utc),
            priority=TriggerPriority.NORMAL,
            vitals=calm_vitals(),
            game_event=GameEventRequest(
                event_type=GameEventType.SCENE_FEATURE_ENTERED,
                subject_id="MINI_BIOME",
                subject_name="Bee Hive",
            ),
            event_context=EventContext(
                biomes=["Jungle"],
                layer="Cavern",
                mini_biomes=["Bee Hive"],
                special_areas=[],
            ),
        )

        decision_input = DecisionInput.from_trigger(trigger)

        self.assertEqual(
            {"feature_category": "MINI_BIOME", "feature_name": "Bee Hive"},
            decision_input.game_event.payload,
        )


class DecisionRouteTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_route_maps_decision_result_to_agent_response(self) -> None:
        app.dependency_overrides[get_decision_node] = lambda: DecisionNode(
            FakeDecisionModelClient()
        )

        with self.assertLogs("uvicorn.error", level="INFO") as captured_logs:
            with TestClient(app) as client:
                response = client.post(
                    "/agent/trigger",
                    json={
                        "triggerType": "USER_QUERY",
                        "timestamp": "2026-08-23T12:00:00Z",
                        "priority": "HIGH",
                        "vitals": {
                            "hpRatio": 1.0,
                            "hpDelta": 0.0,
                            "inCombat": False,
                        },
                        "userQuery": "我下一步应该干什么？",
                        "gameEvent": None,
                        "periodicSummary": None,
                    },
                )

        self.assertEqual(200, response.status_code)
        self.assertEqual("REASON", response.json()["action"])
        self.assertEqual("用户问题需要对应处理路径", response.json()["decisionReason"])
        self.assertTrue(response.json()["success"])
        logs = "\n".join(captured_logs.output)
        self.assertIn("trigger=USER_QUERY", logs)
        self.assertIn("query: 我下一步应该干什么？", logs)
        self.assertIn("action: REASON", logs)
        self.assertIn("model: fake-model", logs)

    def test_model_failure_returns_error_response(self) -> None:
        app.dependency_overrides[get_decision_node] = lambda: DecisionNode(
            FailingDecisionModelClient()
        )

        with TestClient(app) as client:
            response = client.post(
                "/agent/trigger",
                json={
                    "triggerType": "USER_QUERY",
                    "timestamp": "2026-08-23T12:00:00Z",
                    "priority": "HIGH",
                    "vitals": {
                        "hpRatio": 1.0,
                        "hpDelta": 0.0,
                        "inCombat": False,
                    },
                    "userQuery": "你好",
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json()["success"])
        self.assertIn("Decision 模型调用失败", response.json()["error"])

    def test_route_accepts_camel_case_game_event_context(self) -> None:
        app.dependency_overrides[get_decision_node] = lambda: DecisionNode(
            FakeDecisionModelClient()
        )

        with TestClient(app) as client:
            response = client.post(
                "/agent/trigger",
                json={
                    "triggerType": "GAME_EVENT",
                    "timestamp": "2026-08-23T12:00:00Z",
                    "priority": "NORMAL",
                    "vitals": {
                        "hpRatio": 0.8,
                        "hpDelta": -0.02,
                        "inCombat": True,
                    },
                    "gameEvent": {
                        "eventType": "WorldEventStarted",
                        "subjectId": "BloodMoon",
                        "subjectName": "Blood Moon",
                    },
                    "eventContext": {
                        "occurrenceCount": 0,
                        "activeEvents": ["BloodMoon", "PirateInvasion"],
                    },
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("IGNORE", response.json()["action"])
        self.assertTrue(response.json()["success"])

    def test_route_accepts_new_area_scene_collections(self) -> None:
        app.dependency_overrides[get_decision_node] = lambda: DecisionNode(
            FakeDecisionModelClient()
        )

        with TestClient(app) as client:
            response = client.post(
                "/agent/trigger",
                json={
                    "triggerType": "GAME_EVENT",
                    "timestamp": "2026-08-23T12:00:00Z",
                    "priority": "NORMAL",
                    "vitals": {
                        "hpRatio": 0.8,
                        "hpDelta": 0.0,
                        "inCombat": False,
                    },
                    "gameEvent": {
                        "eventType": "NewAreaDiscovered",
                        "cellX": 18,
                        "cellY": 9,
                    },
                    "eventContext": {
                        "progressionStage": "Hardmode Unlocked",
                        "biomes": ["Jungle"],
                        "layer": "Cavern",
                        "miniBiomes": [],
                        "specialAreas": ["Jungle Temple"],
                        "previousBiomes": ["Jungle"],
                        "previousLayer": "Cavern",
                        "previousMiniBiomes": [],
                        "previousSpecialAreas": [],
                    },
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("IGNORE", response.json()["action"])
        self.assertTrue(response.json()["success"])

    def test_all_trigger_types_route_large_hp_drop_directly_to_reason(self) -> None:
        app.dependency_overrides[get_decision_node] = lambda: DecisionNode(
            UnexpectedCallDecisionModelClient()
        )

        with TestClient(app) as client:
            requests = [
                user_query_request(hp_delta=-0.10),
                game_event_request(hp_delta=-0.15),
                periodic_request(hp_ratio=0.55, hp_delta=-0.25),
            ]
            for request in requests:
                response = client.post("/agent/trigger", json=request)

                with self.subTest(trigger_type=request["triggerType"]):
                    self.assertEqual(200, response.status_code)
                    self.assertEqual("REASON", response.json()["action"])
                    self.assertIn("近期明显掉血", response.json()["decisionReason"])

    def test_periodic_healing_and_small_drop_continue_to_model(self) -> None:
        app.dependency_overrides[get_decision_node] = lambda: DecisionNode(
            FakeDecisionModelClient()
        )

        with TestClient(app) as client:
            healing_response = client.post(
                "/agent/trigger",
                json=periodic_request(hp_ratio=0.80, hp_delta=0.30),
            )
            small_drop_response = client.post(
                "/agent/trigger",
                json=periodic_request(hp_ratio=0.55, hp_delta=-0.03),
            )

        self.assertEqual("IGNORE", healing_response.json()["action"])
        self.assertEqual("IGNORE", small_drop_response.json()["action"])

    def test_small_hp_drop_does_not_prevent_model_reason(self) -> None:
        app.dependency_overrides[get_decision_node] = lambda: DecisionNode(
            FakeDecisionModelClient()
        )

        with TestClient(app) as client:
            response = client.post(
                "/agent/trigger",
                json=user_query_request(hp_delta=-0.07),
            )

        self.assertEqual("REASON", response.json()["action"])
        self.assertEqual("用户问题需要对应处理路径", response.json()["decisionReason"])


def user_query_request(*, hp_delta: float) -> dict[str, object]:
    return {
        "triggerType": "USER_QUERY",
        "timestamp": "2026-08-23T12:00:00Z",
        "priority": "HIGH",
        "vitals": {
            "hpRatio": 0.55,
            "hpDelta": hp_delta,
            "inCombat": True,
        },
        "userQuery": "我下一步应该干什么？",
    }


def game_event_request(*, hp_delta: float) -> dict[str, object]:
    return {
        "triggerType": "GAME_EVENT",
        "timestamp": "2026-08-23T12:00:00Z",
        "priority": "NORMAL",
        "vitals": {
            "hpRatio": 0.55,
            "hpDelta": hp_delta,
            "inCombat": True,
        },
        "gameEvent": {
            "eventType": "BossSpawned",
            "subjectId": "35",
            "subjectName": "Skeletron",
        },
        "eventContext": {"nearbyEnemyCount": 2},
    }


def periodic_request(*, hp_ratio: float, hp_delta: float) -> dict[str, object]:
    return {
        "triggerType": "PERIODIC",
        "timestamp": "2026-08-23T12:00:00Z",
        "priority": "LOW",
        "vitals": {
            "hpRatio": hp_ratio,
            "hpDelta": hp_delta,
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
