import json
import logging
import os
import time
from pathlib import Path
from uuid import uuid4

from pydantic import Field, ValidationError

from agent.models.trigger_base import CamelModel
from agent.trace.config import RECENT_CLOSED_TRACE_LIMIT
from agent.trace.trace import Trace


logger = logging.getLogger("uvicorn.error")


class TraceRuntimeState(CamelModel):
    current_trace: Trace | None = None
    recent_closed_traces: list[Trace] = Field(default_factory=list)


class LocalTraceStore:
    """把近期记忆状态安全地保存到一个本地文件"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load_state(self) -> TraceRuntimeState:
        if not self.path.exists():
            return TraceRuntimeState()
        try:
            raw = self.path.read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("state file is empty")
            state = TraceRuntimeState.model_validate_json(raw)
            state.recent_closed_traces = state.recent_closed_traces[
                -RECENT_CLOSED_TRACE_LIMIT:
            ]
            return state
        except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exception:
            logger.warning(
                "[L1Trace] failed to restore %s; starting empty: %s",
                self.path,
                exception,
            )
            return TraceRuntimeState()

    def save_state(self, state: TraceRuntimeState) -> None:
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
                    # 杀毒或索引程序可能会短暂占用旧文件
                    time.sleep(0.01)
        finally:
            if temporary.exists():
                temporary.unlink()

    def clear_state(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
