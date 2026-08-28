from collections.abc import Callable
from datetime import datetime

from agent.models.game_snapshot import GameSnapshot
from agent.models.trigger import (
    EventContext,
    GameEventRequest,
    GameEventType,
    TriggerRequest,
    TriggerType,
)
from agent.models.execution import AgentExecutionResult
from agent.trace.capsule.projector import (
    project_agent_response_capsule,
    project_combat_capsule,
    project_equipment_capsule,
    project_exploration_capsule,
    project_progress_capsule,
    project_user_query_capsule,
    project_world_event_capsule,
)
from agent.trace.capsule.schema import SupportedStateCapsule


CapsuleProjector = Callable[..., SupportedStateCapsule]

CAPSULE_PROJECTORS: dict[GameEventType, CapsuleProjector] = {
    GameEventType.PLAYER_DIED: project_combat_capsule,
    GameEventType.BOSS_SPAWNED: project_combat_capsule,
    GameEventType.BOSS_ENDED: project_combat_capsule,
    GameEventType.BOSS_DEFEATED: project_combat_capsule,
    GameEventType.NEW_AREA_DISCOVERED: project_exploration_capsule,
    GameEventType.SCENE_FEATURE_ENTERED: project_exploration_capsule,
    GameEventType.SCENE_FEATURE_EXITED: project_exploration_capsule,
    GameEventType.PROGRESS_MILESTONE_CHANGED: project_progress_capsule,
    GameEventType.EQUIPMENT_CHANGED: project_equipment_capsule,
    GameEventType.WORLD_EVENT_ENDED: project_world_event_capsule,
}


def project_trigger_capsule(
    trigger: TriggerRequest,
) -> SupportedStateCapsule | None:
    """从一次触发请求中提取发生当时的事件数据"""

    if trigger.game_snapshot is None:
        return None
    if trigger.trigger_type is TriggerType.USER_QUERY:
        if trigger.user_query is None:
            return None
        return project_user_query_capsule(trigger)
    if trigger.game_event is None:
        return None
    return _project_state_capsule(
        trigger.game_event,
        trigger.event_context,
        trigger.game_snapshot,
        captured_at=trigger.timestamp,
    )


def project_response_capsule(
    trigger: TriggerRequest,
    execution: AgentExecutionResult,
) -> SupportedStateCapsule | None:
    """根据请求发生时的游戏状态整理回复记录"""

    if trigger.game_snapshot is None or not execution.message:
        return None
    return project_agent_response_capsule(trigger, execution)


def _project_state_capsule(
    event: GameEventRequest,
    context: EventContext | None,
    snapshot: GameSnapshot,
    *,
    captured_at: datetime,
) -> SupportedStateCapsule | None:
    projector = CAPSULE_PROJECTORS.get(event.event_type)
    if projector is None:
        return None
    return projector(event, context, snapshot, captured_at=captured_at)
