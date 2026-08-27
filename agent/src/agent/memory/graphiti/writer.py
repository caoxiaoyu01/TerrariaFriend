import logging
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, field_validator

from agent.memory.formation.schema import (
    MemoryExtractionResult,
    MemoryRelationCandidate,
)
from agent.memory.ports import (
    MemoryEvidenceEpisode,
    MemoryIngestionBackend,
    MemoryTriplet,
)
from agent.models.trigger_base import CamelModel


logger = logging.getLogger("uvicorn.error")


class MemoryIngestionContext(CamelModel):
    group_id: str = Field(min_length=1)
    evidence_episodes: list[MemoryEvidenceEpisode] = Field(default_factory=list)

    @field_validator("evidence_episodes")
    @classmethod
    def unique_evidence(cls, values: list[MemoryEvidenceEpisode]):
        ids = [value.episode_id for value in values]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence Episode ID 不能重复")
        return values


class MemoryWriteFailure(CamelModel):
    canonical_key: str
    error: str


class MemoryWriteReport(CamelModel):
    attempted: int = 0
    written: int = 0
    skipped: int = 0
    failures: list[MemoryWriteFailure] = Field(default_factory=list)


class GraphitiMemoryWriter:
    """隔离地将候选关系写入 Graphiti 且不修改一级记忆或执行提取"""

    def __init__(self, backend: MemoryIngestionBackend) -> None:
        self.backend = backend

    async def write_memory_extraction(
        self,
        result: MemoryExtractionResult,
        context: MemoryIngestionContext,
    ) -> MemoryWriteReport:
        if not result.keep or not result.relations:
            return MemoryWriteReport(skipped=len(result.relations))

        evidence_by_id = {
            episode.episode_id: episode
            for episode in context.evidence_episodes
        }
        grouped = _group_candidates(result.relations)
        report = MemoryWriteReport(
            attempted=len(grouped),
            skipped=len(result.relations) - len(grouped),
        )
        ensured_evidence: set[str] = set()

        for canonical_key, candidate in grouped.items():
            try:
                evidence = [
                    evidence_by_id[episode_id]
                    for episode_id in candidate.evidence_episode_ids
                ]
                for episode in evidence:
                    if episode.group_id != context.group_id:
                        raise ValueError("evidence group_id 与 ingestion context 不一致")
                    if episode.episode_id not in ensured_evidence:
                        await self.backend.upsert_evidence_episode(episode)
                        ensured_evidence.add(episode.episode_id)

                occurred_at = max(episode.occurred_at for episode in evidence)
                triplet = _to_triplet(
                    candidate,
                    canonical_key=canonical_key,
                    group_id=context.group_id,
                    occurred_at=occurred_at,
                )
                await self.backend.upsert_memory_triplet(triplet)
                report.written += 1
            except Exception as exception:
                logger.exception(
                    "[GraphitiMemoryWriter] relation write failed key=%s",
                    canonical_key,
                )
                report.failures.append(
                    MemoryWriteFailure(
                        canonical_key=canonical_key,
                        error=str(exception),
                    )
                )
        return report


def _group_candidates(
    candidates: list[MemoryRelationCandidate],
) -> dict[str, MemoryRelationCandidate]:
    grouped_evidence: dict[str, list[str]] = defaultdict(list)
    representatives: dict[str, MemoryRelationCandidate] = {}
    for candidate in candidates:
        key = _canonical_key(candidate)
        representatives.setdefault(key, candidate)
        grouped_evidence[key].extend(candidate.evidence_episode_ids)
    return {
        key: representative.model_copy(
            update={
                "evidence_episode_ids": list(dict.fromkeys(grouped_evidence[key]))
            }
        )
        for key, representative in representatives.items()
    }


def _canonical_key(candidate: MemoryRelationCandidate) -> str:
    normalized_object = " ".join(candidate.object.split()).casefold()
    return f"Player|{candidate.relation_type.value}|{normalized_object}"


def _to_triplet(
    candidate: MemoryRelationCandidate,
    *,
    canonical_key: str,
    group_id: str,
    occurred_at: datetime,
) -> MemoryTriplet:
    source_uuid = str(uuid5(NAMESPACE_URL, f"{group_id}|entity|Player"))
    target_uuid = str(
        uuid5(
            NAMESPACE_URL,
            f"{group_id}|entity|{' '.join(candidate.object.split()).casefold()}",
        )
    )
    edge_uuid = str(uuid5(NAMESPACE_URL, f"{group_id}|edge|{canonical_key}"))
    attributes: dict[str, Any] = {
        "canonicalKey": canonical_key,
        "relationType": candidate.relation_type.value,
        "evidenceEpisodeIds": candidate.evidence_episode_ids,
    }
    if candidate.confidence is not None:
        attributes["confidence"] = candidate.confidence
    return MemoryTriplet(
        edge_uuid=edge_uuid,
        source_uuid=source_uuid,
        source_name="Player",
        target_uuid=target_uuid,
        target_name=candidate.object,
        relation_type=candidate.relation_type.value,
        fact=f"Player {candidate.relation_type.value} {candidate.object}",
        evidence_episode_ids=candidate.evidence_episode_ids,
        valid_at=occurred_at,
        reference_time=occurred_at,
        group_id=group_id,
        attributes=attributes,
    )
