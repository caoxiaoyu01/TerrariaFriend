import unittest

from agent.decision.schema import DecisionInput
from agent.models.trigger import TriggerRequest
from agent.reasoning.graph import MAX_REASONING_ROUNDS, MAX_TOOL_CALLS, ReasoningGraph
from agent.reasoning.reasoner import Reasoner
from tests.fakes import ScriptedRoleLLMClient, user_query_json


def reasoning_input() -> tuple[TriggerRequest, DecisionInput]:
    trigger = TriggerRequest.model_validate(user_query_json())
    return trigger, DecisionInput.from_trigger(trigger)


class ReasoningGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_collects_tools_across_multiple_rounds_then_final(self) -> None:
        client = ScriptedRoleLLMClient(
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
                {"status": "FINAL", "answer": "先整理装备，再继续探索丛林。"},
            ],
            role="reasoning",
            enable_thinking=True,
        )
        graph = ReasoningGraph(Reasoner(client))
        trigger, decision_input = reasoning_input()

        answer = await graph.run(trigger, decision_input, "需要规划下一步")

        self.assertEqual("先整理装备，再继续探索丛林。", answer)
        self.assertEqual(3, len(client.inputs))
        self.assertIn("progress", client.inputs[1]["collected_context"])
        final_context = client.inputs[2]["collected_context"]
        self.assertEqual({"progress", "inventory", "scene"}, set(final_context))
        self.assertNotIn("game_snapshot", client.inputs[2])

    async def test_health_risk_selects_combat_and_inventory(self) -> None:
        client = ScriptedRoleLLMClient(
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
                    "answer": "附近有敌人且刚受到伤害，先拉开距离并使用治疗药水。",
                },
            ],
            role="reasoning",
            enable_thinking=True,
        )
        graph = ReasoningGraph(Reasoner(client))
        trigger, decision_input = reasoning_input()

        answer = await graph.run(trigger, decision_input, "玩家近期明显掉血")

        self.assertIn("治疗药水", answer)
        context = client.inputs[1]["collected_context"]
        self.assertEqual({"combat", "inventory"}, set(context))
        self.assertEqual("Hornet", context["combat"]["recentDamage"]["lastDamageSource"])

    async def test_duplicate_tool_call_reuses_existing_result(self) -> None:
        client = ScriptedRoleLLMClient(
            [
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {"name": "get_inventory_context", "arguments": {}}
                    ],
                },
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {"name": "get_inventory_context", "arguments": {}}
                    ],
                },
                {"status": "FINAL", "answer": "现有背包信息已经足够。"},
            ],
            role="reasoning",
        )
        graph = ReasoningGraph(Reasoner(client))
        trigger, decision_input = reasoning_input()

        await graph.run(trigger, decision_input, "测试去重")

        history = client.inputs[2]["tool_history"]
        self.assertEqual("success", history[0]["status"])
        self.assertEqual("reused", history[1]["status"])
        self.assertEqual(MAX_TOOL_CALLS - 1, client.inputs[2]["limits"]["remaining_tool_calls"])

    async def test_tool_error_returns_observation_to_reasoner(self) -> None:
        client = ScriptedRoleLLMClient(
            [
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {
                            "name": "get_player_context",
                            "arguments": {"unexpected": True},
                        }
                    ],
                },
                {"status": "FINAL", "answer": "当前信息不足，请先确保安全。"},
            ],
            role="reasoning",
        )
        graph = ReasoningGraph(Reasoner(client))
        trigger, decision_input = reasoning_input()

        answer = await graph.run(trigger, decision_input, "测试工具错误")

        self.assertIn("信息不足", answer)
        errors = client.inputs[1]["collected_context"]["tool_errors"]
        self.assertEqual("get_player_context", errors[0]["tool"])

    async def test_failed_duplicate_tool_call_is_not_executed_again(self) -> None:
        bad_call = {
            "status": "NEED_TOOL",
            "tool_calls": [
                {
                    "name": "get_player_context",
                    "arguments": {"unexpected": True},
                }
            ],
        }
        client = ScriptedRoleLLMClient(
            [
                bad_call,
                bad_call,
                {"status": "FINAL", "answer": "使用已有错误信息结束。"},
            ],
            role="reasoning",
        )
        graph = ReasoningGraph(Reasoner(client))
        trigger, decision_input = reasoning_input()

        await graph.run(trigger, decision_input, "测试失败调用去重")

        history = client.inputs[2]["tool_history"]
        self.assertEqual("error", history[0]["status"])
        self.assertEqual("reused", history[1]["status"])
        self.assertEqual("error", history[1]["original_status"])
        self.assertEqual(MAX_TOOL_CALLS - 1, client.inputs[2]["limits"]["remaining_tool_calls"])

    async def test_invalid_json_is_repaired_once(self) -> None:
        client = ScriptedRoleLLMClient(
            [
                "not-json",
                {"status": "FINAL", "answer": "修复成功。"},
            ],
            role="reasoning",
        )
        graph = ReasoningGraph(Reasoner(client))
        trigger, decision_input = reasoning_input()

        answer = await graph.run(trigger, decision_input, "测试 JSON repair")

        self.assertEqual("修复成功。", answer)
        self.assertEqual(2, len(client.inputs))
        self.assertIn("repair_instruction", client.inputs[1])

    async def test_tool_call_limit_forces_next_round_final(self) -> None:
        client = ScriptedRoleLLMClient(
            [
                {
                    "status": "NEED_TOOL",
                    "tool_calls": [
                        {"name": "get_player_context", "arguments": {}},
                        {"name": "get_combat_context", "arguments": {}},
                        {"name": "get_inventory_context", "arguments": {}},
                        {"name": "get_progress_context", "arguments": {}},
                        {"name": "get_scene_context", "arguments": {}},
                    ],
                },
                {"status": "FINAL", "answer": "根据已获取的信息给出建议。"},
            ],
            role="reasoning",
        )
        graph = ReasoningGraph(Reasoner(client))
        trigger, decision_input = reasoning_input()

        await graph.run(trigger, decision_input, "测试工具上限")

        self.assertEqual(0, client.inputs[1]["limits"]["remaining_tool_calls"])
        self.assertTrue(client.inputs[1]["limits"]["must_return_final"])
        self.assertEqual(MAX_TOOL_CALLS, len(client.inputs[1]["collected_context"]))

    async def test_reasoning_round_limit_prevents_loop(self) -> None:
        repeated_call = {
            "status": "NEED_TOOL",
            "tool_calls": [{"name": "get_scene_context", "arguments": {}}],
        }
        client = ScriptedRoleLLMClient(
            [repeated_call for _ in range(MAX_REASONING_ROUNDS)],
            role="reasoning",
        )
        graph = ReasoningGraph(Reasoner(client))
        trigger, decision_input = reasoning_input()

        answer = await graph.run(trigger, decision_input, "测试轮次上限")

        self.assertIn("无法完全确定", answer)
        self.assertEqual(MAX_REASONING_ROUNDS, len(client.inputs))
