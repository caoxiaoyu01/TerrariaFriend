from enum import Enum

from pydantic import Field, field_validator

from agent.models.trigger_base import CamelModel


class EpisodeRelationType(str, Enum):
    CONTINUES = "CONTINUES"


class ResolvedReference(CamelModel):
    mention: str = Field(min_length=1)
    resolved_entity: str = Field(min_length=1)

    @field_validator("mention", "resolved_entity")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("resolved reference 不能为空")
        return normalized


class EpisodeRelation(CamelModel):
    source_episode_id: str = Field(min_length=1)
    target_episode_id: str = Field(min_length=1)
    relation_type: EpisodeRelationType
    resolved_references: list[ResolvedReference] = Field(default_factory=list)

    @field_validator("source_episode_id", "target_episode_id")
    @classmethod
    def normalize_episode_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Episode ID 不能为空")
        return normalized
