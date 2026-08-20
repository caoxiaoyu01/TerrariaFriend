from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TriggerType(str, Enum):
    USER_QUERY = "USER_QUERY"
    GAME_EVENT = "GAME_EVENT"
    PERIODIC = "PERIODIC"


class TriggerPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class GameEventType(str, Enum):
    PLAYER_DIED = "PlayerDied"
    BOSS_SPAWNED = "BossSpawned"
    BOSS_ENDED = "BossEnded"
    REGION_ENTERED = "RegionEntered"
    WORLD_EVENT_STARTED = "WorldEventStarted"
    WORLD_EVENT_ENDED = "WorldEventEnded"
    SPECIAL_NPC_APPEARED = "SpecialNpcAppeared"
    PROGRESS_MILESTONE_CHANGED = "ProgressMilestoneChanged"


class GameEventRequest(CamelModel):
    event_type: GameEventType
    subject_id: str | None = None
    subject_name: str | None = None


class TriggerRequest(CamelModel):
    trigger_type: TriggerType
    timestamp: datetime
    priority: TriggerPriority
    game_event: GameEventRequest | None = None
    user_query: str | None = None


class AgentResponse(CamelModel):
    action: str
    message: str | None
    success: bool
    error: str | None
