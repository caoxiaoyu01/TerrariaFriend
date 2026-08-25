import unittest
from copy import deepcopy

from agent.decision.schema import DecisionAction
from agent.models.game_snapshot import GameSnapshot
from agent.reasoning import reasoner as reasoner_module
from agent.reasoning.schema import GameContextToolName
from agent.reasoning.tool_policy import ToolPolicy
from agent.reasoning.tools import ToolExecutor
from agent.response import generator as response_module
from tests.fakes import game_snapshot_payload


class ToolArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ToolPolicy()

    def test_respond_allows_scene_context(self) -> None:
        self.assertTrue(
            self.policy.is_allowed(
                DecisionAction.RESPOND,
                GameContextToolName.GET_SCENE_CONTEXT,
            )
        )

    def test_respond_denies_inventory_context(self) -> None:
        self.assertFalse(
            self.policy.is_allowed(
                DecisionAction.RESPOND,
                GameContextToolName.GET_INVENTORY_CONTEXT,
            )
        )

    def test_reason_allows_inventory_context(self) -> None:
        self.assertTrue(
            self.policy.is_allowed(
                DecisionAction.REASON,
                GameContextToolName.GET_INVENTORY_CONTEXT,
            )
        )

    def test_respond_allows_world_context(self) -> None:
        self.assertTrue(
            self.policy.is_allowed(
                DecisionAction.RESPOND,
                GameContextToolName.GET_WORLD_CONTEXT,
            )
        )

    def test_reason_allows_world_context(self) -> None:
        self.assertTrue(
            self.policy.is_allowed(
                DecisionAction.REASON,
                GameContextToolName.GET_WORLD_CONTEXT,
            )
        )

    def test_response_and_reasoner_share_tool_definitions(self) -> None:
        self.assertIs(
            response_module.TOOL_DESCRIPTIONS,
            reasoner_module.TOOL_DESCRIPTIONS,
        )


class WorldContextToolTests(unittest.TestCase):
    def setUp(self) -> None:
        payload = deepcopy(game_snapshot_payload())
        payload["world"] = {
            "time": {
                "isDay": False,
                "timeOfDay": "21:30",
                "moonPhase": "Full Moon",
            },
            "weather": {
                "isRaining": True,
                "rainIntensity": 0.75,
                "windSpeed": 0.1,
                "isSandstorm": False,
            },
            "activeEvents": [
                {
                    "id": "BloodMoon",
                    "name": "Blood Moon",
                    "category": "Combat",
                    "progress": None,
                }
            ],
        }
        snapshot = GameSnapshot.model_validate(payload)
        _, self.world = ToolExecutor().execute(
            DecisionAction.REASON,
            GameContextToolName.GET_WORLD_CONTEXT,
            {},
            snapshot,
        )

    def test_returns_world_sections(self) -> None:
        self.assertEqual({"time", "weather", "activeEvents"}, set(self.world))

    def test_returns_time_and_weather_fields(self) -> None:
        self.assertEqual(
            {
                "isDay": False,
                "timeOfDay": "21:30",
                "moonPhase": "Full Moon",
            },
            self.world["time"],
        )
        self.assertEqual(
            {
                "isRaining": True,
                "rainIntensity": 0.75,
                "windSpeed": 0.1,
                "isSandstorm": False,
            },
            self.world["weather"],
        )

    def test_returns_active_events_without_changing_null_progress(self) -> None:
        self.assertEqual(
            [
                {
                    "id": "BloodMoon",
                    "name": "Blood Moon",
                    "category": "Combat",
                    "progress": None,
                }
            ],
            self.world["activeEvents"],
        )
