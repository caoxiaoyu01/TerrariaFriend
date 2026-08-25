from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from agent.models.trigger import (
    EventContext,
    GameEventRequest,
    GameEventType,
    PeriodicSummary,
    TriggerRequest,
    TriggerType,
    VitalsContext,
)

"""
    约定输入输出 schema
"""

# Decision Node 只允许选择三种后续路径
class DecisionAction(str, Enum):
    IGNORE = "IGNORE"
    RESPOND = "RESPOND"
    REASON = "REASON"


# 根据 Trigger 类型只携带当前判断需要的上下文
class DecisionGameEvent(BaseModel):
    event_type: GameEventType
    payload: dict[str, str | int]

    @classmethod
    def from_request(cls, game_event: GameEventRequest) -> "DecisionGameEvent":
        # 将通用 Subject 字段转换成各事件的语义 payload
        payload_names = {
            GameEventType.PLAYER_DIED: ("player_id", "player_name"),
            GameEventType.BOSS_SPAWNED: ("boss_type_id", "boss_name"),
            GameEventType.BOSS_ENDED: ("boss_type_id", "boss_name"),
            GameEventType.SCENE_FEATURE_ENTERED: ("feature_category", "feature_name"),
            GameEventType.WORLD_EVENT_STARTED: ("event_id", "event_name"),
            GameEventType.WORLD_EVENT_ENDED: ("event_id", "event_name"),
            GameEventType.SPECIAL_NPC_APPEARED: ("npc_type_id", "npc_name"),
            GameEventType.PROGRESS_MILESTONE_CHANGED: ("milestone_id", "milestone_name"),
        }

        if game_event.event_type is GameEventType.NEW_AREA_DISCOVERED:
            payload = {}
            if game_event.cell_x is not None:
                payload["cell_x"] = game_event.cell_x
            if game_event.cell_y is not None:
                payload["cell_y"] = game_event.cell_y
            return cls(event_type=game_event.event_type, payload=payload)

        id_name, display_name = payload_names[game_event.event_type]
        payload = {}
        if game_event.subject_id is not None:
            payload[id_name] = game_event.subject_id
        if game_event.subject_name is not None:
            payload[display_name] = game_event.subject_name
        return cls(event_type=game_event.event_type, payload=payload)


class DecisionInput(BaseModel):
    trigger_type: TriggerType
    vitals: VitalsContext
    user_query: str | None = None
    game_event: DecisionGameEvent | None = None
    event_context: EventContext | None = None
    periodic_summary: PeriodicSummary | None = None


    # 校验
    @model_validator(mode="after")
    def validate_trigger_context(self) -> "DecisionInput":
        # 每种 Trigger 必须提供自己的核心数据
        if self.trigger_type is TriggerType.USER_QUERY and not self.user_query:
            raise ValueError("USER_QUERY 缺少 user_query")
        if self.trigger_type is TriggerType.GAME_EVENT:
            if self.game_event is None:
                raise ValueError("GAME_EVENT 缺少 game_event")
            if self.event_context is None:
                raise ValueError("GAME_EVENT 缺少 event_context")
        if self.trigger_type is TriggerType.PERIODIC and self.periodic_summary is None:
            raise ValueError("PERIODIC 缺少 periodic_summary")
        return self

    @classmethod
    def from_trigger(cls, trigger: TriggerRequest) -> "DecisionInput":
        # 将 HTTP 请求转换成 Decision Node 专用输入
        return cls(
            trigger_type=trigger.trigger_type,
            vitals=trigger.vitals,
            user_query=trigger.user_query,
            game_event=(
                DecisionGameEvent.from_request(trigger.game_event)
                if trigger.game_event is not None
                else None
            ),
            event_context=trigger.event_context,
            periodic_summary=trigger.periodic_summary,
        )

    def to_prompt_payload(self) -> dict[str, Any]:
        # 只发送当前 Trigger 对应的紧凑动态字段
        payload: dict[str, Any] = {"trigger_type": self.trigger_type.value}
        if self.trigger_type is TriggerType.USER_QUERY:
            payload["query"] = self.user_query
        elif self.trigger_type is TriggerType.GAME_EVENT:
            payload["event_type"] = self.game_event.event_type.value
            payload["payload"] = self.game_event.payload
            payload["event_context"] = self.event_context.model_dump(
                mode="json",
                exclude_none=True,
            )
        else:
            payload["summary"] = self.periodic_summary.model_dump(
                mode="json",
                exclude_none=True,
            )
        payload["vitals"] = self.vitals.model_dump(mode="json")
        return payload


# 模型输出必须通过 Pydantic 校验后才能进入 Route
class DecisionResult(BaseModel):
    action: DecisionAction
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("reason 不能为空")
        return reason
