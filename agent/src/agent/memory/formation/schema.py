from enum import Enum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from agent.models.trigger_base import CamelModel
from agent.trace.episode import Episode
from agent.trace.relation import EpisodeRelation, EpisodeRelationType


class MemoryRelationType(str, Enum):
    PREFERS = "PREFERS"
    DISLIKES = "DISLIKES"
    WANTS = "WANTS"
    USES = "USES"
    TRIED = "TRIED"
    DEFEATED = "DEFEATED"
    FAILED_AGAINST = "FAILED_AGAINST"
    VISITED = "VISITED"
    ASKED_ABOUT = "ASKED_ABOUT"
    CHANGED_TO = "CHANGED_TO"


class MemoryRelationCandidate(CamelModel):
    subject: Literal["Player"]
    relation_type: MemoryRelationType
    object: str = Field(min_length=1, max_length=200)
    evidence_episode_ids: list[str] = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("object")
    @classmethod
    def normalize_object(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("object 不能为空")
        return normalized

    @field_validator("evidence_episode_ids")
    @classmethod
    def normalize_evidence_ids(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values))
        if not normalized or any(not value for value in normalized):
            raise ValueError("evidence_episode_ids 不能为空")
        return normalized


class MemoryExtractionResult(CamelModel):
    keep: bool
    relations: list[MemoryRelationCandidate] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason 不能为空")
        return normalized

    @model_validator(mode="after")
    def require_consistent_keep(self) -> "MemoryExtractionResult":
        if not self.keep:
            self.relations = []
        elif not self.relations:
            raise ValueError("keep=true 时必须至少包含一条 relation")
        return self


class MemoryExtractionInput(CamelModel):
    episode: Episode
    related_episode_context: Episode | None = None
    episode_relations: list[EpisodeRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_context_membership(self) -> "MemoryExtractionInput":
        if any(
            relation.relation_type is not EpisodeRelationType.CONTINUES
            or relation.source_episode_id != self.episode.id
            for relation in self.episode_relations
        ):
            raise ValueError("只允许当前 Episode 发出的 CONTINUES relation")
        if self.episode_relations and self.related_episode_context is None:
            raise ValueError("CONTINUES relation 需要 target Episode context")
        if self.related_episode_context is not None and not self.episode_relations:
            raise ValueError("没有 CONTINUES relation 时不得附加 Episode context")
        if self.related_episode_context is not None and any(
            relation.target_episode_id != self.related_episode_context.id
            for relation in self.episode_relations
        ):
            raise ValueError("related_episode_context 必须匹配 relation target")
        return self
