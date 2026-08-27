from datetime import datetime
from collections import deque
from collections.abc import Iterable

from agent.trace.boundary import BoundaryAction, TraceBoundaryPolicy
from agent.trace.config import (
    DEFAULT_TRACE_LIMITS,
    RECENT_CLOSED_TRACE_LIMIT,
    TraceLimits,
)
from agent.trace.episode import Episode
from agent.trace.relevance import RelatednessChecker
from agent.trace.relation import EpisodeRelation, EpisodeRelationType
from agent.trace.trace import Trace, TraceStatus


class TraceManager:
    """管理完整情节上的硬限制和显式自然边界"""

    def __init__(
        self,
        limits: TraceLimits = DEFAULT_TRACE_LIMITS,
        *,
        boundary_policy: TraceBoundaryPolicy | None = None,
        relatedness_checker: RelatednessChecker | None = None,
        current_trace: Trace | None = None,
        recent_closed_traces: Iterable[Trace] = (),
    ) -> None:
        self.limits = limits
        self.boundary_policy = boundary_policy or TraceBoundaryPolicy()
        self.relatedness_checker = relatedness_checker
        self.current_trace = current_trace
        self.recent_closed_traces: deque[Trace] = deque(
            recent_closed_traces,
            maxlen=RECENT_CLOSED_TRACE_LIMIT,
        )
        self._validate_restored_state()

    @property
    def closed_traces(self) -> list[Trace]:
        """有限近期历史的兼容别名"""

        return list(self.recent_closed_traces)

    async def append_episode(self, episode: Episode) -> Trace | None:
        current = self.current_trace
        if current is None:
            return self._start_and_apply_boundary(episode)

        self._require_chronological(current, episode)

        # 硬限制始终优先包括等待关闭状态
        if self._must_split_before(episode):
            self._archive_current()
            return self._start_and_apply_boundary(episode)

        if current.status is TraceStatus.CLOSE_READY:
            return await self._append_after_close_ready(current, episode)

        current.append_episode(episode)
        self._apply_boundary(current, episode)
        return self.current_trace

    def handle_world_session_ended(self, occurred_at: datetime) -> None:
        """消费同步卸载信号且不虚构情节"""

        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("occurred_at 必须包含时区")
        if self.current_trace is not None:
            self._archive_current(ended_at=occurred_at)

    def close_current(self) -> None:
        """如果当前窗口存在则在最后事实时间关闭"""

        self._archive_current()

    async def _append_after_close_ready(
        self,
        current: Trace,
        episode: Episode,
    ) -> Trace | None:
        close_context = current.close_context
        if close_context is None:
            raise RuntimeError("CLOSE_READY Trace 缺少 CloseContext")

        user_query = self.boundary_policy.user_query(episode)
        if user_query is not None:
            if self.relatedness_checker is None:
                raise RuntimeError("CLOSE_READY USER_QUERY 缺少 relatedness checker")
            result = await self.relatedness_checker(close_context, user_query)
            if result.related:
                current.append_episode(episode)
                current.add_relation(
                    EpisodeRelation(
                        source_episode_id=episode.id,
                        target_episode_id=close_context.source_episode_id,
                        relation_type=EpisodeRelationType.CONTINUES,
                        resolved_references=result.resolved_references,
                    )
                )
                return current
            self._archive_current()
            return self._start_and_apply_boundary(episode)

        if self.boundary_policy.is_deterministic_continuation(
            close_context,
            episode,
        ):
            current.append_episode(episode)
            return current

        self._archive_current()
        return self._start_and_apply_boundary(episode)

    def _start_and_apply_boundary(self, episode: Episode) -> Trace | None:
        self.current_trace = Trace.start(episode)
        self._apply_boundary(self.current_trace, episode)
        return self.current_trace

    def _apply_boundary(self, trace: Trace, episode: Episode) -> None:
        evaluation = self.boundary_policy.evaluate(episode)
        if evaluation.action is BoundaryAction.CLOSE_READY:
            if evaluation.close_context is None:
                raise RuntimeError("CLOSE_READY boundary 缺少 CloseContext")
            trace.mark_close_ready(evaluation.close_context)
        elif evaluation.action is BoundaryAction.CLOSE:
            self._archive_current()

    def _archive_current(self, *, ended_at: datetime | None = None) -> None:
        current = self.current_trace
        if current is None:
            return
        current.close(ended_at=ended_at)
        self.recent_closed_traces.append(current)
        self.current_trace = None

    def _validate_restored_state(self) -> None:
        if self.current_trace is not None and self.current_trace.status is TraceStatus.CLOSED:
            raise ValueError("current_trace 不能是 CLOSED")
        if any(trace.status is not TraceStatus.CLOSED for trace in self.recent_closed_traces):
            raise ValueError("recent_closed_traces 只能包含 CLOSED Trace")

    @staticmethod
    def _require_chronological(current: Trace, episode: Episode) -> None:
        if episode.started_at < current.episodes[-1].ended_at:
            raise ValueError("Episode 必须按时间顺序 append")

    def _must_split_before(self, episode: Episode) -> bool:
        current = self.current_trace
        if current is None:
            return False
        return (
            len(current.episodes) >= self.limits.max_episodes
            or episode.ended_at - current.started_at >= self.limits.max_duration
        )
