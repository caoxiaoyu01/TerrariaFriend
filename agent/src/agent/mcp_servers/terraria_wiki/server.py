from typing import Any

from mcp.server import MCPServer

from agent.mcp_servers.terraria_wiki.errors import WikiRetrievalError
from agent.mcp_servers.terraria_wiki.models import WikiIntent, WikiLanguage
from agent.mcp_servers.terraria_wiki.retrieval_service import WikiRetrievalService


TOOL_DESCRIPTION = """可选的 Terraria Wiki 外部知识查询工具
适合查询物品获取、制作、用途、Boss 或敌怪机制、召唤条件、掉落、世界生成、地点和具体游戏规则
不用于当前生命、位置、背包、Boss 血量、天气等实时游戏状态；这些信息应使用 GameSnapshot Tools
如果模型自身知识足够可靠，不必调用此工具"""

mcp = MCPServer(
    "terraria-wiki",
    description="TerrariaFriend 的轻量 Terraria Wiki 检索服务",
)
_service = WikiRetrievalService()


@mcp.tool(description=TOOL_DESCRIPTION, structured_output=True)
async def lookup_terraria_knowledge(
    entity: str,
    intent: WikiIntent = "general",
    lang: WikiLanguage = "zh",
) -> dict[str, Any]:
    """查询一个明确 Terraria 实体或主题的紧凑 Wiki 证据"""
    try:
        result = await _service.lookup(entity, intent, lang)
    except WikiRetrievalError as exception:
        return {
            "error": {
                "code": exception.code.value,
                "message": str(exception),
            }
        }
    return result.model_dump(mode="json")


if __name__ == "__main__":
    mcp.run(transport="stdio")
