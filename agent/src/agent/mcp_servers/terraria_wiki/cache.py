import json
import logging
import re
import unicodedata
from typing import Any

import redis.asyncio as redis
from redis.backoff import NoBackoff
from redis.retry import Retry


logger = logging.getLogger(__name__)

REDIS_URL = "redis://localhost:6379"
RESOLVE_CACHE_TTL_SECONDS = 1800
PAGE_CACHE_TTL_SECONDS = 43200


def normalize_cache_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", "_", normalized)


class WikiCache:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client or redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
            retry=Retry(NoBackoff(), 0),
        )
        self._available = True

    @staticmethod
    def resolve_key(lang: str, entity: str) -> str:
        return f"terraria_wiki:resolve:{lang}:{normalize_cache_component(entity)}"

    @staticmethod
    def page_key(lang: str, title: str) -> str:
        return f"terraria_wiki:page:{lang}:{normalize_cache_component(title)}"

    async def get_resolve(self, lang: str, entity: str) -> dict[str, Any] | None:
        return await self._get_json(self.resolve_key(lang, entity))

    async def set_resolve(
        self,
        lang: str,
        entity: str,
        value: dict[str, Any],
    ) -> None:
        await self._set_json(
            self.resolve_key(lang, entity),
            value,
            RESOLVE_CACHE_TTL_SECONDS,
        )

    async def get_page(self, lang: str, title: str) -> dict[str, Any] | None:
        return await self._get_json(self.page_key(lang, title))

    async def set_page(
        self,
        lang: str,
        title: str,
        value: dict[str, Any],
    ) -> None:
        await self._set_json(
            self.page_key(lang, title),
            value,
            PAGE_CACHE_TTL_SECONDS,
        )

    async def _get_json(self, key: str) -> dict[str, Any] | None:
        if not self._available:
            return None
        try:
            value = await self._client.get(key)
        except Exception as exception:
            self._available = False
            self._log_unavailable(exception)
            return None
        if value is None:
            return None
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            logger.warning("[TerrariaWiki] invalid cached JSON key=%s", key)
            return None
        return parsed if isinstance(parsed, dict) else None

    async def _set_json(self, key: str, value: dict[str, Any], ttl: int) -> None:
        if not self._available:
            return
        try:
            await self._client.set(
                key,
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                ex=ttl,
            )
        except Exception as exception:
            self._available = False
            self._log_unavailable(exception)

    @staticmethod
    def _log_unavailable(exception: Exception) -> None:
        logger.warning(
            "[TerrariaWiki] code=REDIS_UNAVAILABLE error=%s",
            exception,
        )

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()
