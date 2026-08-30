import json
import logging
import os
import time
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from pydantic import Field, ValidationError

from agent.models.trigger_base import CamelModel
from agent.trace.episode import Episode
from agent.trace.trace import Trace, TraceStatus


logger = logging.getLogger("uvicorn.error")


class TraceFormationCheckpoint(CamelModel):
    completed_episode_ids: list[str] = Field(default_factory=list)
    failed_episode_ids: list[str] = Field(default_factory=list)
    failure_messages: dict[str, str] = Field(default_factory=dict)


class FormationCheckpointState(CamelModel):
    processed_trace_ids: list[str] = Field(default_factory=list)
    traces: dict[str, TraceFormationCheckpoint] = Field(default_factory=dict)

    def is_episode_completed(self, trace_id: str, episode_id: str) -> bool:
        checkpoint = self.traces.get(trace_id)
        return (
            checkpoint is not None
            and episode_id in checkpoint.completed_episode_ids
        )

    def is_trace_completed(self, trace: Trace) -> bool:
        return all(
            self.is_episode_completed(trace.id, episode.id)
            for episode in trace.episodes
        )


class FormationCheckpointStore:
    """只记录长期记忆处理进度 不重复保存情节内容"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load_state(self) -> FormationCheckpointState:
        if not self.path.exists():
            return FormationCheckpointState()
        try:
            return FormationCheckpointState.model_validate_json(
                self.path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exception:
            logger.warning("[L2Formation] invalid checkpoint %s: %s", self.path, exception)
            return FormationCheckpointState()

    def mark_episode_completed(self, trace_id: str, episode_id: str) -> None:
        state = self.load_state()
        checkpoint = state.traces.setdefault(trace_id, TraceFormationCheckpoint())
        if episode_id not in checkpoint.completed_episode_ids:
            checkpoint.completed_episode_ids.append(episode_id)
        if episode_id in checkpoint.failed_episode_ids:
            checkpoint.failed_episode_ids.remove(episode_id)
        checkpoint.failure_messages.pop(episode_id, None)
        self._save(state)

    def mark_episode_failed(self, trace_id: str, episode_id: str, error: str) -> None:
        state = self.load_state()
        checkpoint = state.traces.setdefault(trace_id, TraceFormationCheckpoint())
        if episode_id not in checkpoint.failed_episode_ids:
            checkpoint.failed_episode_ids.append(episode_id)
        checkpoint.failure_messages[episode_id] = error
        self._save(state)

    def mark_trace_processed(self, trace_id: str, episodes: list[Episode]) -> None:
        state = self.load_state()
        checkpoint = state.traces.setdefault(trace_id, TraceFormationCheckpoint())
        if not {episode.id for episode in episodes}.issubset(
            checkpoint.completed_episode_ids
        ):
            raise ValueError("Trace 仍有未完成 Formation 的 Episode")
        if trace_id not in state.processed_trace_ids:
            state.processed_trace_ids.append(trace_id)
        self._save(state)

    def _save(self, state: FormationCheckpointState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                state.model_dump_json(by_alias=True, indent=2),
                encoding="utf-8",
            )
            for attempt in range(3):
                try:
                    os.replace(temporary, self.path)
                    break
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.01)
        finally:
            if temporary.exists():
                temporary.unlink()


class FormationOutboxStore:
    """持久保存还没有完整写入长期记忆的 Trace"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def enqueue(self, trace: Trace) -> None:
        if trace.status is not TraceStatus.CLOSED:
            raise ValueError("Formation Outbox 只接受 CLOSED Trace")
        target = self._trace_path(trace.id)
        if target.exists():
            return
        self.path.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                trace.model_dump_json(by_alias=True, indent=2),
                encoding="utf-8",
            )
            for attempt in range(3):
                try:
                    os.replace(temporary, target)
                    break
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.01)
        finally:
            if temporary.exists():
                temporary.unlink()

    def load_pending(self) -> list[Trace]:
        if not self.path.exists():
            return []
        pending: list[Trace] = []
        for path in sorted(self.path.glob("*.json")):
            try:
                pending.append(Trace.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exception:
                logger.error("[L2Formation] invalid outbox item %s: %s", path, exception)
        return pending

    def acknowledge(self, trace_id: str) -> None:
        self._trace_path(trace_id).unlink(missing_ok=True)

    def _trace_path(self, trace_id: str) -> Path:
        name = sha256(trace_id.encode("utf-8")).hexdigest()
        return self.path / f"{name}.json"
