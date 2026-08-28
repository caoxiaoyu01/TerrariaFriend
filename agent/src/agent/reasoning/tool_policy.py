import logging

from agent.decision.schema import DecisionAction
from agent.reasoning.schema import GameContextToolName


logger = logging.getLogger("uvicorn.error")


RESPOND_ALLOWED_TOOLS = frozenset(
    {
        GameContextToolName.GET_PLAYER_CONTEXT,
        GameContextToolName.GET_COMBAT_CONTEXT,
        GameContextToolName.GET_SCENE_CONTEXT,
        GameContextToolName.GET_WORLD_CONTEXT,
    }
)

REASON_ALLOWED_TOOLS = frozenset(
    {
        GameContextToolName.GET_PLAYER_CONTEXT,
        GameContextToolName.GET_COMBAT_CONTEXT,
        GameContextToolName.GET_INVENTORY_CONTEXT,
        GameContextToolName.GET_PROGRESS_CONTEXT,
        GameContextToolName.GET_SCENE_CONTEXT,
        GameContextToolName.GET_WORLD_CONTEXT,
        GameContextToolName.GET_MEMORY_CONTEXT,
    }
)


class ToolPolicy:
    def __init__(self, *, wiki_mcp_enabled: bool = False) -> None:
        self.wiki_mcp_enabled = wiki_mcp_enabled

    def allowed_tools(
        self,
        mode: DecisionAction,
    ) -> frozenset[GameContextToolName]:
        if mode is DecisionAction.RESPOND:
            return RESPOND_ALLOWED_TOOLS
        if mode is not DecisionAction.REASON:
            return frozenset()
        if self.wiki_mcp_enabled:
            return REASON_ALLOWED_TOOLS | {
                GameContextToolName.LOOKUP_TERRARIA_KNOWLEDGE
            }
        return REASON_ALLOWED_TOOLS

    def is_allowed(
        self,
        mode: DecisionAction,
        tool_name: GameContextToolName,
    ) -> bool:
        allowed = tool_name in self.allowed_tools(mode)
        logger.info(
            "[ToolPolicy] mode=%s tool=%s allowed=%s",
            mode.value,
            tool_name.value,
            str(allowed).lower(),
        )
        return allowed
