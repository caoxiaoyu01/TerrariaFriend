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
    """连接已完成事务与持久一级状态的轻量运行时桥梁"""

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
        self.formation_runtime = formation_runtime
        self.reorder_window_seconds = reorder_window_seconds
        self.reorder_max_episodes = reorder_max_episodes
        restored = store.load_state()
        try:
            self.manager = TraceManager(
                relatedness_checker=relatedness_checker,
                current_trace=restored.current_trace,
                recent_closed_traces=restored.recent_closed_traces,
            )
        except ValueError as exception:
            logger.warning("[L1Trace] invalid restored state; starting empty: %s", exception)
            self.manager = TraceManager(relatedness_checker=relatedness_checker)
        self._lock = asyncio.Lock()
        self._pending: list[_PendingEpisode] = []
        self._arrival_sequence = 0
        self._flush_task: asyncio.Task[None] | None = None

    async def record_trigger(
        self,
        trigger: TriggerRequest,
        *,
        execution: AgentExecutionResult | None = None,
        response_occurred_at: datetime | None = None,
    ) -> Episode | None:
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

    async def handle_world_session_ended(self, occurred_at: datetime) -> None:
        async with self._lock:
            self._cancel_flush_task_locked()
            await self._flush_pending_locked()
            previous_closed_ids = self._closed_trace_ids()
            self.manager.handle_world_session_ended(occurred_at)
            self._save()
            self._schedule_newly_closed(previous_closed_ids)

    def resume_closed_traces(self) -> None:
        """仅恢复尚未被二级检查点覆盖的已关闭轨迹"""

        if self.formation_runtime is None:
            return
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
