from agent.decision.schema import DecisionAction
from agent.reasoning.tools import create_tool_registry


class ToolPolicy:
    """保留旧构造方式，工具权限仍以 Registry 为准"""

    def __init__(self, *, wiki_mcp_enabled: bool = False) -> None:
        self.wiki_mcp_enabled = wiki_mcp_enabled
        self._registry = create_tool_registry(include_wiki=wiki_mcp_enabled)

    def allowed_tools(self, mode: DecisionAction) -> frozenset[str]:
        return frozenset(self._registry.available_tool_specs(mode))

    def is_allowed(self, mode: DecisionAction, tool_name: object) -> bool:
        name = getattr(tool_name, "value", tool_name)
        return self._registry.is_allowed(mode, str(name))
