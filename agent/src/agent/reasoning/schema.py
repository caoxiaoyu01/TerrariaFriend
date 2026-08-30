from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator


class ReasonerStatus(str, Enum):
    NEED_TOOL = "NEED_TOOL"
    FINAL = "FINAL"


# 仅保留旧调用方的名称引用，新工具不需要在这里登记
class GameContextToolName(str, Enum):
    GET_PLAYER_CONTEXT = "get_player_context"
    GET_COMBAT_CONTEXT = "get_combat_context"
    GET_INVENTORY_CONTEXT = "get_inventory_context"
    GET_PROGRESS_CONTEXT = "get_progress_context"
    GET_SCENE_CONTEXT = "get_scene_context"
    GET_WORLD_CONTEXT = "get_world_context"
    GET_MEMORY_CONTEXT = "get_memory_context"
    LOOKUP_TERRARIA_KNOWLEDGE = "lookup_terraria_knowledge"


class ToolCall(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)

    def arguments_dict(self) -> dict[str, object]:
        return self.arguments


TOOL_CALL_ADAPTER = TypeAdapter(ToolCall)


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
