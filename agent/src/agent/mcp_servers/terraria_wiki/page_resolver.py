import re
import unicodedata

from agent.mcp_servers.terraria_wiki.cache import WikiCache
from agent.mcp_servers.terraria_wiki.errors import WikiErrorCode, WikiRetrievalError
from agent.mcp_servers.terraria_wiki.models import (
    ResolvedWikiPage,
    SearchCandidate,
    WikiLanguage,
)
from agent.mcp_servers.terraria_wiki.wiki_client import WikiClient


class PageResolver:
    def __init__(self, client: WikiClient, cache: WikiCache) -> None:
        self._client = client
        self._cache = cache

    async def resolve(
        self,
        entity: str,
        lang: WikiLanguage,
    ) -> tuple[ResolvedWikiPage, bool, bool]:
        cached = await self._cache.get_resolve(lang, entity)
        if cached is not None:
            return ResolvedWikiPage.model_validate(cached), True, False

        page = await self._client.lookup_exact(entity, lang)
        fallback_used = False
        if page is None:
            fallback_used = True
            candidates = await self._client.search(entity, lang)
            candidate = self._select_reliable_candidate(entity, candidates)
            if candidate is None:
                code = (
                    WikiErrorCode.PAGE_NOT_FOUND
                    if not candidates
                    else WikiErrorCode.PAGE_UNRESOLVED
                )
                raise WikiRetrievalError(code, f"无法可靠定位 Wiki 页面: {entity}")
            page = await self._client.resolve_search_candidate(candidate, lang)
            if page is None:
                raise WikiRetrievalError(
                    WikiErrorCode.PAGE_UNRESOLVED,
                    f"搜索结果无法解析为 Wiki 页面: {candidate.title}",
                )

        await self._cache.set_resolve(lang, entity, page.model_dump(mode="json"))
        return page, False, fallback_used

    @classmethod
    def _select_reliable_candidate(
        cls,
        entity: str,
        candidates: tuple[SearchCandidate, ...],
    ) -> SearchCandidate | None:
        entity_key = cls._normalize_title(entity)
        for candidate in candidates:
            if cls._normalize_title(candidate.title) == entity_key:
                return candidate

        if not candidates:
            return None
        top = candidates[0]
        title_key = cls._normalize_title(top.title)
        if entity_key in title_key or title_key in entity_key:
            shorter = min(len(entity_key), len(title_key))
            longer = max(len(entity_key), len(title_key))
            if longer and shorter / longer >= 0.6:
                return top
        return None

    @staticmethod
    def _normalize_title(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"[\s_\-:：()（）]", "", normalized)
