import logging
import time
from typing import cast

from agent.mcp_servers.terraria_wiki.cache import WikiCache
from agent.mcp_servers.terraria_wiki.content_parser import ContentParser
from agent.mcp_servers.terraria_wiki.content_selector import RelevantContentSelector
from agent.mcp_servers.terraria_wiki.errors import WikiErrorCode, WikiRetrievalError
from agent.mcp_servers.terraria_wiki.models import (
    PARSED_PAGE_SCHEMA_VERSION,
    ParsedWikiPage,
    TerrariaKnowledgeResult,
    VALID_INTENTS,
    WikiIntent,
    WikiLanguage,
)
from agent.mcp_servers.terraria_wiki.page_resolver import PageResolver
from agent.mcp_servers.terraria_wiki.wiki_client import WikiClient


logger = logging.getLogger(__name__)


class WikiRetrievalService:
    def __init__(
        self,
        *,
        client: WikiClient | None = None,
        cache: WikiCache | None = None,
        parser: ContentParser | None = None,
        selector: RelevantContentSelector | None = None,
        resolver: PageResolver | None = None,
    ) -> None:
        self._client = client or WikiClient()
        self._cache = cache or WikiCache()
        self._parser = parser or ContentParser()
        self._selector = selector or RelevantContentSelector()
        self._resolver = resolver or PageResolver(self._client, self._cache)

    async def lookup(
        self,
        entity: str,
        intent: str = "general",
        lang: str = "zh",
    ) -> TerrariaKnowledgeResult:
        normalized_entity = entity.strip()
        if not normalized_entity or len(normalized_entity) > 120:
            raise WikiRetrievalError(
                WikiErrorCode.INVALID_ENTITY,
                "entity 必须是非空且明确的 Terraria 实体或主题",
            )
        if intent not in VALID_INTENTS:
            raise WikiRetrievalError(
                WikiErrorCode.INVALID_INTENT,
                f"不支持的 intent: {intent}",
            )
        if lang not in {"zh", "en"}:
            raise WikiRetrievalError(
                WikiErrorCode.LANGUAGE_MAPPING_UNAVAILABLE,
                f"不支持的语言: {lang}",
            )

        requested_lang = lang
        resolved_lang = cast(WikiLanguage, lang)
        normalized_intent = cast(WikiIntent, intent)
        started_at = time.perf_counter()
        resolve_started_at = time.perf_counter()
        try:
            page, resolve_cache_hit, fallback_used = await self._resolver.resolve(
                normalized_entity,
                resolved_lang,
            )
        except WikiRetrievalError as exception:
            if requested_lang == "zh" and exception.code is WikiErrorCode.PAGE_NOT_FOUND:
                raise WikiRetrievalError(
                    WikiErrorCode.LANGUAGE_MAPPING_UNAVAILABLE,
                    "中文页面不存在，没有可靠的中英文实体映射，未猜测英文名称",
                ) from exception
            raise
        resolve_latency_ms = _elapsed_ms(resolve_started_at)

        page_cache_hit = False
        wiki_latency_ms = 0.0
        parse_latency_ms = 0.0
        cached_page = await self._cache.get_page(page.lang, page.title)
        if (
            cached_page is not None
            and cached_page.get("schema_version") == PARSED_PAGE_SCHEMA_VERSION
        ):
            parsed_page = ParsedWikiPage.model_validate(cached_page)
            page_cache_hit = True
        else:
            wiki_started_at = time.perf_counter()
            raw_page = await self._client.fetch_page(page)
            wiki_latency_ms = _elapsed_ms(wiki_started_at)

            parse_started_at = time.perf_counter()
            parsed_page = self._parser.parse(raw_page)
            parse_latency_ms = _elapsed_ms(parse_started_at)
            await self._cache.set_page(
                page.lang,
                page.title,
                parsed_page.model_dump(mode="json"),
            )

        evidence = self._selector.select(parsed_page, normalized_intent)
        result = TerrariaKnowledgeResult(
            entity=normalized_entity,
            title=parsed_page.title,
            intent=normalized_intent,
            lang=requested_lang,
            resolved_lang=parsed_page.lang,
            evidence=evidence,
            source_url=parsed_page.source_url,
            revision_id=parsed_page.revision_id,
        )
        logger.info(
            "[TerraWiki] entity=%s intent=%s requested_lang=%s resolved_lang=%s "
            "resolve_cache=%s page_cache=%s resolve_latency_ms=%.1f "
            "wiki_latency_ms=%.1f parse_latency_ms=%.1f total_latency_ms=%.1f "
            "result_chars=%d fallback_used=%s",
            normalized_entity,
            intent,
            requested_lang,
            parsed_page.lang,
            "hit" if resolve_cache_hit else "miss",
            "hit" if page_cache_hit else "miss",
            resolve_latency_ms,
            wiki_latency_ms,
            parse_latency_ms,
            _elapsed_ms(started_at),
            sum(len(item.section) + len(item.content) for item in evidence),
            str(fallback_used).lower(),
        )
        return result

    async def aclose(self) -> None:
        await self._client.aclose()
        await self._cache.aclose()


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000
