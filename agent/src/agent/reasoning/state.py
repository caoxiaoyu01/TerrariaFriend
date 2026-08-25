from typing import Any, TypedDict

from agent.models.game_snapshot import GameSnapshot


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
