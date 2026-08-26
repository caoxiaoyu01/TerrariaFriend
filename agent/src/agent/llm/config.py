import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv


_AGENT_ROOT = Path(__file__).resolve().parents[3]


class LLMProvider(str, Enum):
    SILICONFLOW = "siliconflow"
    DEEPSEEK = "deepseek"


def _read_bool(name: str) -> bool:
    return os.environ[name].lower() == "true"


def _provider_value(provider: LLMProvider, suffix: str) -> str:
    provider_name = provider.value.upper()
    candidates = [f"TERRARIAFRIEND_{provider_name}_{suffix}"]
    if provider is LLMProvider.DEEPSEEK:
        candidates.append(f"TERRARIAFRIEND_DECISION_{suffix}")
    candidates.append(f"TERRARIAFRIEND_LLM_{suffix}")
    if provider is LLMProvider.SILICONFLOW:
        candidates.append(f"TERRARIAFRIEND_DECISION_{suffix}")
    for name in candidates:
        value = os.environ.get(name)
        if value:
            return value
    raise KeyError(candidates[0])


def _model_value(provider: LLMProvider, role: str) -> str:
    return os.environ.get(
        f"TERRARIAFRIEND_{provider.value.upper()}_{role.upper()}_MODEL"
    ) or os.environ[f"TERRARIAFRIEND_{role.upper()}_MODEL"]


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    api_key: str = field(repr=False)
    base_url: str
    timeout_seconds: float = 60.0
    provider: LLMProvider = LLMProvider.SILICONFLOW


@dataclass(frozen=True, slots=True)
class ModelConfig:
    role: str
    model_name: str
    temperature: float
    max_tokens: int
    enable_thinking: bool
    reasoning_effort: str | None = None
    top_p: float | None = None
    top_k: int | None = None
    frequency_penalty: float | None = None


@dataclass(frozen=True, slots=True)
class AgentLLMSettings:
    provider: ProviderConfig
    decision: ModelConfig
    response: ModelConfig
    reasoning: ModelConfig
    wiki_mcp_enabled: bool = False

    @classmethod
    def from_environment(cls) -> "AgentLLMSettings":
        # 真实凭证只从 agent/.env 或系统环境变量读取
        load_dotenv(_AGENT_ROOT / ".env", override=False)

        provider_name = os.environ.get(
            "TERRARIAFRIEND_LLM_PROVIDER",
            LLMProvider.SILICONFLOW.value,
        ).lower()
        try:
            selected_provider = LLMProvider(provider_name)
        except ValueError as exception:
            allowed = ", ".join(provider.value for provider in LLMProvider)
            raise ValueError(
                f"不支持的 LLM provider: {provider_name}; 可选值: {allowed}"
            ) from exception
        provider = ProviderConfig(
            api_key=_provider_value(selected_provider, "API_KEY"),
            base_url=_provider_value(selected_provider, "BASE_URL"),
            provider=selected_provider,
        )
        decision = ModelConfig(
            role="decision",
            model_name=_model_value(selected_provider, "decision"),
            temperature=float(os.environ["TERRARIAFRIEND_DECISION_TEMPERATURE"]),
            max_tokens=int(os.environ["TERRARIAFRIEND_DECISION_MAX_TOKENS"]),
            enable_thinking=_read_bool("TERRARIAFRIEND_DECISION_ENABLE_THINKING"),
            top_p=float(os.environ["TERRARIAFRIEND_DECISION_TOP_P"]),
            top_k=int(os.environ["TERRARIAFRIEND_DECISION_TOP_K"]),
            frequency_penalty=float(
                os.environ["TERRARIAFRIEND_DECISION_FREQUENCY_PENALTY"]
            ),
        )
        response = ModelConfig(
            role="response",
            model_name=_model_value(selected_provider, "response"),
            temperature=float(os.environ["TERRARIAFRIEND_RESPONSE_TEMPERATURE"]),
            max_tokens=int(os.environ["TERRARIAFRIEND_RESPONSE_MAX_TOKENS"]),
            enable_thinking=_read_bool("TERRARIAFRIEND_RESPONSE_ENABLE_THINKING"),
        )
        reasoning = ModelConfig(
            role="reasoning",
            model_name=_model_value(selected_provider, "reasoning"),
            temperature=float(os.environ["TERRARIAFRIEND_REASONING_TEMPERATURE"]),
            max_tokens=int(os.environ["TERRARIAFRIEND_REASONING_MAX_TOKENS"]),
            enable_thinking=_read_bool("TERRARIAFRIEND_REASONING_ENABLE_THINKING"),
            reasoning_effort=os.environ["TERRARIAFRIEND_REASONING_EFFORT"],
        )
        return cls(
            provider=provider,
            decision=decision,
            response=response,
            reasoning=reasoning,
            wiki_mcp_enabled=(
                os.environ.get("WIKI_MCP_ENABLED", "false").lower() == "true"
            ),
        )
