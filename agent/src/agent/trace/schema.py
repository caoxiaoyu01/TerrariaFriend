from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import Field, field_validator

from agent.models.trigger import TriggerPriority, TriggerType
from agent.models.trigger_base import CamelModel
from agent.trace.capsule.schema import SupportedStateCapsule


class TraceOrigin(str, Enum):
    TRIGGER = "trigger"
    RESPONSE = "response"


class TraceMetadata(CamelModel):
    """记录事件来自哪里以及何时发生"""

    origin: TraceOrigin
    trigger_type: TriggerType
    trigger_priority: TriggerPriority


class TraceEvent(CamelModel):
    """保存后不再修改的近期记忆事件"""

    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    occurred_at: datetime
    correlation_id: str | None = None
    capsule: SupportedStateCapsule
    trace_metadata: TraceMetadata

    @field_validator("id", "correlation_id")
    @classmethod
    def normalize_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("ID 不能为空")
        return normalized

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at 必须包含时区")
        return value
