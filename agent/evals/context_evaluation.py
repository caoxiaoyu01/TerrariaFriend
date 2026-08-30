import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.decision.schema import DecisionAction
from agent.llm.client import OpenAICompatibleClient, RoleLLMClient
from agent.llm.config import AgentLLMSettings
from agent.mcp_servers.terraria_wiki.retrieval_service import WikiRetrievalService
from agent.memory.retrieval import MemoryContextResult
from agent.models.game_snapshot import GameSnapshot
from agent.reasoning.reasoner import Reasoner
from agent.reasoning.schema import ReasonerStatus
from agent.reasoning.tools import ToolExecutor, tool_signature


logger = logging.getLogger("context-evaluation")


@dataclass(frozen=True, slots=True)
class ExpectedCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    category: str
    query: str
    expected_calls: tuple[ExpectedCall, ...]
    expected_fact_groups: tuple[tuple[str, ...], ...]
    forbidden_tools: tuple[str, ...] = ()
    retrieval_mode: str = "production"
    retrieval_fact_groups: tuple[tuple[str, ...], ...] | None = None


@dataclass(slots=True)
class CallRecord:
    round: int
    name: str
    arguments: dict[str, Any]
    source_key: str | None
    context_chars: int
    estimated_context_tokens: int
    latency_ms: float
    error: str | None = None


@dataclass(slots=True)
class CaseResult:
    case_id: str
    category: str
    query: str
    retrieval_mode: str
    expected_tools: list[str]
    selected_tools: list[str]
    retrieval_passed: bool
    tool_selection_passed: bool
    answer_support_passed: bool
    duplicate_calls: int
    stale_or_conflict: bool
    prompt_tokens: int
    completion_tokens: int
    final_answer: str
    calls: list[dict[str, Any]]
    errors: list[str]

    @property
    def passed(self) -> bool:
        return (
            self.retrieval_passed
            and self.tool_selection_passed
            and self.answer_support_passed
            and self.duplicate_calls == 0
            and not self.stale_or_conflict
            and not self.errors
        )


class RecordingRoleClient:
    def __init__(self, client: RoleLLMClient) -> None:
        self._client = client
        self.config = client.config
        self.completions = []

    @property
    def model_name(self) -> str:
        return self._client.model_name

    async def generate_structured(self, **kwargs):
        completion = await self._client.generate_structured(**kwargs)
        self.completions.append(completion)
        return completion


class EvaluationWikiClient:
    def __init__(self, service: WikiRetrievalService) -> None:
        self.service = service

    async def lookup_terraria_knowledge(
        self,
        entity: str,
        intent: str = "general",
        lang: str = "zh",
    ) -> dict[str, Any]:
        result = await self.service.lookup(entity, intent, lang)
        return result.model_dump(mode="json")


class EvaluationMemoryTool:
    async def get_memory_context(
        self,
        query: str,
        scope: str = "recent",
    ) -> MemoryContextResult:
        normalized = query.casefold()
        recent = []
        long_term = []
        if scope in {"recent", "both"}:
            recent = [
                {
                    "score": 0.94,
                    "episode_id": "eval-recent-hive",
                    "episode_type": "conversation",
                    "started_at": "2026-08-30T12:00:00Z",
                    "primary_entity": "Bee Hive",
                    "events": [
                        {"type": "USER_QUERY", "content": "我上次在蜂巢做了什么"},
                        {"type": "AGENT_RESPONSE", "content": "你在蜂巢搭建了战斗平台"},
                    ],
                },
                {
                    "score": 0.91,
                    "episode_id": "eval-recent-queen-bee",
                    "episode_type": "event",
                    "started_at": "2026-08-30T12:10:00Z",
                    "primary_entity": "Queen Bee",
                    "events": [
                        {"type": "BossEnded", "content": "蜂王挑战失败"},
                    ],
                },
                {
                    "score": 0.88,
                    "episode_id": "eval-recent-bee-gun",
                    "episode_type": "conversation",
                    "started_at": "2026-08-30T12:20:00Z",
                    "primary_entity": "Bee Gun",
                    "events": [
                        {"type": "USER_QUERY", "content": "蜜蜂枪有什么用"},
                    ],
                },
                {
                    "score": 0.86,
                    "episode_id": "eval-recent-minishark",
                    "episode_type": "event",
                    "started_at": "2026-08-30T12:30:00Z",
                    "primary_entity": "Minishark",
                    "events": [
                        {"type": "EquipmentChanged", "content": "玩家换上了迷你鲨"},
                    ],
                },
            ]
            recent = [item for item in recent if _memory_item_matches(item, normalized)]
        if scope in {"long_term", "both"}:
            long_term = [
                {
                    "subject": "Player",
                    "relation": "DEFEATED",
                    "object": "Queen Bee",
                    "evidence_episode_ids": ["eval-defeated-queen-bee"],
                    "relevance_score": 0.96,
                },
                {
                    "subject": "Player",
                    "relation": "VISITED",
                    "object": "Bee Hive",
                    "evidence_episode_ids": ["eval-visited-hive"],
                    "relevance_score": 0.93,
                },
                {
                    "subject": "Player",
                    "relation": "PREFERS",
                    "object": "Ranged Combat",
                    "evidence_episode_ids": ["eval-prefers-ranged"],
                    "relevance_score": 0.90,
                },
                {
                    "subject": "Player",
                    "relation": "FAILED_AGAINST",
                    "object": "Skeletron",
                    "evidence_episode_ids": ["eval-failed-skeletron"],
                    "relevance_score": 0.89,
                },
            ]
            long_term = [item for item in long_term if _memory_item_matches(item, normalized)]
        return MemoryContextResult.model_validate(
            {"recent_memory": recent, "long_term_memory": long_term}
        )


def _memory_item_matches(item: dict[str, Any], query: str) -> bool:
    text = json.dumps(item, ensure_ascii=False).casefold()
    keyword_groups = {
        "蜂巢": ("蜂巢", "hive"),
        "蜂王": ("蜂王", "queen bee", "boss"),
        "蜜蜂枪": ("蜜蜂枪", "bee gun"),
        "迷你鲨": ("迷你鲨", "minishark", "装备"),
        "击败": ("击败", "打过", "defeated", "boss"),
        "远程": ("远程", "ranged", "偏好"),
        "骷髅王": ("骷髅王", "skeletron", "失败"),
    }
    matched = [terms for key, terms in keyword_groups.items() if key in query]
    if not matched:
        return True
    return any(any(term in text for term in terms) for terms in matched)


# 伪造 GameSnapshot 
def _base_snapshot() -> GameSnapshot:
    return GameSnapshot.model_validate(
        {
            "tick": 3600,
            "player": {
                "playerId": 0,
                "name": "Player",
                "isDead": False,
                "life": 400,
                "maxLife": 400,
                "mana": 180,
                "maxMana": 200,
                "defense": 42,
                "positionTileX": 120.0,
                "positionTileY": 300.0,
                "velocityTilesPerSecondX": 0.0,
                "velocityTilesPerSecondY": 0.0,
                "direction": 1,
                "isMounted": True,
                "mount": {"typeId": 4, "buffTypeId": 90, "name": "海龟坐骑"},
                "breath": 200,
                "maxBreath": 200,
                "heldItem": {"typeId": 273, "name": "永夜刃", "stack": 1},
                "buffs": [
                    {"typeId": 5, "name": "铁皮", "isDebuff": False, "remainingTicks": 18000},
                    {"typeId": 20, "name": "中毒", "isDebuff": True, "remainingTicks": 300},
                ],
            },
            "inventory": {
                "hotbar": [],
                "armor": {
                    "head": {"typeId": 231, "name": "熔岩头盔", "stack": 1},
                    "body": {"typeId": 232, "name": "熔岩胸甲", "stack": 1},
                    "legs": {"typeId": 233, "name": "熔岩护胫", "stack": 1},
                },
                "accessories": [{"typeId": 399, "name": "黑曜石盾", "stack": 1}],
                "healing": {
                    "totalHealingItemCount": 8,
                    "bestHealingItem": {"typeId": 499, "name": "强效治疗药水", "stack": 8},
                    "bestHealingAmount": 150,
                },
                "mana": {"totalManaItemCount": 3, "bestManaItem": {"typeId": 500, "name": "强效魔力药水", "stack": 3}, "bestManaAmount": 200},
                "bossSummons": [{"typeId": 43, "name": "可疑眼球", "stack": 1}],
                "freeSlots": 7,
            },
            "world": {
                "time": {"isDay": False, "timeOfDay": "21:30", "moonPhase": "Full Moon"},
                "weather": {"isRaining": True, "rainIntensity": 0.75, "windSpeed": 0.1, "isSandstorm": False},
                "activeEvents": [{"id": "BloodMoon", "name": "Blood Moon", "category": "Combat", "progress": None}],
            },
            "progress": {
                "defeatedBosses": ["Eye of Cthulhu", "Queen Bee"],
                "worldMilestones": [],
                "currentStage": {"id": "pre_hardmode", "name": "Pre-Hardmode"},
                "visitedRegions": ["Jungle", "Desert", "Ocean"],
            },
            "scene": {
                "biomes": ["Jungle"],
                "layer": "Surface",
                "miniBiomes": ["Bee Hive"],
                "specialAreas": [],
                "nearbyBuffs": [],
            },
            "combat": {
                "inCombat": True,
                "combatDurationSeconds": 4.2,
                "bossActive": True,
                "activeBosses": [{"typeId": 222, "name": "Queen Bee", "life": 1200, "maxLife": 3400}],
                "nearbyEnemyCount": 3,
                "hpRatio": 1.0,
                "recentDamage": {"damageTakenLast5s": 25, "lastDamageAmount": 12, "lastDamageSource": "Hornet", "timeSinceLastDamageSeconds": 0.5},
            },
            "npc": {"townNpcCount": 0, "townNpcs": [], "nearbyTownNpcCount": 0, "nearbyTownNpcs": [], "specialNpcCount": 0, "specialNpcs": [], "bossActive": True, "activeBossCount": 1, "activeBosses": []},
        }
    )


def _c(
    case_id: str,
    category: str,
    query: str,
    calls: tuple[tuple[str, dict[str, Any]], ...],
    *fact_groups: tuple[str, ...],
    forbidden: tuple[str, ...] = (),
    retrieval_mode: str = "production",
    retrieval_facts: tuple[tuple[str, ...], ...] | None = None,
) -> EvaluationCase:
    return EvaluationCase(
        case_id,
        category,
        query,
        tuple(ExpectedCall(name, arguments) for name, arguments in calls),
        fact_groups,
        forbidden,
        retrieval_mode,
        retrieval_facts,
    )


# 造测试用例：问题、预期使用工具、预期答案
def evaluation_cases() -> tuple[EvaluationCase, ...]:
    empty: dict[str, Any] = {}
    return (
        _c("G01", "player", "我现在多少血", (("get_player_context", empty),), ("400",)),
        _c("G02", "player", "我现在有多少魔力", (("get_player_context", empty),), ("180",)),
        _c("G03", "player", "我现在防御多少", (("get_player_context", empty),), ("42",)),
        _c("G04", "player", "我现在拿着什么", (("get_player_context", empty),), ("永夜刃",)),
        _c("G05", "player", "我现在骑的是什么", (("get_player_context", empty),), ("海龟坐骑",)),
        _c("G06", "player", "我现在有什么增益", (("get_player_context", empty),), ("铁皮",)),
        _c("G07", "player", "我中了什么减益", (("get_player_context", empty),), ("中毒",)),
        _c("G08", "combat", "附近有多少敌人", (("get_combat_context", empty),), ("3",)),
        _c("G09", "combat", "现在正在打哪个 Boss", (("get_combat_context", empty),), ("蜂王", "Queen Bee")),
        _c("G10", "combat", "刚才是谁打了我", (("get_combat_context", empty),), ("黄蜂", "Hornet")),
        _c("G11", "scene", "我现在在哪个群系", (("get_scene_context", empty),), ("丛林", "Jungle")),
        _c("G12", "scene", "我现在是不是在蜂巢", (("get_scene_context", empty),), ("蜂巢", "Bee Hive")),
        _c("G13", "scene", "我现在位于地表还是地下", (("get_scene_context", empty),), ("地表", "Surface")),
        _c("G14", "world", "现在下雨吗", (("get_world_context", empty),), ("下雨", "正在下雨"), retrieval_facts=(("isRaining",), ("true",))),
        _c("G15", "world", "现在几点", (("get_world_context", empty),), ("21:30",)),
        _c("G16", "world", "现在有什么世界事件", (("get_world_context", empty),), ("血月", "Blood Moon")),
        _c("G17", "inventory", "我最好的治疗药是什么", (("get_inventory_context", empty),), ("强效治疗药水",)),
        _c("G18", "inventory", "我穿着什么盔甲", (("get_inventory_context", empty),), ("熔岩",)),
        _c("G19", "inventory", "我装备了什么饰品", (("get_inventory_context", empty),), ("黑曜石盾",)),
        _c("G20", "inventory", "我有 Boss 召唤物吗", (("get_inventory_context", empty),), ("可疑眼球",)),
        _c("G21", "inventory", "背包还有多少空位", (("get_inventory_context", empty),), ("7",)),
        _c("G22", "progress", "这个世界击败过哪些 Boss", (("get_progress_context", empty),), ("克苏鲁之眼", "Eye of Cthulhu"), ("蜂王", "Queen Bee")),
        _c("G23", "progress", "这个世界现在是什么阶段", (("get_progress_context", empty),), ("困难模式前", "Pre-Hardmode")),
        _c("G24", "progress", "这个世界去过哪些区域", (("get_progress_context", empty),), ("丛林", "Jungle"), ("沙漠", "Desert"), ("海洋", "Ocean")),
        _c("G25", "mixed", "我现在适合继续打蜂王吗", (("get_combat_context", empty), ("get_player_context", empty), ("get_inventory_context", empty)), ("蜂王", "Queen Bee"), ("400", "满血", "生命全满")),
        _c("W01", "wiki", "蜂王掉什么", (("lookup_terraria_knowledge", {"entity": "蜂王", "intent": "drops", "lang": "zh"}),), ("蜂蜡",)),
        _c("W02", "wiki", "蜂王怎么召唤", (("lookup_terraria_knowledge", {"entity": "蜂王", "intent": "summoning", "lang": "zh"}),), ("幼虫", "憎恶之蜂")),
        _c("W03", "wiki", "魔镜有什么用", (("lookup_terraria_knowledge", {"entity": "魔镜", "intent": "usage", "lang": "zh"}),), ("出生点", "重生点")),
        _c("W04", "wiki", "闪亮红气球在哪里获得", (("lookup_terraria_knowledge", {"entity": "闪亮红气球", "intent": "obtaining", "lang": "zh"}),), ("天域箱", "天空匣")),
        _c("W05", "wiki", "可疑眼球有什么用", (("lookup_terraria_knowledge", {"entity": "可疑眼球", "intent": "usage", "lang": "zh"}),), ("克苏鲁之眼",)),
        _c("W06", "wiki", "黑曜石皮药水有什么效果", (("lookup_terraria_knowledge", {"entity": "黑曜石皮药水", "intent": "usage", "lang": "zh"}),), ("熔岩",)),
        _c("W07", "wiki", "地狱熔炉在哪里", (("lookup_terraria_knowledge", {"entity": "地狱熔炉", "intent": "location", "lang": "zh"}),), ("地狱", "Underworld")),
        _c("W08", "wiki", "永夜刃怎么合成", (("lookup_terraria_knowledge", {"entity": "永夜刃", "intent": "crafting", "lang": "zh"}),), ("村正",), ("草剑",)),
        _c("W09", "wiki", "向导巫毒娃娃有什么用", (("lookup_terraria_knowledge", {"entity": "向导巫毒娃娃", "intent": "usage", "lang": "zh"}),), ("血肉墙", "肉山")),
        _c("W10", "wiki", "生命水晶有什么作用", (("lookup_terraria_knowledge", {"entity": "生命水晶", "intent": "usage", "lang": "zh"}),), ("生命",)),
        _c("W11", "wiki", "哥布林工匠在哪里出现", (("lookup_terraria_knowledge", {"entity": "哥布林工匠", "intent": "location", "lang": "zh"}),), ("洞穴", "地下")),
        _c("W12", "wiki", "工作台怎么制作", (("lookup_terraria_knowledge", {"entity": "工作台", "intent": "crafting", "lang": "zh"}),), ("木材", "木头")),
        _c("M01", "recent_memory", "我上次在蜂巢做了什么", (("get_memory_context", {"query": "玩家上次在蜂巢做了什么", "scope": "recent"}),), ("战斗平台",), retrieval_mode="fixture"),
        _c("M02", "recent_memory", "我上次挑战蜂王结果怎么样", (("get_memory_context", {"query": "玩家上次挑战蜂王的结果", "scope": "recent"}),), ("失败",), retrieval_mode="fixture"),
        _c("M03", "recent_memory", "我刚才问过蜜蜂枪吗", (("get_memory_context", {"query": "玩家近期是否问过蜜蜂枪", "scope": "recent"}),), ("蜜蜂枪",), retrieval_mode="fixture"),
        _c("M04", "recent_memory", "我最近换了什么武器", (("get_memory_context", {"query": "玩家最近更换的武器", "scope": "recent"}),), ("迷你鲨",), retrieval_mode="fixture"),
        _c("M05", "long_term_memory", "我以前击败过蜂王吗", (("get_memory_context", {"query": "玩家是否击败过蜂王", "scope": "long_term"}),), ("击败", "打败"), retrieval_mode="fixture", retrieval_facts=(("DEFEATED",), ("Queen Bee",))),
        _c("M06", "long_term_memory", "我以前去过蜂巢吗", (("get_memory_context", {"query": "玩家是否访问过蜂巢", "scope": "long_term"}),), ("去过", "访问过"), retrieval_mode="fixture", retrieval_facts=(("VISITED",), ("Bee Hive",))),
        _c("M07", "long_term_memory", "我长期更喜欢什么战斗方式", (("get_memory_context", {"query": "玩家长期战斗偏好", "scope": "long_term"}),), ("远程", "Ranged"), retrieval_mode="fixture"),
        _c("M08", "long_term_memory", "我以前输给过骷髅王吗", (("get_memory_context", {"query": "玩家对战骷髅王的历史结果", "scope": "long_term"}),), ("失败", "输过", "输给过"), retrieval_mode="fixture", retrieval_facts=(("FAILED_AGAINST",), ("Skeletron",))),
        _c("C01", "grounding", "龟有什么用", (("get_player_context", empty), ("lookup_terraria_knowledge", {"entity": "海龟坐骑", "intent": "usage", "lang": "zh"})), ("水",), forbidden=("get_memory_context",)),
        _c("C02", "grounding", "这把武器怎么合成", (("get_player_context", empty), ("lookup_terraria_knowledge", {"entity": "永夜刃", "intent": "crafting", "lang": "zh"})), ("村正",), forbidden=("get_memory_context",)),
        _c("C03", "grounding", "我身上的铁皮有什么作用", (("get_player_context", empty), ("lookup_terraria_knowledge", {"entity": "铁皮药水", "intent": "usage", "lang": "zh"})), ("防御",), forbidden=("get_memory_context",)),
        _c("C04", "freshness", "我现在还有多少血", (("get_player_context", empty),), ("400",), forbidden=("get_memory_context", "lookup_terraria_knowledge")),
        _c("C05", "source_boundary", "蜂王具体掉落什么", (("lookup_terraria_knowledge", {"entity": "蜂王", "intent": "drops", "lang": "zh"}),), ("蜂蜡",), forbidden=("get_memory_context",)),
    )


async def _retrieve_expected(
    case: EvaluationCase,
    executor: ToolExecutor,
    snapshot: GameSnapshot,
) -> tuple[dict[str, Any], list[CallRecord], list[str]]:
    context: dict[str, Any] = {}
    records: list[CallRecord] = []
    errors: list[str] = []
    for expected in case.expected_calls:
        started_at = time.perf_counter()
        try:
            source_key, result = await executor.execute_async(
                DecisionAction.REASON,
                expected.name,
                expected.arguments,
                snapshot,
            )
            context[source_key] = result
            records.append(_call_record(0, expected, source_key, result, started_at))
        except Exception as exception:
            errors.append(f"retrieval {expected.name}: {exception}")
    return context, records, errors


async def _run_orchestration(
    case: EvaluationCase,
    reasoner: Reasoner,
    recorder: RecordingRoleClient,
    executor: ToolExecutor,
    snapshot: GameSnapshot,
) -> tuple[str, list[CallRecord], list[str], int]:
    collected_context: dict[str, Any] = {}
    tool_history: list[dict[str, Any]] = []
    records: list[CallRecord] = []
    errors: list[str] = []
    answer = ""
    duplicate_calls = 0
    seen_signatures: set[str] = set()
    for round_number in range(1, 5):
        state = {
            "trigger": {},
            "query": case.query,
            "initial_context": {
                "trigger_type": "USER_QUERY",
                "priority": "HIGH",
                "timestamp": "2026-08-31T12:00:00Z",
                "vitals": {"hp_ratio": 1.0, "hp_delta": 0.0, "in_combat": True},
                "decision_reason": "评估复杂查询的信息收集",
                "user_query": case.query,
            },
            "game_snapshot": snapshot,
            "collected_context": collected_context,
            "tool_history": tool_history,
            "reasoning_messages": [],
            "pending_tool_calls": [],
            "last_status": None,
            "final_answer": None,
            "tool_call_count": len(records),
            "reasoning_round": round_number - 1,
            "reasoner_total_latency_seconds": 0.0,
            "run_metrics": None,
        }
        result = await reasoner.decide(
            state,
            round_number=round_number,
            remaining_tool_calls=max(4 - len(records), 0),
            force_final=round_number == 4,
        )
        if result.status is ReasonerStatus.FINAL:
            answer = result.answer or ""
            break
        for call in result.tool_calls:
            arguments = call.arguments_dict()
            signature = tool_signature(call.name, arguments)
            if signature in seen_signatures:
                duplicate_calls += 1
                continue
            seen_signatures.add(signature)
            started_at = time.perf_counter()
            try:
                source_key, tool_result = await executor.execute_async(
                    DecisionAction.REASON,
                    call.name,
                    arguments,
                    snapshot,
                )
                collected_context[source_key] = tool_result
                records.append(
                    _call_record(
                        round_number,
                        ExpectedCall(call.name, arguments),
                        source_key,
                        tool_result,
                        started_at,
                    )
                )
                tool_history.append(
                    {"name": call.name, "arguments": arguments, "signature": signature, "status": "success", "round": round_number}
                )
            except Exception as exception:
                errors.append(f"round {round_number} {call.name}: {exception}")
                tool_history.append(
                    {"name": call.name, "arguments": arguments, "signature": signature, "status": "error", "round": round_number, "error": str(exception)}
                )
    if not answer:
        errors.append("Reasoner 未在四轮内返回 FINAL")
    return answer, records, errors, duplicate_calls


def _call_record(
    round_number: int,
    call: ExpectedCall,
    source_key: str,
    result: Any,
    started_at: float,
) -> CallRecord:
    text = json.dumps(result, ensure_ascii=False, default=str, separators=(",", ":"))
    return CallRecord(
        round=round_number,
        name=call.name,
        arguments=call.arguments,
        source_key=source_key,
        context_chars=len(text),
        estimated_context_tokens=max(1, round(len(text) / 2)),
        latency_ms=(time.perf_counter() - started_at) * 1000,
    )


def _contains_fact_groups(value: Any, groups: tuple[tuple[str, ...], ...]) -> bool:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, default=str)
    ).casefold()
    return all(any(term.casefold() in text for term in group) for group in groups)


def _tool_selection_passed(case: EvaluationCase, records: list[CallRecord]) -> bool:
    selected = [record.name for record in records]
    expected = [call.name for call in case.expected_calls]
    return sorted(selected) == sorted(expected) and not any(
        name in case.forbidden_tools for name in selected
    )


def _detect_stale_or_conflict(case: EvaluationCase, answer: str) -> bool:
    if case.category == "freshness":
        return "100" in answer or "190" in answer
    return False


async def run_evaluation(
    output_dir: Path,
    cases: tuple[EvaluationCase, ...] | None = None,
) -> list[CaseResult]:
    settings = AgentLLMSettings.from_environment()
    shared_client = OpenAICompatibleClient(settings.provider)
    recorder = RecordingRoleClient(RoleLLMClient(shared_client, settings.reasoning))
    wiki_service = WikiRetrievalService()
    executor = ToolExecutor(
        wiki_client=EvaluationWikiClient(wiki_service),
        memory_tool=EvaluationMemoryTool(),
    )
    reasoner = Reasoner(
        recorder,
        available_tools=executor.available_tool_specs(DecisionAction.REASON),
    )
    snapshot = _base_snapshot()
    results: list[CaseResult] = []
    try:
        selected_cases = cases or evaluation_cases()
        for index, case in enumerate(selected_cases, start=1):
            before = len(recorder.completions)
            retrieval_context, retrieval_records, retrieval_errors = (
                await _retrieve_expected(case, executor, snapshot)
            )
            answer, orchestration_records, orchestration_errors, duplicates = (
                await _run_orchestration(
                    case,
                    reasoner,
                    recorder,
                    executor,
                    snapshot,
                )
            )
            completions = recorder.completions[before:]
            result = CaseResult(
                case_id=case.case_id,
                category=case.category,
                query=case.query,
                retrieval_mode=case.retrieval_mode,
                expected_tools=[call.name for call in case.expected_calls],
                selected_tools=[record.name for record in orchestration_records],
                retrieval_passed=(
                    not retrieval_errors
                    and _contains_fact_groups(
                        retrieval_context,
                        case.retrieval_fact_groups or case.expected_fact_groups,
                    )
                ),
                tool_selection_passed=_tool_selection_passed(
                    case,
                    orchestration_records,
                ),
                answer_support_passed=_contains_fact_groups(
                    answer,
                    case.expected_fact_groups,
                ),
                duplicate_calls=duplicates,
                stale_or_conflict=_detect_stale_or_conflict(case, answer),
                prompt_tokens=sum(
                    completion.usage.prompt_tokens or 0 for completion in completions
                ),
                completion_tokens=sum(
                    completion.usage.completion_tokens or 0 for completion in completions
                ),
                final_answer=answer,
                calls=[asdict(record) for record in orchestration_records],
                errors=[*retrieval_errors, *orchestration_errors],
            )
            results.append(result)
            logger.info(
                "[%02d/%02d] %s passed=%s tools=%s",
                index,
                len(selected_cases),
                case.case_id,
                result.passed,
                result.selected_tools,
            )
    finally:
        await wiki_service.aclose()
        await shared_client.aclose()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"context-evaluation-{timestamp}.json"
    markdown_path = output_dir / f"context-evaluation-{timestamp}.md"
    json_path.write_text(
        json.dumps([asdict(result) | {"passed": result.passed} for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown_report(results), encoding="utf-8")
    logger.info("JSON report: %s", json_path)
    logger.info("Markdown report: %s", markdown_path)
    return results


def _markdown_report(results: list[CaseResult]) -> str:
    passed = sum(result.passed for result in results)
    retrieval_passed = sum(result.retrieval_passed for result in results)
    selection_passed = sum(result.tool_selection_passed for result in results)
    support_passed = sum(result.answer_support_passed for result in results)
    lines = [
        "# 上下文评测报告",
        "",
        f"- 总案例：{len(results)}",
        f"- 完整通过：{passed}",
        f"- Retrieval 通过：{retrieval_passed}",
        f"- 工具选择通过：{selection_passed}",
        f"- 最终答案支持通过：{support_passed}",
        f"- Prompt tokens：{sum(result.prompt_tokens for result in results)}",
        f"- 重复工具调用：{sum(result.duplicate_calls for result in results)}",
        f"- 过期或冲突上下文：{sum(result.stale_or_conflict for result in results)}",
        "",
        "| 案例 | 类别 | 检索 | 工具选择 | 回答支持 | 重复调用 | 结果 |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for result in results:
        lines.append(
            "| {case_id} | {category} | {retrieval} | {tools} | {answer} | {duplicate} | {passed} |".format(
                case_id=result.case_id,
                category=result.category,
                retrieval="PASS" if result.retrieval_passed else "FAIL",
                tools="PASS" if result.tool_selection_passed else "FAIL",
                answer="PASS" if result.answer_support_passed else "FAIL",
                duplicate=result.duplicate_calls,
                passed="PASS" if result.passed else "FAIL",
            )
        )
    source_totals: dict[str, dict[str, int]] = {}
    for result in results:
        for call in result.calls:
            totals = source_totals.setdefault(
                call["name"],
                {"calls": 0, "chars": 0, "tokens": 0},
            )
            totals["calls"] += 1
            totals["chars"] += call["context_chars"]
            totals["tokens"] += call["estimated_context_tokens"]
    lines.extend(
        [
            "",
            "## 信息源规模",
            "",
            "| 工具 | 调用次数 | 返回字符数 | 估算 token 数 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name, totals in source_totals.items():
        lines.append(
            f"| {name} | {totals['calls']} | {totals['chars']} | {totals['tokens']} |"
        )
    lines.extend(["", "## 未通过案例", ""])
    for result in results:
        if result.passed:
            continue
        lines.extend(
            [
                f"### {result.case_id} {result.query}",
                "",
                f"- 预期工具：{result.expected_tools}",
                f"- 实际工具：{result.selected_tools}",
                f"- 错误：{result.errors}",
                f"- 回答：{result.final_answer}",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 TerrariaFriend Context Evaluation")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/context_evaluation"),
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case", action="append", dest="case_ids")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cases = evaluation_cases()
    if arguments.case_ids:
        requested = set(arguments.case_ids)
        cases = tuple(case for case in cases if case.case_id in requested)
    if arguments.limit is not None:
        cases = cases[: max(arguments.limit, 0)]
    results = asyncio.run(run_evaluation(arguments.output_dir, cases))
    passed = sum(result.passed for result in results)
    print(f"Context Evaluation: {passed}/{len(results)} passed")


if __name__ == "__main__":
    main()
