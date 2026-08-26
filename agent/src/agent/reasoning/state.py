from dataclasses import dataclass, field
from typing import Any, TypedDict

from agent.models.game_snapshot import GameSnapshot


@dataclass(slots=True)
class ReasoningRunMetrics:
    reasoning_rounds: int = 0
    reasoner_total_latency_seconds: float = 0.0
    tool_history: list[dict[str, Any]] = field(default_factory=list)


class ReasoningState(TypedDict):
    trigger: dict[str, Any]
    query: str | None
    initial_context: dict[str, Any]
    game_snapshot: GameSnapshot
    collected_context: dict[str, Any]
    tool_history: list[dict[str, Any]]
    reasoning_messages: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]]
    last_status: str | None
    final_answer: str | None
    tool_call_count: int
    reasoning_round: int
    reasoner_total_latency_seconds: float
    run_metrics: ReasoningRunMetrics
