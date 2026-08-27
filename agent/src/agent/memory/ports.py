from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryEpisode(BaseModel):
    """记忆形成层接收的后端无关情节"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    body: str = Field(min_length=1)
    source: Literal["text", "json"] = "json"
    source_description: str = Field(min_length=1)
    reference_time: datetime
    group_id: str = Field(min_length=1)


class MemoryEvidenceEpisode(BaseModel):
    """最小化的 Graphiti 情节来源且不包含一级快照"""

    model_config = ConfigDict(extra="forbid")

    episode_id: str = Field(min_length=1)
    occurred_at: datetime
    group_id: str = Field(min_length=1)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at 必须包含时区")
        return value


class MemoryTriplet(BaseModel):
    """图记忆适配器接收的显式关系写入结构"""

    model_config = ConfigDict(extra="forbid")

    edge_uuid: str = Field(min_length=1)
    source_uuid: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    target_uuid: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    fact: str = Field(min_length=1)
    evidence_episode_ids: list[str] = Field(min_length=1)
    valid_at: datetime
    reference_time: datetime
    group_id: str = Field(min_length=1)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("valid_at", "reference_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Memory temporal fields 必须包含时区")
        return value


class MemoryBackend(Protocol):
    async def initialize(self) -> None: ...

    async def add_episode(self, episode: MemoryEpisode) -> Any: ...

    async def search(
        self,
        query: str,
        *,
        group_ids: list[str],
        num_results: int = 10,
    ) -> list[Any]: ...

    async def close(self) -> None: ...


class MemoryIngestionBackend(Protocol):
    async def upsert_evidence_episode(
        self,
        episode: MemoryEvidenceEpisode,
    ) -> None: ...

    async def upsert_memory_triplet(self, triplet: MemoryTriplet) -> Any: ...
