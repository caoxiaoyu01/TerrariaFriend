import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


_AGENT_ROOT = Path(__file__).resolve().parents[3]


def _read_bool(name: str) -> bool:
    return os.environ[name].lower() == "true"


def _shared_value(name: str, legacy_name: str) -> str:
    value = os.environ.get(name) or os.environ.get(legacy_name)
    if value is None:
        raise KeyError(name)
    return value


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    api_key: str = field(repr=False)
    base_url: str
    timeout_seconds: float = 60.0


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

    @classmethod
    def from_environment(cls) -> "AgentLLMSettings":
        # 真实凭证只从 agent/.env 或系统环境变量读取
        load_dotenv(_AGENT_ROOT / ".env", override=False)

        provider = ProviderConfig(
            api_key=_shared_value(
                "TERRARIAFRIEND_LLM_API_KEY",
                "TERRARIAFRIEND_DECISION_API_KEY",
            ),
            base_url=_shared_value(
                "TERRARIAFRIEND_LLM_BASE_URL",
                "TERRARIAFRIEND_DECISION_BASE_URL",
            ),
        )
        decision = ModelConfig(
            role="decision",
            model_name=os.environ["TERRARIAFRIEND_DECISION_MODEL"],
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
            model_name=os.environ["TERRARIAFRIEND_RESPONSE_MODEL"],
            temperature=float(os.environ["TERRARIAFRIEND_RESPONSE_TEMPERATURE"]),
            max_tokens=int(os.environ["TERRARIAFRIEND_RESPONSE_MAX_TOKENS"]),
            enable_thinking=_read_bool("TERRARIAFRIEND_RESPONSE_ENABLE_THINKING"),
        )
        reasoning = ModelConfig(
            role="reasoning",
            model_name=os.environ["TERRARIAFRIEND_REASONING_MODEL"],
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
        )
