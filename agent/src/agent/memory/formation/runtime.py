import asyncio
import logging
from collections.abc import Awaitable, Callable

from agent.memory.formation.extractor import MemoryExtractor
from agent.memory.formation.schema import MemoryExtractionInput
from agent.memory.formation.store import FormationCheckpointStore, FormationOutboxStore
from agent.memory.graphiti.writer import GraphitiMemoryWriter, MemoryIngestionContext
from agent.memory.ports import MemoryEvidenceEpisode
from agent.trace.episode import Episode
from agent.trace.trace import Trace, TraceStatus


logger = logging.getLogger("uvicorn.error")
MAX_EPISODE_ATTEMPTS = 2


class MemoryFormationRuntime:
    """在后台把已关闭的近期记忆整理成长期记忆"""

    def __init__(
        self,
        extractor: MemoryExtractor,
        writer: GraphitiMemoryWriter,
        checkpoint_store: FormationCheckpointStore,
        outbox_store: FormationOutboxStore | None = None,
        *,
        group_id: str | None = None,
        group_id_factory: Callable[[str], str] | None = None,
        initialize_backend: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        if (group_id is None) == (group_id_factory is None):
            raise ValueError("group_id 和 group_id_factory 必须且只能提供一个")
        self.extractor = extractor
        self.writer = writer
        self.checkpoint_store = checkpoint_store
        self.outbox_store = outbox_store or FormationOutboxStore(
            checkpoint_store.path.with_name(
                f"{checkpoint_store.path.stem}_outbox"
            )
        )
        self.group_id = group_id
        self.group_id_factory = group_id_factory
        self.initialize_backend = initialize_backend
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._backend_initialized = initialize_backend is None
        self._backend_lock = asyncio.Lock()

    def schedule(self, trace: Trace) -> None:
        if trace.status is not TraceStatus.CLOSED:
            return
        state = self.checkpoint_store.load_state()
        if state.is_trace_completed(trace):
            self.outbox_store.acknowledge(trace.id)
            return
        self.outbox_store.enqueue(trace)
        if trace.id in self._tasks:
            return
        task = asyncio.create_task(
            self.process_trace(trace.model_copy(deep=True)),
            name=f"memory-formation-{trace.id}",
        )
        self._tasks[trace.id] = task
        task.add_done_callback(lambda completed, trace_id=trace.id: self._finish_task(trace_id, completed))

    async def process_trace(self, trace: Trace) -> None:
        if trace.status is not TraceStatus.CLOSED:
            return
        async with self._locks.setdefault(trace.id, asyncio.Lock()):
            state = self.checkpoint_store.load_state()
            if state.is_trace_completed(trace):
                self.outbox_store.acknowledge(trace.id)
                return
            episode_by_id = {episode.id: episode for episode in trace.episodes}
            for episode in trace.episodes:
                state = self.checkpoint_store.load_state()
                if state.is_episode_completed(trace.id, episode.id):
                    continue
                await self._process_episode(trace, episode, episode_by_id)
            state = self.checkpoint_store.load_state()
            if state.is_trace_completed(trace):
                self.checkpoint_store.mark_trace_processed(trace.id, trace.episodes)
                self.outbox_store.acknowledge(trace.id)

    def resume_pending(self) -> None:
        for trace in self.outbox_store.load_pending():
            self.schedule(trace)

    async def _process_episode(
        self,
        trace: Trace,
        episode: Episode,
        episode_by_id: dict[str, Episode],
    ) -> None:
        relations = [
            relation
            for relation in trace.relations
            if relation.source_episode_id == episode.id
        ]
        target_ids = {relation.target_episode_id for relation in relations}
        if len(target_ids) > 1:
            self.checkpoint_store.mark_episode_failed(
                trace.id,
                episode.id,
                "Episode has multiple CONTINUES targets",
            )
            logger.error(
                "[L2Formation] trace=%s episode=%s has multiple CONTINUES targets",
                trace.id,
                episode.id,
            )
            return
        related = episode_by_id[next(iter(target_ids))] if target_ids else None
        extraction_input = MemoryExtractionInput(
            episode=episode,
            related_episode_context=related,
            episode_relations=relations,
        )

        result = None
        last_error: Exception | None = None
        for _ in range(MAX_EPISODE_ATTEMPTS):
            try:
                result = await self.extractor.extract(extraction_input)
                break
            except Exception as exception:
                last_error = exception
                logger.exception(
                    "[L2Formation] trace=%s episode=%s extraction attempt failed",
                    trace.id,
                    episode.id,
                )
        if result is None:
            self.checkpoint_store.mark_episode_failed(trace.id, episode.id, str(last_error))
            return
        if not result.keep:
            self.checkpoint_store.mark_episode_completed(trace.id, episode.id)
            return

        evidence_ids = {
            evidence_id
            for candidate in result.relations
            for evidence_id in candidate.evidence_episode_ids
        }
        group_id = self._group_id(trace.world_id)
        context = MemoryIngestionContext(
            group_id=group_id,
            evidence_episodes=[
                MemoryEvidenceEpisode(
                    episode_id=evidence_id,
                    occurred_at=episode_by_id[evidence_id].started_at,
                    group_id=group_id,
                )
                for evidence_id in evidence_ids
            ],
        )
        for _ in range(MAX_EPISODE_ATTEMPTS):
            try:
                await self._ensure_backend()
                report = await self.writer.write_memory_extraction(result, context)
                if report.failures:
                    raise RuntimeError(
                        "; ".join(failure.error for failure in report.failures)
                    )
                self.checkpoint_store.mark_episode_completed(trace.id, episode.id)
                return
            except Exception as exception:
                last_error = exception
                logger.exception(
                    "[L2Formation] trace=%s episode=%s write attempt failed",
                    trace.id,
                    episode.id,
                )
        self.checkpoint_store.mark_episode_failed(trace.id, episode.id, str(last_error))

    def _group_id(self, world_id: str) -> str:
        if self.group_id_factory is not None:
            return self.group_id_factory(world_id)
        if self.group_id is None:
            raise RuntimeError("长期记忆缺少世界分组")
        return self.group_id

    async def _ensure_backend(self) -> None:
        if self._backend_initialized:
            return
        async with self._backend_lock:
            if not self._backend_initialized:
                await self.initialize_backend()
                self._backend_initialized = True

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    @property
    def backend_initialized(self) -> bool:
        return self._backend_initialized

    def _finish_task(self, trace_id: str, task: asyncio.Task[None]) -> None:
        self._tasks.pop(trace_id, None)
        try:
            task.result()
        except Exception:
            logger.exception("[L2Formation] trace=%s formation failed", trace_id)
