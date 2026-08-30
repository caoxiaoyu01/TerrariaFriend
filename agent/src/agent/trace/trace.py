from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from agent.models.trigger_base import CamelModel
from agent.trace.boundary import CloseContext
from agent.trace.episode import Episode
from agent.trace.relation import EpisodeRelation


class TraceStatus(str, Enum):
    OPEN = "OPEN"
    CLOSE_READY = "CLOSE_READY"
    CLOSED = "CLOSED"


class Trace(CamelModel):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    world_id: str = Field(min_length=1)
    started_at: datetime
    ended_at: datetime | None = None
    status: TraceStatus = TraceStatus.OPEN
    episodes: list[Episode] = Field(min_length=1)
    close_context: CloseContext | None = None
    relations: list[EpisodeRelation] = Field(default_factory=list)

    @field_validator("started_at", "ended_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Trace 时间必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_state(self) -> "Trace":
        if self.started_at != self.episodes[0].started_at:
            raise ValueError("started_at 必须来自首个 Episode")
        if any(episode.world_id != self.world_id for episode in self.episodes):
            raise ValueError("Trace 只能包含同一世界的 Episode")
        if any(
            right.started_at < left.ended_at
            for left, right in zip(self.episodes, self.episodes[1:])
        ):
            raise ValueError("Episode 必须按时间顺序保存")
        if self.status in {TraceStatus.OPEN, TraceStatus.CLOSE_READY} and self.ended_at is not None:
            raise ValueError("未关闭 Trace 不能设置 ended_at")
        if self.status is TraceStatus.OPEN and self.close_context is not None:
            raise ValueError("OPEN Trace 不能设置 close_context")
        if self.status is TraceStatus.CLOSE_READY and self.close_context is None:
            raise ValueError("CLOSE_READY Trace 必须设置 close_context")
        if self.status is TraceStatus.CLOSED:
            if self.ended_at is None or self.ended_at < self.episodes[-1].ended_at:
                raise ValueError("CLOSED Trace ended_at 不能早于最后一个 Episode")
        episode_ids = {episode.id for episode in self.episodes}
        if (
            self.close_context is not None
            and self.close_context.source_episode_id not in episode_ids
        ):
            raise ValueError("CloseContext 不能引用 Trace 外部 Episode")
        if any(
            relation.source_episode_id not in episode_ids
            or relation.target_episode_id not in episode_ids
            for relation in self.relations
        ):
            raise ValueError("EpisodeRelation 不能引用 Trace 外部 Episode")
        return self

    @classmethod
    def start(cls, episode: Episode) -> "Trace":
        return cls(
            world_id=episode.world_id,
            started_at=episode.started_at,
            episodes=[episode],
        )

    def append_episode(self, episode: Episode) -> None:
        if self.status is TraceStatus.CLOSED:
            raise ValueError("CLOSED Trace 不允许 append")
        if episode.started_at < self.episodes[-1].ended_at:
            raise ValueError("Episode 不能早于当前 Trace 的最后时间")
        if episode.world_id != self.world_id:
            raise ValueError("不能把其他世界的 Episode 加入当前 Trace")
        self.episodes.append(episode)

    def close(self, *, ended_at: datetime | None = None) -> None:
        if self.status is TraceStatus.CLOSED:
            return
        close_time = ended_at or self.episodes[-1].ended_at
        if close_time.tzinfo is None or close_time.utcoffset() is None:
            raise ValueError("ended_at 必须包含时区")
        if close_time < self.episodes[-1].ended_at:
            raise ValueError("ended_at 不能早于最后一个 Episode")
        self.status = TraceStatus.CLOSED
        self.ended_at = close_time

    def add_relation(self, relation: EpisodeRelation) -> None:
        if self.status is TraceStatus.CLOSED:
            raise ValueError("CLOSED Trace 不允许添加 relation")
        episode_ids = {episode.id for episode in self.episodes}
        if (
            relation.source_episode_id not in episode_ids
            or relation.target_episode_id not in episode_ids
        ):
            raise ValueError("EpisodeRelation 端点必须属于当前 Trace")
        self.relations.append(relation)

    def mark_close_ready(self, close_context: CloseContext) -> None:
        if self.status is TraceStatus.CLOSED:
            raise ValueError("CLOSED Trace 不能进入 CLOSE_READY")
        self.status = TraceStatus.CLOSE_READY
        self.close_context = close_context
