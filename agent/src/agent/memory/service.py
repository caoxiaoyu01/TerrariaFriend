from typing import Any

from agent.memory.ports import MemoryBackend, MemoryEpisode


class MemoryService:
    """围绕可替换记忆后端的小型应用边界

    运行时摄取 写入门控 轨迹分段和检索工具不属于当前初始框架
    """

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
