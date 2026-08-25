from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ReasonerStatus(str, Enum):
    NEED_TOOL = "NEED_TOOL"
    FINAL = "FINAL"


class GameContextToolName(str, Enum):
    GET_PLAYER_CONTEXT = "get_player_context"
    GET_COMBAT_CONTEXT = "get_combat_context"
    GET_INVENTORY_CONTEXT = "get_inventory_context"
    GET_PROGRESS_CONTEXT = "get_progress_context"
    GET_SCENE_CONTEXT = "get_scene_context"
    GET_WORLD_CONTEXT = "get_world_context"


class ToolCall(BaseModel):
    name: GameContextToolName
    arguments: dict[str, Any] = Field(default_factory=dict)


class ReasonerResult(BaseModel):
    status: ReasonerStatus
    tool_calls: list[ToolCall] = Field(default_factory=list)
    answer: str | None = None

    @field_validator("answer")
    @classmethod
    def normalize_answer(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_status_fields(self) -> "ReasonerResult":
        if self.status is ReasonerStatus.NEED_TOOL:
            if not self.tool_calls:
                raise ValueError("NEED_TOOL 必须提供 tool_calls")
            if self.answer:
                raise ValueError("NEED_TOOL 不能同时提供 answer")
        elif not self.answer:
            raise ValueError("FINAL 必须提供 answer")
        return self
