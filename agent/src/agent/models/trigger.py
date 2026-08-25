from datetime import datetime
from enum import Enum

from pydantic import Field

from agent.models.game_snapshot import GameSnapshot
from agent.models.trigger_base import CamelModel



# Trigger 类型
class TriggerType(str, Enum):
    USER_QUERY = "USER_QUERY"
    GAME_EVENT = "GAME_EVENT"
    PERIODIC = "PERIODIC"

# 分级
class TriggerPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


# 游戏状态变化类型
class GameEventType(str, Enum):
    PLAYER_DIED = "PlayerDied"
    BOSS_SPAWNED = "BossSpawned"
    BOSS_ENDED = "BossEnded"
    NEW_AREA_DISCOVERED = "NewAreaDiscovered"
    SCENE_FEATURE_ENTERED = "SceneFeatureEntered"
    WORLD_EVENT_STARTED = "WorldEventStarted"
    WORLD_EVENT_ENDED = "WorldEventEnded"
    SPECIAL_NPC_APPEARED = "SpecialNpcAppeared"
    PROGRESS_MILESTONE_CHANGED = "ProgressMilestoneChanged"


class GameEventRequest(CamelModel):
    event_type: GameEventType
    subject_id: str | None = None
    subject_name: str | None = None
    cell_x: int | None = None
    cell_y: int | None = None


# GAME_EVENT 发生时用于决策的少量局部事实
class EventContext(CamelModel):
    nearby_enemy_count: int | None = Field(default=None, ge=0)
    progression_stage: str | None = None
    occurrence_count: int | None = Field(default=None, ge=0)
    active_events: list[str] | None = None
    biomes: list[str] | None = None
    layer: str | None = None
    mini_biomes: list[str] | None = None
    special_areas: list[str] | None = None
    previous_biomes: list[str] | None = None
    previous_layer: str | None = None
    previous_mini_biomes: list[str] | None = None
    previous_special_areas: list[str] | None = None
    is_nearby: bool | None = None
    boss_active: bool | None = None
    boss_name: str | None = None
    damage_taken_last_5s: int | None = Field(default=None, ge=0)
    last_damage_source: str | None = None


# PERIODIC 只携带 Decision 所需的轻量状态
class PeriodicSummary(CamelModel):
    biomes: list[str] = Field(default_factory=list)
    layer: str
    active_bosses: list[str] = Field(default_factory=list)
    progression_stage: str
    held_item: str


# 三种 Trigger 共享的当前生命状态
class VitalsContext(CamelModel):
    hp_ratio: float = Field(ge=0.0, le=1.0)
    hp_delta: float
    in_combat: bool


# FastAPI 接收的 C# TriggerEvent 请求结构
class TriggerRequest(CamelModel):
    trigger_type: TriggerType
    timestamp: datetime
    priority: TriggerPriority
    vitals: VitalsContext
    game_event: GameEventRequest | None = None
    event_context: EventContext | None = None
    user_query: str | None = None
    periodic_summary: PeriodicSummary | None = None
    # Decision 不读取完整快照 仅在 REASON 时作为 Tool 数据源
    game_snapshot: GameSnapshot | None = None


class AgentResponse(CamelModel):
    action: str
    message: str | None
    decision_reason: str | None
    success: bool
    error: str | None
