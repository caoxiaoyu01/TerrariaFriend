import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from agent.models.execution import AgentExecutionResult
from agent.models.trigger import TriggerRequest, TriggerType
from agent.trace.episode import Episode, build_trigger_episode
from agent.trace.config import (
    reorder_max_episodes as configured_reorder_max_episodes,
    reorder_window_seconds as configured_reorder_window_seconds,
)
from agent.trace.manager import TraceManager
from agent.trace.relevance import RelatednessChecker
from agent.trace.store import LocalTraceStore, TraceRuntimeState


logger = logging.getLogger("uvicorn.error")

if TYPE_CHECKING:
    from agent.memory.formation.runtime import MemoryFormationRuntime


@dataclass(slots=True)
class _PendingEpisode:
    episode: Episode
    arrival_sequence: int
    completion: asyncio.Future[None]


class TraceRuntime:
    """把完成的事件和回复写入近期记忆"""

    def __init__(
        self,
        store: LocalTraceStore,
        *,
        relatedness_checker: RelatednessChecker | None = None,
        formation_runtime: "MemoryFormationRuntime | None" = None,
        reorder_window_seconds: float | None = None,
        reorder_max_episodes: int | None = None,
    ) -> None:
        reorder_window_seconds = (
            reorder_window_seconds
            if reorder_window_seconds is not None
            else configured_reorder_window_seconds()
        )
        reorder_max_episodes = (
            reorder_max_episodes
            if reorder_max_episodes is not None
            else configured_reorder_max_episodes()
        )
        if reorder_window_seconds < 0:
            raise ValueError("reorder_window_seconds 不能小于 0")
        if reorder_max_episodes <= 0:
            raise ValueError("reorder_max_episodes 必须大于 0")
        self.store = store
        self.relatedness_checker = relatedness_checker
        self.formation_runtime = formation_runtime
        self.reorder_window_seconds = reorder_window_seconds
        self.reorder_max_episodes = reorder_max_episodes
        self.manager = TraceManager(relatedness_checker=relatedness_checker)
        self._lock = asyncio.Lock()
        self._pending: list[_PendingEpisode] = []
        self._arrival_sequence = 0
        self._flush_task: asyncio.Task[None] | None = None
        self._world_id: str | None = None
        self._session_id: str | None = None
        self._ended_session_ids: set[str] = set()

    async def activate_context(self, world_id: str, session_id: str) -> bool:
        async with self._lock:
            if session_id in self._ended_session_ids:
                logger.info(
                    "[L1Trace] ignored ended session world=%s session=%s",
                    world_id,
                    session_id,
                )
                return False
            if self._world_id == world_id and self._session_id == session_id:
                return True

            self._cancel_flush_task_locked()
            await self._flush_pending_locked()
            if self.manager.current_trace is not None:
                previous_closed_ids = self._closed_trace_ids()
                self.manager.close_current()
                self._save()
                self._schedule_newly_closed(previous_closed_ids)

            self.store.activate_scope(world_id)
            restored = self.store.load_state()
            self.manager = TraceManager(
                relatedness_checker=self.relatedness_checker,
                current_trace=restored.current_trace,
                recent_closed_traces=restored.recent_closed_traces,
            )
            self._world_id = world_id
            self._session_id = session_id
            logger.info(
                "[L1Trace] activated world=%s session=%s",
                world_id,
                session_id,
            )
            return True

    async def record_trigger(
        self,
        trigger: TriggerRequest,
        *,
        execution: AgentExecutionResult | None = None,
        response_occurred_at: datetime | None = None,
    ) -> Episode | None:
        if not await self.activate_context(trigger.world_id, trigger.session_id):
            return None
        if trigger.trigger_type is TriggerType.PERIODIC:
            return None
        if trigger.trigger_type is TriggerType.USER_QUERY and execution is None:
            return None
        episode = build_trigger_episode(
            trigger,
            execution=execution,
            response_occurred_at=response_occurred_at,
        )
        if episode is None:
            return None
        loop = asyncio.get_running_loop()
        completion = loop.create_future()
        async with self._lock:
            pending = _PendingEpisode(
                episode=episode,
                arrival_sequence=self._arrival_sequence,
                completion=completion,
            )
            self._arrival_sequence += 1
            self._pending.append(pending)
            if (
                self.reorder_window_seconds == 0
                or len(self._pending) >= self.reorder_max_episodes
            ):
                self._cancel_flush_task_locked()
                await self._flush_pending_locked()
            elif self._flush_task is None:
                self._flush_task = asyncio.create_task(
                    self._flush_after_window(),
                    name="l1-episode-reorder-flush",
                )
        await asyncio.shield(completion)
        return episode

    async def handle_world_session_ended(
        self,
        occurred_at: datetime,
        *,
        world_id: str,
        session_id: str,
    ) -> None:
        async with self._lock:
            self._ended_session_ids.add(session_id)
            if self._world_id != world_id or self._session_id != session_id:
                logger.info(
                    "[L1Trace] ignored stale session end world=%s session=%s",
                    world_id,
                    session_id,
                )
                return
            self._cancel_flush_task_locked()
            await self._flush_pending_locked()
            previous_closed_ids = self._closed_trace_ids()
            self.manager.handle_world_session_ended(occurred_at)
            self._save()
            self._schedule_newly_closed(previous_closed_ids)
            self._session_id = None

    def resume_closed_traces(self) -> None:
        """重新处理还没有写入长期记忆的已关闭轨迹"""

        if self.formation_runtime is None:
            return
        self.formation_runtime.resume_pending()
        for trace in self.manager.recent_closed_traces:
            self.formation_runtime.schedule(trace)

    async def shutdown(self) -> None:
        await self.flush_pending()
        if self.formation_runtime is not None:
            await self.formation_runtime.drain()

    async def flush_pending(self) -> None:
        async with self._lock:
            self._cancel_flush_task_locked()
            await self._flush_pending_locked()

    async def _flush_after_window(self) -> None:
        try:
            await asyncio.sleep(self.reorder_window_seconds)
            async with self._lock:
                self._flush_task = None
                await self._flush_pending_locked()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[L1Trace] Episode reorder flush failed")

    async def _flush_pending_locked(self) -> None:
        if not self._pending:
            return
        batch = self._pending
        self._pending = []
        batch.sort(
            key=lambda item: (
                item.episode.started_at,
                item.arrival_sequence,
            )
        )
        try:
            for item in batch:
                previous_closed_ids = self._closed_trace_ids()
                current = self.manager.current_trace
                if (
                    current is not None
                    and item.episode.started_at < current.episodes[-1].ended_at
                ):
                    logger.warning(
                        "[L1Trace] out-of-order Episode %s (%s); rotating Trace without changing fact time",
                        item.episode.id,
                        item.episode.started_at.isoformat(),
                    )
                    self.manager.close_current()
                await self.manager.append_episode(item.episode)
                self._schedule_newly_closed(previous_closed_ids)
            self._save()
        except Exception as exception:
            for item in batch:
                if not item.completion.done():
                    item.completion.set_exception(exception)
            raise
        else:
            for item in batch:
                if not item.completion.done():
                    item.completion.set_result(None)

    def _cancel_flush_task_locked(self) -> None:
        task = self._flush_task
        self._flush_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def _closed_trace_ids(self) -> set[str]:
        return {trace.id for trace in self.manager.recent_closed_traces}

    def _schedule_newly_closed(self, previous_ids: set[str]) -> None:
        if self.formation_runtime is None:
            return
        for trace in self.manager.recent_closed_traces:
            if trace.id not in previous_ids:
                self.formation_runtime.schedule(trace)

    def _save(self) -> None:
        self.store.save_state(
            TraceRuntimeState(
                current_trace=self.manager.current_trace,
                recent_closed_traces=list(self.manager.recent_closed_traces),
            )
        )
