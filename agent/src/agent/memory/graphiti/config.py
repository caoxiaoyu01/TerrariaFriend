import os
from dataclasses import dataclass, field

from agent.llm.config import AgentLLMSettings


@dataclass(frozen=True, slots=True)
class GraphitiSettings:
    """不使用硬编码密钥加载 Graphiti 专用基础设施设置"""

    gemini_api_key: str = field(repr=False)
    falkordb_host: str = "127.0.0.1"
    falkordb_port: int = 6380
    falkordb_database: str = "terrariafriend_memory"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimension: int = 1024
    max_coroutines: int = 1

    @classmethod
    def from_environment(cls) -> "GraphitiSettings":
        # 智能体模型设置负责项目环境文件的加载约定
        AgentLLMSettings.from_environment()
        return cls(
            gemini_api_key=os.environ["GEMINI_API_KEY"],
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
            embedding_dimension=int(
                os.getenv("GRAPHITI_EMBEDDING_DIMENSION", "1024")
            ),
            max_coroutines=int(os.getenv("GRAPHITI_MAX_COROUTINES", "1")),
        )
