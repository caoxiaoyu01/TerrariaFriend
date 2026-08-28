from typing import Any

from agent.memory.ports import MemoryBackend, MemoryEpisode


class MemoryService:
    """为不同长期记忆实现提供统一的读写入口"""

    def __init__(self, backend: MemoryBackend) -> None:
        self._backend = backend

    async def initialize(self) -> None:
        await self._backend.initialize()

    async def add_episode(self, episode: MemoryEpisode) -> Any:
        return await self._backend.add_episode(episode)

    async def search(
        self,
        query: str,
        *,
        group_ids: list[str],
        num_results: int = 10,
    ) -> list[Any]:
        return await self._backend.search(
            query,
            group_ids=group_ids,
            num_results=num_results,
        )

    async def close(self) -> None:
        await self._backend.close()
