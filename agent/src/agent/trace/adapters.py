from datetime import datetime

from agent.models.execution import AgentExecutionResult
from agent.models.trigger import TriggerRequest
from agent.trace.capsule import project_response_capsule, project_trigger_capsule
from agent.trace.schema import TraceEvent, TraceMetadata, TraceOrigin


def trigger_to_trace_event(
    trigger: TriggerRequest,
    *,
    correlation_id: str | None = None,
    event_id: str | None = None,
) -> TraceEvent | None:
    """把一次触发请求转换成轨迹事件 不重新采集游戏状态"""

    capsule = project_trigger_capsule(trigger)
    if capsule is None:
        return None
    values = {
        "occurred_at": trigger.timestamp,
        "correlation_id": correlation_id,
        "capsule": capsule,
        "trace_metadata": TraceMetadata(
            origin=TraceOrigin.TRIGGER,
            trigger_type=trigger.trigger_type,
            trigger_priority=trigger.priority,
        ),
    }
    if event_id is not None:
        values["id"] = event_id
    return TraceEvent.model_validate(values)


def response_to_trace_event(
    trigger: TriggerRequest,
    execution: AgentExecutionResult,
    *,
    occurred_at: datetime,
    correlation_id: str,
    event_id: str | None = None,
) -> TraceEvent | None:
    """把当前触发产生的回复转换成轨迹事件"""

    capsule = project_response_capsule(trigger, execution)
    if capsule is None:
        return None
    values = {
        "occurred_at": occurred_at,
        "correlation_id": correlation_id,
        "capsule": capsule,
        "trace_metadata": TraceMetadata(
            origin=TraceOrigin.RESPONSE,
            trigger_type=trigger.trigger_type,
            trigger_priority=trigger.priority,
        ),
    }
    if event_id is not None:
        values["id"] = event_id
    return TraceEvent.model_validate(values)
