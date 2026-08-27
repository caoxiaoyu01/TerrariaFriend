from dataclasses import dataclass
from datetime import timedelta
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TraceLimits:
    max_duration: timedelta = timedelta(minutes=30)
    max_episodes: int = 30

    def __post_init__(self) -> None:
        if self.max_duration <= timedelta(0):
            raise ValueError("max_duration 必须大于 0")
        if self.max_episodes <= 0:
            raise ValueError("max_episodes 必须大于 0")


DEFAULT_TRACE_LIMITS = TraceLimits()
RECENT_CLOSED_TRACE_LIMIT = 4
DEFAULT_REORDER_WINDOW_SECONDS = 0.25
DEFAULT_REORDER_MAX_EPISODES = 32


def reorder_window_seconds() -> float:
    configured = os.getenv("TERRARIA_TRACE_REORDER_WINDOW_SECONDS")
    value = (
        float(configured)
        if configured is not None
        else DEFAULT_REORDER_WINDOW_SECONDS
    )
    if value < 0:
        raise ValueError("TERRARIA_TRACE_REORDER_WINDOW_SECONDS 不能小于 0")
    return value


def reorder_max_episodes() -> int:
    configured = os.getenv("TERRARIA_TRACE_REORDER_MAX_EPISODES")
    value = (
        int(configured)
        if configured is not None
        else DEFAULT_REORDER_MAX_EPISODES
    )
    if value <= 0:
        raise ValueError("TERRARIA_TRACE_REORDER_MAX_EPISODES 必须大于 0")
    return value


def trace_state_path() -> Path:
    """返回唯一配置的本地一级状态文件"""

    configured = os.getenv("TERRARIA_TRACE_STATE_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3] / "data" / "l1_trace_state.json"


def formation_state_path() -> Path:
    """返回独立的二级处理检查点路径"""

    configured = os.getenv("TERRARIA_FORMATION_STATE_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3] / "data" / "l2_formation_state.json"
