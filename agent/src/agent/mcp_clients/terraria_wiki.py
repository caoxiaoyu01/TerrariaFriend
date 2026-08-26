import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Callable

from mcp import ClientSession, StdioServerParameters, stdio_client


WIKI_TOOL_NAME = "lookup_terraria_knowledge"
DEFAULT_TIMEOUT_SECONDS = 15.0
_AGENT_ROOT = Path(__file__).resolve().parents[3]


class TerrariaWikiMCPError(RuntimeError):
    pass


class TerrariaWikiMCPClient:
    """复用同一个 stdio MCP 会话调用 Terraria Wiki 工具"""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        stdio_factory: Callable[..., Any] = stdio_client,
        session_factory: Callable[..., Any] = ClientSession,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._stdio_factory = stdio_factory
        self._session_factory = session_factory
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    @property
    def is_started(self) -> bool:
        return self._session is not None

    async def start(self) -> None:
        if self._session is not None:
            return

        stack = AsyncExitStack()
        try:
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "agent.mcp_servers.terraria_wiki.server"],
                cwd=_AGENT_ROOT,
            )
            read_stream, write_stream = await stack.enter_async_context(
                self._stdio_factory(parameters)
            )
            session = await stack.enter_async_context(
                self._session_factory(read_stream, write_stream)
            )
            await asyncio.wait_for(
                session.initialize(),
                timeout=self._timeout_seconds,
            )
        except Exception as exception:
            await stack.aclose()
            raise TerrariaWikiMCPError(
                f"Terraria Wiki MCP 启动失败: {exception}"
            ) from exception

        self._stack = stack
        self._session = session

    async def lookup_terraria_knowledge(
        self,
        *,
        entity: str,
        intent: str = "general",
        lang: str = "zh",
    ) -> dict[str, Any]:
        if self._session is None:
            raise TerrariaWikiMCPError("Terraria Wiki MCP 尚未连接")

        arguments = {"entity": entity, "intent": intent, "lang": lang}
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(WIKI_TOOL_NAME, arguments),
                timeout=self._timeout_seconds,
            )
        except Exception as exception:
            raise TerrariaWikiMCPError(
                f"Terraria Wiki MCP 调用失败: {exception}"
            ) from exception

        if result.is_error:
            raise TerrariaWikiMCPError(_content_text(result.content))

        payload = result.structured_content
        if payload is None:
            payload = _parse_text_payload(result.content)
        if not isinstance(payload, dict):
            raise TerrariaWikiMCPError("Terraria Wiki MCP 返回了无效结果")

        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code", "WIKI_ERROR")
            message = error.get("message", "Wiki 查询失败")
            raise TerrariaWikiMCPError(f"{code}: {message}")
        return payload

    async def aclose(self) -> None:
        stack = self._stack
        self._session = None
        self._stack = None
        if stack is not None:
            await stack.aclose()


def create_terraria_wiki_mcp_client(
    enabled: bool,
) -> TerrariaWikiMCPClient | None:
    return TerrariaWikiMCPClient() if enabled else None


def _parse_text_payload(content: list[Any]) -> Any:
    text = _content_text(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exception:
        raise TerrariaWikiMCPError(
            "Terraria Wiki MCP 未返回结构化 JSON"
        ) from exception


def _content_text(content: list[Any]) -> str:
    texts = [block.text for block in content if hasattr(block, "text")]
    return "\n".join(texts) or "Terraria Wiki MCP 返回错误"
