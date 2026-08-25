import json
from collections import deque
from typing import Any

from agent.llm.client import LLMCompletion, LLMUsage
from agent.llm.config import ModelConfig


class ScriptedRoleLLMClient:
    def __init__(
        self,
        outputs: list[dict[str, Any] | str | Exception],
        *,
        role: str = "test",
        enable_thinking: bool = False,
    ) -> None:
        self.config = ModelConfig(
            role=role,
            model_name=f"{role}-model",
            temperature=0.0,
            max_tokens=256,
            enable_thinking=enable_thinking,
            reasoning_effort="high" if enable_thinking else None,
        )
        self._outputs = deque(outputs)
        self.inputs: list[dict[str, Any]] = []

    @property
    def model_name(self) -> str:
        return self.config.model_name

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
        output_schema: dict[str, Any],
        include_output_schema: bool = True,
    ) -> LLMCompletion:
        self.inputs.append(input_data)
        return self._next_completion()

    async def generate_text(
        self,
        *,
        system_prompt: str,
        input_data: dict[str, Any],
    ) -> LLMCompletion:
        self.inputs.append(input_data)
        return self._next_completion()

    def _next_completion(self) -> LLMCompletion:
        output = self._outputs.popleft()
        if isinstance(output, Exception):
            raise output
        content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        return LLMCompletion(
            content=content,
            reasoning_content="不会显示给玩家的内部推理",
            usage=LLMUsage(
                prompt_tokens=10,
                completion_tokens=5,
                reasoning_tokens=2,
                total_tokens=15,
            ),
            latency_seconds=0.01,
        )


def game_snapshot_payload() -> dict[str, Any]:
    return {
        "tick": 120,
        "player": {
            "playerId": 0,
            "name": "Player",
            "isDead": False,
            "life": 190,
            "maxLife": 500,
            "mana": 100,
            "maxMana": 200,
            "defense": 28,
            "positionTileX": 120.0,
            "positionTileY": 300.0,
            "heldItem": {"typeId": 1, "name": "Sword", "stack": 1},
            "buffs": [],
        },
        "inventory": {
            "hotbar": [],
            "armor": {"head": None, "body": None, "legs": None},
            "accessories": [],
            "healing": {
                "totalHealingItemCount": 3,
                "bestHealingItem": {
                    "typeId": 28,
                    "name": "Healing Potion",
                    "stack": 3,
                },
                "bestHealingAmount": 100,
            },
            "mana": {
                "totalManaItemCount": 0,
                "bestManaItem": None,
                "bestManaAmount": 0,
            },
            "bossSummons": [],
            "freeSlots": 12,
        },
        "world": {
            "time": {"isDay": True, "timeOfDay": "Morning", "moonPhase": "Full"},
            "weather": {
                "isRaining": False,
                "rainIntensity": 0.0,
                "windSpeed": 0.0,
                "isSandstorm": False,
            },
            "activeEvents": [],
        },
        "progress": {
            "defeatedBosses": ["Eye of Cthulhu"],
            "worldMilestones": [],
            "visitedRegions": ["Jungle"],
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
            "bossActive": False,
            "activeBosses": [],
            "nearbyEnemyCount": 3,
            "hpRatio": 0.38,
            "recentDamage": {
                "damageTakenLast5s": 75,
                "lastDamageAmount": 30,
                "lastDamageSource": "Hornet",
                "timeSinceLastDamageSeconds": 0.5,
            },
        },
        "npc": {
            "townNpcCount": 0,
            "townNpcs": [],
            "nearbyTownNpcCount": 0,
            "nearbyTownNpcs": [],
            "specialNpcCount": 0,
            "specialNpcs": [],
            "bossActive": False,
            "activeBossCount": 0,
            "activeBosses": [],
        },
    }


def user_query_json(*, query: str = "我下一步应该干什么？", hp_delta: float = 0.0) -> dict[str, Any]:
    return {
        "triggerType": "USER_QUERY",
        "timestamp": "2026-08-25T12:00:00Z",
        "priority": "HIGH",
        "vitals": {
            "hpRatio": 0.38,
            "hpDelta": hp_delta,
            "inCombat": True,
        },
        "userQuery": query,
        "gameSnapshot": game_snapshot_payload(),
    }
