from typing import Any

from pydantic import Field

from agent.decision.schema import DecisionAction
from agent.models.trigger_base import CamelModel


GAME_CONTEXT_KEYS = frozenset(
    {"player", "combat", "inventory", "progress", "scene", "world"}
)


class ToolHistoryMetadata(CamelModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str
    success: bool | None = None
    round: int | None = None
    latency_ms: float | None = None
    cache_hit: bool | None = None


class AgentExecutionResult(CamelModel):
    """内部执行结果且不改变公开响应结构"""

    message: str
    decision_action: DecisionAction
    reasoning_rounds: int = Field(ge=0)
    used_game_context: dict[str, dict[str, Any]] = Field(default_factory=dict)
    tool_history: list[ToolHistoryMetadata] = Field(default_factory=list)


def select_game_context(
    collected_context: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """仅保留六个进程内游戏快照工具的结果"""

    return {
        key: value
        for key, value in collected_context.items()
        if key in GAME_CONTEXT_KEYS and isinstance(value, dict)
    }
