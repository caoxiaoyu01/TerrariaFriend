import unittest

from agent.decision.schema import DecisionInput
from agent.models.trigger import TriggerRequest
from agent.reasoning.schema import GameContextToolName
from agent.reasoning.tools import GameContextTools, ToolExecutor
from agent.response.generator import RESPONSE_FALLBACK, ResponseGenerator
from tests.fakes import ScriptedRoleLLMClient, user_query_json


class RecordingRegistry(GameContextTools):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[GameContextToolName] = []

    def execute(self, name, arguments, snapshot):
        self.calls.append(name)
        return super().execute(name, arguments, snapshot)


class ResponseGeneratorTests(unittest.IsolatedAsyncioTestCase):
    def _input(self, query: str = "你好") -> tuple[TriggerRequest, DecisionInput]:
        trigger = TriggerRequest.model_validate(user_query_json(query=query))
        return trigger, DecisionInput.from_trigger(trigger)

    async def test_generates_one_direct_response_without_tools(self) -> None:
        client = ScriptedRoleLLMClient(
            [{"status": "FINAL", "answer": "你好，我会陪你一起探索。"}],
            role="response",
        )
        generator = ResponseGenerator(client)
        trigger, decision_input = self._input()

        response = await generator.generate(
            decision_input,
            "简单问候不需要额外信息",
            trigger.game_snapshot,
        )

        self.assertEqual("你好，我会陪你一起探索。", response)
        self.assertEqual(1, len(client.inputs))
        self.assertEqual("你好", client.inputs[0]["trigger"]["user_query"])
        self.assertEqual(1, client.inputs[0]["limits"]["remaining_tool_calls"])

    async def test_executes_one_allowed_tool_then_returns_final(self) -> None:
        client = ScriptedRoleLLMClient(
            [
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {
                            "name": "get_scene_context",
                            "arguments": {},
                        }
                    ],
                },
                {"status": "FINAL", "answer": "你正在丛林地表，可以继续谨慎探索。"},
            ],
            role="response",
        )
        registry = RecordingRegistry()
        generator = ResponseGenerator(
            client,
            tool_executor=ToolExecutor(registry),
        )
        trigger, decision_input = self._input("我现在在哪里？")

        response = await generator.generate(
            decision_input,
            "只缺少当前位置",
            trigger.game_snapshot,
        )

        self.assertIn("丛林", response)
        self.assertEqual([GameContextToolName.GET_SCENE_CONTEXT], registry.calls)
        self.assertEqual(2, len(client.inputs))
        self.assertEqual(
            "get_scene_context",
            client.inputs[1]["tool_observation"]["name"],
        )
        self.assertEqual(0, client.inputs[1]["limits"]["remaining_tool_calls"])
        self.assertTrue(client.inputs[1]["limits"]["must_return_final"])

    async def test_does_not_execute_second_tool_request(self) -> None:
        client = ScriptedRoleLLMClient(
            [
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {
                            "name": "get_scene_context",
                            "arguments": {},
                        }
                    ],
                },
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {
                            "name": "get_player_context",
                            "arguments": {},
                        }
                    ],
                },
            ],
            role="response",
        )
        registry = RecordingRegistry()
        generator = ResponseGenerator(
            client,
            tool_executor=ToolExecutor(registry),
        )
        trigger, decision_input = self._input("我现在在哪里？")

        response = await generator.generate(
            decision_input,
            "只缺少当前位置",
            trigger.game_snapshot,
        )

        self.assertEqual(RESPONSE_FALLBACK, response)
        self.assertEqual([GameContextToolName.GET_SCENE_CONTEXT], registry.calls)
        self.assertEqual(2, len(client.inputs))

    async def test_denied_tool_returns_fallback_without_execution(self) -> None:
        client = ScriptedRoleLLMClient(
            [
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {
                            "name": "get_inventory_context",
                            "arguments": {},
                        }
                    ],
                }
            ],
            role="response",
        )
        registry = RecordingRegistry()
        generator = ResponseGenerator(
            client,
            tool_executor=ToolExecutor(registry),
        )
        trigger, decision_input = self._input("我背包里有什么？")

        response = await generator.generate(
            decision_input,
            "轻量回复路径",
            trigger.game_snapshot,
        )

        self.assertEqual(RESPONSE_FALLBACK, response)
        self.assertEqual([], registry.calls)
        self.assertEqual(1, len(client.inputs))
