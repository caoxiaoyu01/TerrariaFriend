import logging
import time
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator

from agent.llm.client import RoleLLMClient, parse_json_object
from agent.models.trigger_base import CamelModel
from agent.trace.episode import Episode
from agent.trace.schema import TraceOrigin
from agent.trace.store import LocalTraceStore


RECENT_MEMORY_TOP_K = 3
RECENT_MEMORY_MIN_SCORE = 0.5
LONG_TERM_MEMORY_TOP_K = 10
MEMORY_TOOL_DESCRIPTION = "查询玩家历史记忆"


logger = logging.getLogger("uvicorn.error")


RECENT_MEMORY_RELEVANCE_PROMPT = """
你负责判断玩家查询与近期 Terraria 记忆的相关程度
输入包含查询和若干完整情节的轻量表示
请为相关情节返回零到一之间的分数
只返回确实有助于回答当前查询的情节
不要回答查询也不要改写情节内容
""".strip()


class MemoryEvent(CamelModel):
    type: str
    content: str


class RecentMemoryEpisode(CamelModel):
    episode_id: str
    episode_type: str
    started_at: str
    primary_entity: str | None = None
    events: list[MemoryEvent] = Field(min_length=1)


class RecentMemoryScore(CamelModel):
    episode_id: str
    score: float

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("score 必须位于 0 到 1 之间")
        return value


class RecentMemoryScores(CamelModel):
    results: list[RecentMemoryScore] = Field(default_factory=list)


class RecentMemoryMatch(CamelModel):
    score: float
    episode_id: str
    episode_type: str
    started_at: str
    primary_entity: str | None = None
    events: list[MemoryEvent] = Field(min_length=1)


class LongTermMemoryMatch(CamelModel):
    subject: str
    relation: str
    object: str
    evidence_episode_ids: list[str] = Field(default_factory=list)
    relevance_score: float | None = None


class MemoryContextResult(CamelModel):
    recent_memory: list[RecentMemoryMatch] = Field(default_factory=list)
    long_term_memory: list[LongTermMemoryMatch] = Field(default_factory=list)


class MemoryToolArguments(CamelModel):
    query: str = Field(min_length=1)
    scope: Literal["recent", "long_term", "both"] = "recent"


class SemanticMemoryBackend(Protocol):
    async def search(
        self,
        query: str,
        *,
        group_ids: list[str],
        num_results: int = 10,
    ) -> list[Any]: ...


class RecentMemoryRetriever:
    def __init__(
        self,
        store: LocalTraceStore,
        model_client: RoleLLMClient,
        *,
        top_k: int = RECENT_MEMORY_TOP_K,
        min_score: float = RECENT_MEMORY_MIN_SCORE,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if not 0 <= min_score <= 1:
            raise ValueError("min_score 必须位于 0 到 1 之间")
        if model_client.config.enable_thinking:
            raise ValueError("近期记忆相关性模型必须关闭思考模式")
        self.store = store
        self.model_client = model_client
        self.top_k = top_k
        self.min_score = min_score

    async def retrieve(self, query: str) -> list[RecentMemoryMatch]:
        candidates = self._load_candidates()
        if not candidates:
            logger.info(
                "[MemoryRelevance] candidates=0 selected=0 threshold=%.2f top_k=%d",
                self.min_score,
                self.top_k,
            )
            return []
        completion = await self.model_client.generate_structured(
            system_prompt=RECENT_MEMORY_RELEVANCE_PROMPT,
            input_data={
                "query": query,
                "candidate_episodes": [
                    candidate.model_dump(mode="json", by_alias=True)
                    for candidate in candidates
                ],
            },
            output_schema=RecentMemoryScores.model_json_schema(),
        )
        scores = RecentMemoryScores.model_validate(
            parse_json_object(completion.content)
        )
        candidate_by_id = {
            candidate.episode_id: candidate for candidate in candidates
        }
        best_by_id: dict[str, float] = {}
        for result in scores.results:
            if result.episode_id not in candidate_by_id:
                continue
            if result.score < self.min_score:
                continue
            best_by_id[result.episode_id] = max(
                result.score,
                best_by_id.get(result.episode_id, 0),
            )
        ranked = sorted(
            best_by_id.items(),
            key=lambda item: item[1],
            reverse=True,
        )[: self.top_k]
        matches = [
            RecentMemoryMatch(
                score=score,
                **candidate_by_id[episode_id].model_dump(),
            )
            for episode_id, score in ranked
        ]
        logger.info(
            "[MemoryRelevance] candidates=%d selected=%d threshold=%.2f top_k=%d",
            len(candidates),
            len(matches),
            self.min_score,
            self.top_k,
        )
        for match in matches:
            logger.info(
                "[MemoryHit] source=L1 episode_id=%s type=%s score=%.3f",
                match.episode_id,
                match.episode_type,
                match.score,
            )
        return matches

    def _load_candidates(self) -> list[RecentMemoryEpisode]:
        state = self.store.load_state()
        traces = [*state.recent_closed_traces]
        if state.current_trace is not None:
            traces.append(state.current_trace)
        return [
            _project_episode(episode)
            for trace in traces
            for episode in trace.episodes
        ]


class LongTermMemoryRetriever:
    def __init__(
        self,
        backend: SemanticMemoryBackend,
        *,
        group_id: str,
        top_k: int = LONG_TERM_MEMORY_TOP_K,
    ) -> None:
        self.backend = backend
        self.group_id = group_id
        self.top_k = top_k

    async def retrieve(self, query: str) -> list[LongTermMemoryMatch]:
        results = await self.backend.search(
            query,
            group_ids=[self.group_id],
            num_results=self.top_k,
        )
        matches = [
            match
            for item in results
            if (match := _project_long_term_result(item)) is not None
        ]
        for match in matches:
            logger.info(
                "[MemoryHit] source=L2 relation=%s object=%s relevance_score=%s",
                match.relation,
                match.object,
                (
                    f"{match.relevance_score:.3f}"
                    if match.relevance_score is not None
                    else "none"
                ),
            )
        return matches


class MemoryContextTool:
    def __init__(
        self,
        recent: RecentMemoryRetriever,
        long_term: LongTermMemoryRetriever,
    ) -> None:
        self.recent = recent
        self.long_term = long_term

    async def get_memory_context(
        self,
        query: str,
        scope: Literal["recent", "long_term", "both"] = "recent",
    ) -> MemoryContextResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query 不能为空")
        started_at = time.perf_counter()
        logger.info(
            '[MemoryTool] query="%s" scope=%s',
            normalized_query,
            scope,
        )
        if scope == "recent":
            result = MemoryContextResult(
                recent_memory=await self.recent.retrieve(normalized_query)
            )
        elif scope == "long_term":
            result = MemoryContextResult(
                long_term_memory=await self.long_term.retrieve(normalized_query)
            )
        else:
            recent_memory = await self.recent.retrieve(normalized_query)
            long_term_memory = await self.long_term.retrieve(normalized_query)
            result = MemoryContextResult(
                recent_memory=recent_memory,
                long_term_memory=long_term_memory,
            )
        logger.info(
            "[MemoryTool] completed recent=%d long_term=%d latency=%.3fs",
            len(result.recent_memory),
            len(result.long_term_memory),
            time.perf_counter() - started_at,
        )
        return result


def _project_episode(episode: Episode) -> RecentMemoryEpisode:
    primary_entity = next(
        (
            event.capsule.primary_entity.entity_name
            or event.capsule.primary_entity.entity_id
            for event in episode.events
            if event.capsule.primary_entity is not None
            and (
                event.capsule.primary_entity.entity_name
                or event.capsule.primary_entity.entity_id
            )
        ),
        None,
    )
    return RecentMemoryEpisode(
        episode_id=episode.id,
        episode_type=episode.episode_type.value,
        started_at=episode.started_at.isoformat(),
        primary_entity=primary_entity,
        events=[_project_event(event) for event in episode.events],
    )


def _project_event(event: Any) -> MemoryEvent:
    event_type = event.capsule.source_event_type
    if event.trace_metadata.origin is TraceOrigin.RESPONSE or event_type == "USER_QUERY":
        content = str(event.capsule.data.content)
    else:
        entity = event.capsule.primary_entity
        content = (
            entity.entity_name or entity.entity_id
            if entity is not None
            else event_type
        )
    return MemoryEvent(type=event_type, content=content)


def _project_long_term_result(item: Any) -> LongTermMemoryMatch | None:
    relation = str(getattr(item, "name", "") or "").strip()
    fact = str(getattr(item, "fact", "") or "").strip()
    attributes = getattr(item, "attributes", None) or {}
    relation = str(attributes.get("relationType") or relation).strip()
    if not relation:
        return None
    subject = "Player"
    prefix = f"{subject} {relation} "
    object_name = fact[len(prefix):].strip() if fact.startswith(prefix) else ""
    if not object_name:
        canonical_key = str(attributes.get("canonicalKey") or "")
        parts = canonical_key.split("|", 2)
        object_name = parts[2] if len(parts) == 3 else fact
    if not object_name:
        return None
    evidence = list(
        getattr(item, "episodes", None)
        or attributes.get("evidenceEpisodeIds")
        or []
    )
    score = _optional_score(item)
    return LongTermMemoryMatch(
        subject=subject,
        relation=relation,
        object=object_name,
        evidence_episode_ids=evidence,
        relevance_score=score,
    )


def _optional_score(item: Any) -> float | None:
    for name in ("score", "relevance_score", "reranker_score"):
        value = getattr(item, name, None)
        if isinstance(value, (int, float)):
            return float(value)
    return None
