from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import Field, field_validator, model_validator

from agent.models.trigger_base import CamelModel
from agent.models.execution import ToolHistoryMetadata
from agent.decision.schema import DecisionAction


class CapsuleType(str, Enum):
    COMBAT = "combat"
    EQUIPMENT = "equipment"
    EXPLORATION = "exploration"
    PROGRESS = "progress"
    CONVERSATION = "conversation"
    WORLD_EVENT = "world_event"


class CapsuleEntityRef(CamelModel):
    entity_type: str = Field(min_length=1)
    entity_id: str | None = None
    entity_name: str | None = None

    @model_validator(mode="after")
    def require_identity(self) -> "CapsuleEntityRef":
        if not self.entity_id and not self.entity_name:
            raise ValueError("entity_id 和 entity_name 至少需要一个")
        return self


class ItemState(CamelModel):
    type_id: int
    name: str
    stack: int


class ArmorState(CamelModel):
    head: ItemState | None = None
    body: ItemState | None = None
    legs: ItemState | None = None


class SceneState(CamelModel):
    biomes: list[str] = Field(default_factory=list)
    layer: str | None = None
    mini_biomes: list[str] = Field(default_factory=list)
    special_areas: list[str] = Field(default_factory=list)


class CombatPlayerState(CamelModel):
    is_dead: bool
    life: int
    max_life: int
    hp_ratio: float
    mana: int
    max_mana: int
    defense: int


class BossState(CamelModel):
    type_id: int
    name: str
    life_ratio: float


class RecentDamageState(CamelModel):
    damage_taken_last_5s: int
    last_damage_amount: int
    last_damage_source: str | None = None
    time_since_last_damage_seconds: float


class CombatState(CamelModel):
    in_combat: bool
    bosses: list[BossState] = Field(default_factory=list)
    nearby_enemy_count: int
    recent_damage: RecentDamageState


class CombatLoadoutState(CamelModel):
    held_item: ItemState
    armor: ArmorState
    accessories: list[ItemState] = Field(default_factory=list)


class HealingState(CamelModel):
    total_healing_item_count: int
    best_healing_item: ItemState | None = None
    best_healing_amount: int


class CombatCapsuleData(CamelModel):
    event_state: Literal[
        "boss_spawned",
        "boss_disappeared",
        "boss_defeated",
        "player_died",
    ]
    player: CombatPlayerState
    combat: CombatState
    loadout: CombatLoadoutState
    healing: HealingState
    scene: SceneState
    progression_stage: str


class AreaCell(CamelModel):
    x: int
    y: int
    size_tiles: int = 100


class SceneFeatureExplorationData(CamelModel):
    discovery_kind: Literal["scene_feature"] = "scene_feature"
    feature_category: str | None = None
    feature_name: str | None = None
    current_scene: SceneState
    progression_stage: str
    is_first_world_discovery: bool = True


class AreaExplorationData(CamelModel):
    discovery_kind: Literal["area_cell"] = "area_cell"
    cell: AreaCell | None = None
    previous_scene: SceneState | None = None
    current_scene: SceneState
    progression_stage: str


ExplorationCapsuleData = SceneFeatureExplorationData | AreaExplorationData


class ProgressUnlockState(CamelModel):
    unlocked: bool


class ProgressCapsuleData(CamelModel):
    change_category: Literal["boss", "world_milestone"] | None = None
    change_id: str | None = None
    change_name: str | None = None
    before: ProgressUnlockState = Field(
        default_factory=lambda: ProgressUnlockState(unlocked=False)
    )
    after: ProgressUnlockState = Field(
        default_factory=lambda: ProgressUnlockState(unlocked=True)
    )
    progression_stage_after: str
    scene: SceneState


class EquipmentCapsuleData(CamelModel):
    armor_before: ArmorState | None = None
    armor_after: ArmorState | None = None
    accessories_added: list[ItemState] = Field(default_factory=list)
    accessories_removed: list[ItemState] = Field(default_factory=list)


class ConversationCapsuleData(CamelModel):
    role: Literal["player", "agent"]
    content: str
    progression_stage: str
    in_combat: bool
    active_bosses: list[BossState] = Field(default_factory=list)
    scene: SceneState
    decision_action: DecisionAction | None = None
    reasoning_rounds: int = Field(default=0, ge=0)
    used_game_context: dict[str, dict[str, Any]] = Field(default_factory=dict)
    tool_history: list[ToolHistoryMetadata] = Field(default_factory=list)


class WorldEventCapsuleData(CamelModel):
    event_id: str | None = None
    event_name: str | None = None
    remaining_active_event_ids: list[str] = Field(default_factory=list)


CapsuleDataT = TypeVar("CapsuleDataT", bound=CamelModel)


class StateCapsule(CamelModel, Generic[CapsuleDataT]):
    """只保存事件本身相关的简要事实"""

    capsule_type: CapsuleType
    captured_at: datetime
    snapshot_tick: int = Field(ge=0)
    source_event_type: str = Field(min_length=1)
    primary_entity: CapsuleEntityRef | None = None
    data: CapsuleDataT

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at 必须包含时区")
        return value


CombatCapsule = StateCapsule[CombatCapsuleData]
ExplorationCapsule = StateCapsule[ExplorationCapsuleData]
ProgressCapsule = StateCapsule[ProgressCapsuleData]
EquipmentCapsule = StateCapsule[EquipmentCapsuleData]
ConversationCapsule = StateCapsule[ConversationCapsuleData]
WorldEventCapsule = StateCapsule[WorldEventCapsuleData]
SupportedStateCapsule = (
    CombatCapsule
    | ExplorationCapsule
    | ProgressCapsule
    | EquipmentCapsule
    | ConversationCapsule
    | WorldEventCapsule
)
