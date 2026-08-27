from graphiti_core import Graphiti
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

from agent.llm.config import AgentLLMSettings
from agent.memory.graphiti.config import GraphitiSettings


def create_graphiti(
    settings: GraphitiSettings | None = None,
    *,
    agent_settings: AgentLLMSettings | None = None,
) -> Graphiti:
    """使用项目的 DeepSeek 兼容模型和 Gemini 构建 Graphiti"""

    graphiti_settings = settings or GraphitiSettings.from_environment()
    llm_settings = agent_settings or AgentLLMSettings.from_environment()

    llm_client = OpenAIGenericClient(
        config=LLMConfig(
            api_key=llm_settings.provider.api_key,
            base_url=llm_settings.provider.base_url,
            model=llm_settings.reasoning.model_name,
            small_model=llm_settings.reasoning.model_name,
        ),
        structured_output_mode="json_object",
    )
    embedder = GeminiEmbedder(
        config=GeminiEmbedderConfig(
            api_key=graphiti_settings.gemini_api_key,
            embedding_model=graphiti_settings.embedding_model,
            embedding_dim=graphiti_settings.embedding_dimension,
        )
    )
    reranker = GeminiRerankerClient(
        config=LLMConfig(api_key=graphiti_settings.gemini_api_key)
    )
    driver = FalkorDriver(
        host=graphiti_settings.falkordb_host,
        port=graphiti_settings.falkordb_port,
        database=graphiti_settings.falkordb_database,
    )
    return Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=reranker,
        max_coroutines=graphiti_settings.max_coroutines,
    )
