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

REASON_ALLOWED_TOOLS = frozenset(GameContextToolName)


class ToolPolicy:
    def is_allowed(
        self,
        mode: DecisionAction,
        tool_name: GameContextToolName,
    ) -> bool:
        allowed_tools = {
            DecisionAction.RESPOND: RESPOND_ALLOWED_TOOLS,
            DecisionAction.REASON: REASON_ALLOWED_TOOLS,
        }.get(mode, frozenset())
        allowed = tool_name in allowed_tools
        logger.info(
            "[ToolPolicy] mode=%s tool=%s allowed=%s",
            mode.value,
            tool_name.value,
            str(allowed).lower(),
        )
        return allowed
