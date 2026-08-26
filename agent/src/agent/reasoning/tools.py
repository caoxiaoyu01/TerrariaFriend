import json
from typing import Any, Callable, Protocol

from agent.decision.schema import DecisionAction
from agent.models.game_snapshot import GameSnapshot
from agent.reasoning.schema import GameContextToolName, WikiToolArguments
from agent.reasoning.tool_policy import ToolPolicy


ToolReader = Callable[[GameSnapshot], dict[str, Any]]


TOOL_DESCRIPTIONS = {
    GameContextToolName.GET_PLAYER_CONTEXT.value: "读取玩家生命、魔力、防御、移动、呼吸、手持物品和 Buff",
    GameContextToolName.GET_COMBAT_CONTEXT.value: "读取当前战斗、Boss、附近敌人和最近受伤状态",
    GameContextToolName.GET_INVENTORY_CONTEXT.value: "读取快捷栏、护甲、饰品、恢复品、Boss 召唤物和空位摘要",
    GameContextToolName.GET_PROGRESS_CONTEXT.value: "读取已击败 Boss、世界里程碑和已访问关键区域",
    GameContextToolName.GET_SCENE_CONTEXT.value: "读取当前群系、层级、迷你群系、特殊区域和附近环境 Buff",
    GameContextToolName.GET_WORLD_CONTEXT.value: "读取当前时间、月相、天气和世界事件状态",
    GameContextToolName.LOOKUP_TERRARIA_KNOWLEDGE.value: (
        "查询可靠的 Terraria 外部知识，适合具体获取方式、配方、掉落、召唤条件、位置和游戏机制"
    ),
}


class TerrariaWikiToolClient(Protocol):
    async def lookup_terraria_knowledge(
        self,
        *,
        entity: str,
        intent: str = "general",
        lang: str = "zh",
    ) -> dict[str, Any]: ...


class GameContextTools:
    def __init__(self) -> None:
        self._readers: dict[GameContextToolName, tuple[str, ToolReader]] = {
            GameContextToolName.GET_PLAYER_CONTEXT: ("player", _player_context),
            GameContextToolName.GET_COMBAT_CONTEXT: ("combat", _combat_context),
            GameContextToolName.GET_INVENTORY_CONTEXT: (
                "inventory",
                _inventory_context,
            ),
            GameContextToolName.GET_PROGRESS_CONTEXT: ("progress", _progress_context),
            GameContextToolName.GET_SCENE_CONTEXT: ("scene", _scene_context),
            GameContextToolName.GET_WORLD_CONTEXT: ("world", _world_context),
        }

    def execute(
        self,
        name: GameContextToolName,
        arguments: dict[str, Any],
        snapshot: GameSnapshot,
    ) -> tuple[str, dict[str, Any]]:
        if arguments:
            raise ValueError(f"{name.value} 不接受参数")
        context_key, reader = self._readers[name]
        return context_key, reader(snapshot)


class ToolPermissionError(PermissionError):
    pass


class ToolExecutor:
    def __init__(
        self,
        registry: GameContextTools | None = None,
        policy: ToolPolicy | None = None,
        wiki_client: TerrariaWikiToolClient | None = None,
    ) -> None:
        self.registry = registry or GameContextTools()
        self.policy = policy or ToolPolicy()
        self.wiki_client = wiki_client

    @property
    def wiki_mcp_enabled(self) -> bool:
        return self.policy.wiki_mcp_enabled

    def available_tool_descriptions(
        self,
        mode: DecisionAction,
    ) -> dict[str, str]:
        return {
            name.value: TOOL_DESCRIPTIONS[name.value]
            for name in self.policy.allowed_tools(mode)
        }

    def available_tool_specs(
        self,
        mode: DecisionAction,
    ) -> dict[str, dict[str, Any]]:
        wiki_arguments = WikiToolArguments.model_json_schema()["properties"]
        return {
            name.value: {
                "description": TOOL_DESCRIPTIONS[name.value],
                "args": (
                    wiki_arguments
                    if name is GameContextToolName.LOOKUP_TERRARIA_KNOWLEDGE
                    else {}
                ),
            }
            for name in self.policy.allowed_tools(mode)
        }

    def execute(
        self,
        mode: DecisionAction,
        name: GameContextToolName,
        arguments: dict[str, Any],
        snapshot: GameSnapshot,
    ) -> tuple[str, dict[str, Any]]:
        if not self.policy.is_allowed(mode, name):
            raise ToolPermissionError(
                f"{mode.value} 不允许调用工具 {name.value}"
            )
        return self.registry.execute(name, arguments, snapshot)

    async def execute_async(
        self,
        mode: DecisionAction,
        name: GameContextToolName,
        arguments: dict[str, Any],
        snapshot: GameSnapshot,
    ) -> tuple[str, dict[str, Any]]:
        if not self.policy.is_allowed(mode, name):
            raise ToolPermissionError(
                f"{mode.value} 不允许调用工具 {name.value}"
            )
        if name is not GameContextToolName.LOOKUP_TERRARIA_KNOWLEDGE:
            return self.registry.execute(name, arguments, snapshot)
        if self.wiki_client is None:
            raise RuntimeError("Terraria Wiki MCP Client 不可用")

        validated_arguments = WikiToolArguments.model_validate(arguments)

        result = await self.wiki_client.lookup_terraria_knowledge(
            **validated_arguments.model_dump(mode="json"),
        )
        return "terraria_wiki", result


def tool_signature(name: str, arguments: dict[str, Any]) -> str:
    return json.dumps(
        {"name": name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _select(source: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {name: source[name] for name in names if name in source}


def _player_context(snapshot: GameSnapshot) -> dict[str, Any]:
    return _select(
        snapshot.player,
        (
            "playerId",
            "name",
            "isDead",
            "life",
            "maxLife",
            "mana",
            "maxMana",
            "defense",
            "positionTileX",
            "positionTileY",
            "velocityTilesPerSecondX",
            "velocityTilesPerSecondY",
            "direction",
            "isMounted",
            "breath",
            "maxBreath",
            "heldItem",
            "buffs",
        ),
    )


def _combat_context(snapshot: GameSnapshot) -> dict[str, Any]:
    return _select(
        snapshot.combat,
        (
            "inCombat",
            "combatDurationSeconds",
            "bossActive",
            "activeBosses",
            "nearbyEnemyCount",
            "hpRatio",
            "recentDamage",
        ),
    )


def _inventory_context(snapshot: GameSnapshot) -> dict[str, Any]:
    return _select(
        snapshot.inventory,
        (
            "hotbar",
            "armor",
            "accessories",
            "healing",
            "mana",
            "bossSummons",
            "freeSlots",
        ),
    )


def _progress_context(snapshot: GameSnapshot) -> dict[str, Any]:
    return _select(
        snapshot.progress,
        ("defeatedBosses", "worldMilestones", "visitedRegions"),
    )


def _scene_context(snapshot: GameSnapshot) -> dict[str, Any]:
    return _select(
        snapshot.scene,
        ("biomes", "layer", "miniBiomes", "specialAreas", "nearbyBuffs"),
    )


def _world_context(snapshot: GameSnapshot) -> dict[str, Any]:
    return _select(snapshot.world, ("time", "weather", "activeEvents"))
