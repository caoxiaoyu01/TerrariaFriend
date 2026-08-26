from typing import Any
from urllib.parse import quote

import httpx

from agent.mcp_servers.terraria_wiki.errors import WikiErrorCode, WikiRetrievalError
from agent.mcp_servers.terraria_wiki.models import (
    RawWikiPage,
    ResolvedWikiPage,
    SearchCandidate,
    WikiLanguage,
)

# 泰拉维基
WIKI_API_URLS: dict[WikiLanguage, str] = {
    "zh": "https://terraria.wiki.gg/zh/api.php",
    "en": "https://terraria.wiki.gg/api.php",
}


class WikiClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"User-Agent": "TerrariaFriend/0.1 Wiki MCP"},
            follow_redirects=True,
        )

    async def lookup_exact(
        self,
        entity: str,
        lang: WikiLanguage,
    ) -> ResolvedWikiPage | None:
        data = await self._request_json(
            lang,
            {
                "action": "query",
                "titles": entity,
                "redirects": "1",
                "prop": "info",
                "inprop": "url",
                "format": "json",
                "formatversion": "2",
            },
        )
        pages = data.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing") is True:
            return None

        page = pages[0]
        redirects = data.get("query", {}).get("redirects", [])
        redirect_info = None
        if redirects:
            redirect_info = {
                "from": redirects[-1].get("from", entity),
                "to": redirects[-1].get("to", page["title"]),
            }
        return ResolvedWikiPage(
            title=page["title"],
            page_id=page["pageid"],
            lang=lang,
            source_url=page.get("fullurl") or self._page_url(page["title"], lang),
            redirect_info=redirect_info,
        )

    async def search(
        self,
        entity: str,
        lang: WikiLanguage,
        *,
        limit: int = 5,
    ) -> tuple[SearchCandidate, ...]:
        data = await self._request_json(
            lang,
            {
                "action": "query",
                "list": "search",
                "srsearch": entity,
                "srlimit": str(limit),
                "srprop": "",
                "format": "json",
                "formatversion": "2",
            },
        )
        return tuple(
            SearchCandidate(title=item["title"], page_id=item["pageid"])
            for item in data.get("query", {}).get("search", [])
        )

    async def resolve_search_candidate(
        self,
        candidate: SearchCandidate,
        lang: WikiLanguage,
    ) -> ResolvedWikiPage | None:
        return await self.lookup_exact(candidate.title, lang)

    async def fetch_page(self, page: ResolvedWikiPage) -> RawWikiPage:
        data = await self._request_json(
            page.lang,
            {
                "action": "parse",
                "pageid": str(page.page_id),
                "prop": "text|revid",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            },
        )
        parsed = data.get("parse")
        if not isinstance(parsed, dict) or not isinstance(parsed.get("text"), str):
            raise WikiRetrievalError(
                WikiErrorCode.WIKI_PARSE_ERROR,
                f"Wiki 页面 {page.title} 缺少可解析正文",
            )
        return RawWikiPage(
            title=parsed.get("title") or page.title,
            lang=page.lang,
            html=parsed["text"],
            source_url=page.source_url,
            revision_id=parsed.get("revid"),
        )

    async def _request_json(
        self,
        lang: WikiLanguage,
        params: dict[str, str],
    ) -> dict[str, Any]:
        try:
            response = await self._client.get(WIKI_API_URLS[lang], params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exception:
            raise WikiRetrievalError(
                WikiErrorCode.WIKI_TIMEOUT,
                "Terraria Wiki 请求超时",
            ) from exception
        except (httpx.HTTPError, ValueError) as exception:
            raise WikiRetrievalError(
                WikiErrorCode.WIKI_HTTP_ERROR,
                "Terraria Wiki 请求失败",
            ) from exception

        if "error" in data:
            raise WikiRetrievalError(
                WikiErrorCode.WIKI_HTTP_ERROR,
                f"Terraria Wiki API error: {data['error'].get('code', 'unknown')}",
            )
        return data

    @staticmethod
    def _page_url(title: str, lang: WikiLanguage) -> str:
        prefix = "/zh/wiki/" if lang == "zh" else "/wiki/"
        return f"https://terraria.wiki.gg{prefix}{quote(title.replace(' ', '_'))}"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
