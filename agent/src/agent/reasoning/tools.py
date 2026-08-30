import json
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.decision.schema import DecisionAction
from agent.models.game_snapshot import GameSnapshot
from agent.memory.retrieval import (
    MEMORY_TOOL_DESCRIPTION,
    MemoryContextTool,
    MemoryToolArguments,
)


logger = logging.getLogger("uvicorn.error")


class EmptyToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WikiToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str = Field(min_length=1)
    intent: Literal[
        "general",
        "obtaining",
        "usage",
        "crafting",
        "summoning",
        "location",
        "drops",
        "mechanics",
    ] = "general"
    lang: Literal["zh", "en"] = "zh"

    @field_validator("entity")
    @classmethod
    def normalize_entity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("entity 不能为空")
        return normalized


class TerrariaWikiToolClient(Protocol):
    async def lookup_terraria_knowledge(
        self,
        *,
        entity: str,
        intent: str = "general",
        lang: str = "zh",
    ) -> dict[str, Any]: ...


class ToolPermissionError(PermissionError):
    pass


ToolHandler = Callable[
    [BaseModel, GameSnapshot],
    dict[str, Any] | BaseModel | Awaitable[dict[str, Any] | BaseModel],
]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments_model: type[BaseModel]
    allowed_modes: frozenset[DecisionAction]
    handler: ToolHandler
    context_key: str


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs = {spec.name: spec for spec in specs}
        if len(self._specs) != len(specs):
            raise ValueError("工具名称不能重复")

    @property
    def wiki_mcp_enabled(self) -> bool:
        return "lookup_terraria_knowledge" in self._specs

    def available_tool_descriptions(self, mode: DecisionAction) -> dict[str, str]:
        return {
            spec.name: spec.description
            for spec in self._specs.values()
            if mode in spec.allowed_modes
        }

    def available_tool_specs(
        self,
        mode: DecisionAction,
    ) -> dict[str, dict[str, Any]]:
        return {
            spec.name: {
                "description": spec.description,
                "args": spec.arguments_model.model_json_schema().get("properties", {}),
            }
            for spec in self._specs.values()
            if mode in spec.allowed_modes
        }

    def is_allowed(self, mode: DecisionAction, name: str) -> bool:
        spec = self._specs.get(name)
        allowed = spec is not None and mode in spec.allowed_modes
        logger.info(
            "[ToolPolicy] mode=%s tool=%s allowed=%s",
            mode.value,
            name,
            str(allowed).lower(),
        )
        return allowed

    def execute(
        self,
        mode: DecisionAction,
        name: str,
        arguments: dict[str, Any],
        snapshot: GameSnapshot,
    ) -> tuple[str, dict[str, Any]]:
        spec, validated = self._prepare(mode, name, arguments)
        result = spec.handler(validated, snapshot)
        if inspect.isawaitable(result):
            raise RuntimeError(f"工具 {name} 需要异步调用")
        return spec.context_key, _result_dict(result)

    async def execute_async(
        self,
        mode: DecisionAction,
        name: str,
        arguments: dict[str, Any],
        snapshot: GameSnapshot,
    ) -> tuple[str, dict[str, Any]]:
        spec, validated = self._prepare(mode, name, arguments)
        result = spec.handler(validated, snapshot)
        if inspect.isawaitable(result):
            result = await result
        return spec.context_key, _result_dict(result)

    async def execute_into_context(
        self,
        mode: DecisionAction,
        name: str,
        arguments: dict[str, Any],
        snapshot: GameSnapshot,
        collected_context: dict[str, Any],
    ) -> dict[str, Any]:
        context_key, result = await self.execute_async(
            mode,
            name,
            arguments,
            snapshot,
        )
        collected_context[context_key] = result
        return result

    def _prepare(
        self,
        mode: DecisionAction,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[ToolSpec, BaseModel]:
        if not self.is_allowed(mode, name):
            raise ToolPermissionError(f"{mode.value} 不允许调用工具 {name}")
        spec = self._specs[name]
        return spec, spec.arguments_model.model_validate(arguments)


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        *,
        policy: Any | None = None,
        wiki_client: TerrariaWikiToolClient | None = None,
        memory_tool: MemoryContextTool | None = None,
    ) -> None:
        self.registry = registry or create_tool_registry(
            wiki_client=wiki_client,
            memory_tool=memory_tool,
            include_wiki=(
                wiki_client is not None
                or bool(getattr(policy, "wiki_mcp_enabled", False))
            ),
        )

    @property
    def wiki_mcp_enabled(self) -> bool:
        return self.registry.wiki_mcp_enabled

    def available_tool_descriptions(self, mode: DecisionAction) -> dict[str, str]:
        return self.registry.available_tool_descriptions(mode)

    def available_tool_specs(
        self,
        mode: DecisionAction,
    ) -> dict[str, dict[str, Any]]:
        return self.registry.available_tool_specs(mode)

    def execute(
        self,
        mode: DecisionAction,
        name: str,
        arguments: dict[str, Any],
        snapshot: GameSnapshot,
    ) -> tuple[str, dict[str, Any]]:
        return self.registry.execute(mode, name, arguments, snapshot)

    async def execute_async(
        self,
        mode: DecisionAction,
        name: str,
        arguments: dict[str, Any],
        snapshot: GameSnapshot,
    ) -> tuple[str, dict[str, Any]]:
        return await self.registry.execute_async(mode, name, arguments, snapshot)

    async def execute_into_context(
        self,
        mode: DecisionAction,
        name: str,
        arguments: dict[str, Any],
        snapshot: GameSnapshot,
        collected_context: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.registry.execute_into_context(
            mode,
            name,
            arguments,
            snapshot,
            collected_context,
        )


def create_tool_registry(
    *,
    wiki_client: TerrariaWikiToolClient | None = None,
    memory_tool: MemoryContextTool | None = None,
    include_wiki: bool = False,
) -> ToolRegistry:
    respond_and_reason = frozenset({DecisionAction.RESPOND, DecisionAction.REASON})
    reason_only = frozenset({DecisionAction.REASON})
    specs = [
        ToolSpec(
            "get_player_context",
            "读取玩家生命、魔力、防御、移动、呼吸、当前坐骑、手持物品和 Buff",
            EmptyToolArguments,
            respond_and_reason,
            _game_handler(_player_context),
            "player",
        ),
        ToolSpec(
            "get_combat_context",
            "读取当前战斗、Boss、附近敌人和最近受伤状态",
            EmptyToolArguments,
            respond_and_reason,
            _game_handler(_combat_context),
            "combat",
        ),
        ToolSpec(
            "get_inventory_context",
            "读取快捷栏、护甲、饰品、恢复品、Boss 召唤物和空位摘要",
            EmptyToolArguments,
            reason_only,
            _game_handler(_inventory_context),
            "inventory",
        ),
        ToolSpec(
            "get_progress_context",
            "读取已击败 Boss、世界里程碑和已访问关键区域",
            EmptyToolArguments,
            reason_only,
            _game_handler(_progress_context),
            "progress",
        ),
        ToolSpec(
            "get_scene_context",
            "读取当前群系、层级、迷你群系、特殊区域和附近环境 Buff",
            EmptyToolArguments,
            respond_and_reason,
            _game_handler(_scene_context),
            "scene",
        ),
        ToolSpec(
            "get_world_context",
            "读取当前时间、月相、天气和世界事件状态",
            EmptyToolArguments,
            respond_and_reason,
            _game_handler(_world_context),
            "world",
        ),
        ToolSpec(
            "get_memory_context",
            MEMORY_TOOL_DESCRIPTION,
            MemoryToolArguments,
            reason_only,
            _memory_handler(memory_tool),
            "memory",
        ),
    ]
    if include_wiki or wiki_client is not None:
        specs.append(
            ToolSpec(
                "lookup_terraria_knowledge",
                "查询可靠的 Terraria 外部知识，适合具体获取方式、配方、掉落、召唤条件、位置和游戏机制",
                WikiToolArguments,
                reason_only,
                _wiki_handler(wiki_client),
                "terraria_wiki",
            )
        )
    return ToolRegistry(specs)


def _game_handler(
    reader: Callable[[GameSnapshot], dict[str, Any]],
) -> ToolHandler:
    def handle(_: BaseModel, snapshot: GameSnapshot) -> dict[str, Any]:
        return reader(snapshot)

    return handle


def _memory_handler(memory_tool: MemoryContextTool | None) -> ToolHandler:
    async def handle(arguments: BaseModel, _: GameSnapshot) -> BaseModel:
        if memory_tool is None:
            raise RuntimeError("玩家记忆工具不可用")
        return await memory_tool.get_memory_context(
            **arguments.model_dump(mode="json")
        )

    return handle


def _wiki_handler(wiki_client: TerrariaWikiToolClient | None) -> ToolHandler:
    async def handle(arguments: BaseModel, _: GameSnapshot) -> dict[str, Any]:
        if wiki_client is None:
            raise RuntimeError("Terraria Wiki MCP Client 不可用")
        return await wiki_client.lookup_terraria_knowledge(
            **arguments.model_dump(mode="json")
        )

    return handle


def _result_dict(result: dict[str, Any] | BaseModel) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    return result


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
            "mount",
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
        ("defeatedBosses", "worldMilestones", "currentStage", "visitedRegions"),
    )


def _scene_context(snapshot: GameSnapshot) -> dict[str, Any]:
    return _select(
        snapshot.scene,
        ("biomes", "layer", "miniBiomes", "specialAreas", "nearbyBuffs"),
    )


def _world_context(snapshot: GameSnapshot) -> dict[str, Any]:
    return _select(snapshot.world, ("time", "weather", "activeEvents"))
