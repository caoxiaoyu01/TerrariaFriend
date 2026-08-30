import os
from dataclasses import dataclass, field

from agent.llm.config import AgentLLMSettings


@dataclass(frozen=True, slots=True)
class GraphitiSettings:
    """从环境变量读取长期记忆服务配置"""

    gemini_api_key: str = field(repr=False)
    reranker_api_key: str = field(repr=False)
    reranker_base_url: str
    falkordb_host: str = "127.0.0.1"
    falkordb_port: int = 6380
    falkordb_database: str = "terrariafriend_memory"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimension: int = 1024
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    max_coroutines: int = 1

    @classmethod
    def from_environment(cls) -> "GraphitiSettings":
        # 统一沿用模型配置读取环境文件的方式
        agent_settings = AgentLLMSettings.from_environment()
        provider = agent_settings.provider
        return cls(
            gemini_api_key=os.environ["GEMINI_API_KEY"],
            reranker_api_key=os.getenv(
                "GRAPHITI_RERANKER_API_KEY",
                provider.api_key,
            ),
            reranker_base_url=os.getenv(
                "GRAPHITI_RERANKER_BASE_URL",
                provider.base_url,
            ),
            falkordb_host=os.getenv("FALKORDB_HOST", "127.0.0.1"),
            falkordb_port=int(os.getenv("FALKORDB_PORT", "6380")),
            falkordb_database=os.getenv(
                "FALKORDB_DATABASE",
                "terrariafriend_memory",
            ),
            embedding_model=os.getenv(
                "GRAPHITI_EMBEDDING_MODEL",
                "gemini-embedding-001",
            ),
            reranker_model=os.getenv(
                "GRAPHITI_RERANKER_MODEL",
                "BAAI/bge-reranker-v2-m3",
            ),
            embedding_dimension=int(
                os.getenv("GRAPHITI_EMBEDDING_DIMENSION", "1024")
            ),
            max_coroutines=int(os.getenv("GRAPHITI_MAX_COROUTINES", "1")),
        )
