from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


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
    LOOKUP_TERRARIA_KNOWLEDGE = "lookup_terraria_knowledge"


class WikiToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str = Field(min_length=1)
    intent: Literal[
        "general",
        "obtaining",
        "usage",
        "crafting",
        "summoning",
        "location",
        "drops",
        "mechanics",
    ] = "general"
    lang: Literal["zh", "en"] = "zh"

    @field_validator("entity")
    @classmethod
    def normalize_entity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("entity 不能为空")
        return normalized


class GameContextToolCall(BaseModel):
    name: Literal[
        GameContextToolName.GET_PLAYER_CONTEXT,
        GameContextToolName.GET_COMBAT_CONTEXT,
        GameContextToolName.GET_INVENTORY_CONTEXT,
        GameContextToolName.GET_PROGRESS_CONTEXT,
        GameContextToolName.GET_SCENE_CONTEXT,
        GameContextToolName.GET_WORLD_CONTEXT,
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)

    def arguments_dict(self) -> dict[str, object]:
        return self.arguments


class WikiKnowledgeToolCall(BaseModel):
    name: Literal[GameContextToolName.LOOKUP_TERRARIA_KNOWLEDGE]
    arguments: WikiToolArguments

    def arguments_dict(self) -> dict[str, object]:
        return self.arguments.model_dump(mode="json")


ToolCall = Annotated[
    GameContextToolCall | WikiKnowledgeToolCall,
    Field(discriminator="name"),
]
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
