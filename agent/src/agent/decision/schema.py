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

# 决策结果只能走以下三条路径
class DecisionAction(str, Enum):
    IGNORE = "IGNORE"
    RESPOND = "RESPOND"
    REASON = "REASON"


# 每种触发只携带当前判断需要的信息
class DecisionGameEvent(BaseModel):
    event_type: GameEventType
    payload: dict[str, str | int]

    @classmethod
    def from_request(cls, game_event: GameEventRequest) -> "DecisionGameEvent":
        # 把通用事件主体转换成对应事件数据
        payload_names = {
            GameEventType.PLAYER_DIED: ("player_id", "player_name"),
            GameEventType.BOSS_SPAWNED: ("boss_type_id", "boss_name"),
            GameEventType.BOSS_ENDED: ("boss_type_id", "boss_name"),
            GameEventType.BOSS_DEFEATED: ("boss_type_id", "boss_name"),
            GameEventType.SCENE_FEATURE_ENTERED: ("feature_category", "feature_name"),
            GameEventType.SCENE_FEATURE_EXITED: ("feature_category", "feature_name"),
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

        if game_event.event_type in {
            GameEventType.EQUIPMENT_CHANGED,
            GameEventType.WORLD_SESSION_ENDED,
        }:
            return cls(event_type=game_event.event_type, payload={})

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


    # 检查事件数据是否完整
    @model_validator(mode="after")
    def validate_trigger_context(self) -> "DecisionInput":
        # 每种触发都必须带上自己的核心数据
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
        # 把接口请求整理成决策节点使用的输入
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
        # 只发送当前触发真正需要的字段
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


# 模型输出检查通过后才能进入下一步
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
