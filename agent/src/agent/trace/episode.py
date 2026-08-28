from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from agent.models.execution import AgentExecutionResult
from agent.models.trigger import TriggerRequest, TriggerType
from agent.models.trigger_base import CamelModel
from agent.trace.adapters import response_to_trace_event, trigger_to_trace_event
from agent.trace.schema import TraceEvent, TraceOrigin


class EpisodeType(str, Enum):
    CONVERSATION = "conversation"
    EVENT = "event"


class Episode(CamelModel):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    episode_type: EpisodeType
    started_at: datetime
    ended_at: datetime
    correlation_id: str | None = None
    events: list[TraceEvent] = Field(min_length=1)

    @field_validator("started_at", "ended_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Episode 时间必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_event_bounds(self) -> "Episode":
        if self.ended_at < self.started_at:
            raise ValueError("ended_at 不能早于 started_at")
        if self.started_at != self.events[0].occurred_at:
            raise ValueError("started_at 必须来自首个 TraceEvent")
        if self.ended_at != self.events[-1].occurred_at:
            raise ValueError("ended_at 必须来自最后一个 TraceEvent")
        return self


def build_episode(
    events: list[TraceEvent],
    *,
    episode_id: str | None = None,
) -> Episode:
    """把同一次事件和回复组成一个完整情节"""

    if not events:
        raise ValueError("Episode 至少需要一个 TraceEvent")
    if any(
        right.occurred_at < left.occurred_at
        for left, right in zip(events, events[1:])
    ):
        raise ValueError("TraceEvent 必须按 occurred_at 顺序传入")

    trigger_event = events[0]
    is_conversation = trigger_event.capsule.source_event_type == "USER_QUERY"
    episode_type = (
        EpisodeType.CONVERSATION if is_conversation else EpisodeType.EVENT
    )

    if len(events) == 1:
        if is_conversation or trigger_event.trace_metadata.origin is TraceOrigin.RESPONSE:
            raise ValueError("对话 Episode 必须包含 USER_QUERY 和 AGENT_RESPONSE")
        correlation_id = trigger_event.correlation_id
    elif len(events) == 2:
        response_event = events[1]
        correlation_id = trigger_event.correlation_id
        if (
            not correlation_id
            or response_event.correlation_id != correlation_id
            or response_event.trace_metadata.origin is not TraceOrigin.RESPONSE
            or response_event.capsule.source_event_type != "AGENT_RESPONSE"
        ):
            raise ValueError("两个 TraceEvent 必须是同 correlation_id 的 trigger + response")
    else:
        raise ValueError("P0 Episode 只允许一个 trigger 和可选的一个 response")

    values = {
        "episode_type": episode_type,
        "started_at": events[0].occurred_at,
        "ended_at": events[-1].occurred_at,
        "correlation_id": correlation_id,
        "events": events,
    }
    if episode_id is not None:
        values["id"] = episode_id
    return Episode.model_validate(values)


def build_trigger_episode(
    trigger: TriggerRequest,
    *,
    execution: AgentExecutionResult | None = None,
    response_occurred_at: datetime | None = None,
) -> Episode | None:
    """只有触发确实产生回复时才把两者关联起来"""

    if trigger.trigger_type is TriggerType.USER_QUERY and execution is None:
        raise ValueError("USER_QUERY Episode 需要对应的 AgentExecutionResult")
    if execution is not None and response_occurred_at is None:
        raise ValueError("生成 response TraceEvent 时必须提供实际发生时间")

    correlation_id = str(uuid4()) if execution is not None else None
    trigger_event = trigger_to_trace_event(trigger, correlation_id=correlation_id)
    if trigger_event is None:
        return None
    events = [trigger_event]
    if execution is not None:
        response_event = response_to_trace_event(
            trigger,
            execution,
            occurred_at=response_occurred_at,
            correlation_id=correlation_id,
        )
        if response_event is None:
            return None
        events.append(response_event)
    return build_episode(events)
