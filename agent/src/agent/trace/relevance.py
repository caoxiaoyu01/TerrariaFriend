from collections.abc import Awaitable, Callable

from pydantic import Field, field_validator, model_validator

from agent.llm.client import RoleLLMClient, parse_json_object
from agent.models.trigger_base import CamelModel
from agent.trace.boundary import CloseContext
from agent.trace.relation import ResolvedReference


CLOSE_CONTEXT_RELEVANCE_PROMPT = """
You classify whether a Terraria player query clearly continues the immediately
preceding close context. Return only the requested JSON structure.

RELATED only when the query refers to that just-ended entity, event, location,
outcome, drops, or an obvious pronoun such as "刚才/刚刚/那个" grounded by the
provided close context. A question about another boss, event, or location is
UNRELATED. When RELATED, list only ambiguous mentions in the original query
that the close context resolves to a concrete entity. Use the exact mention and
the entity name from the close context. Return an empty list when there is no
such mention or the resolution is uncertain. Do not rewrite or answer the query,
and do not infer causality or long-term memory. Always include a non-empty
"reason" explaining the classification briefly.
""".strip()


class TraceContinuationResult(CamelModel):
    related: bool
    resolved_references: list[ResolvedReference] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=200)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason 不能为空")
        return normalized

    @model_validator(mode="after")
    def discard_unrelated_references(self) -> "TraceContinuationResult":
        if not self.related:
            self.resolved_references = []
        return self


RelatednessChecker = Callable[
    [CloseContext, str],
    Awaitable[TraceContinuationResult],
]


async def is_related_to_close_context(
    close_context: CloseContext,
    user_query: str,
    *,
    model_client: RoleLLMClient,
) -> TraceContinuationResult:
    """单独判断问题是否与刚结束的记忆有关"""

    completion = await model_client.generate_structured(
        system_prompt=CLOSE_CONTEXT_RELEVANCE_PROMPT,
        input_data={
            "close_context": close_context.model_dump(mode="json", by_alias=True),
            "user_query": user_query,
        },
        output_schema=TraceContinuationResult.model_json_schema(),
    )
    return TraceContinuationResult.model_validate(
        parse_json_object(completion.content)
    )
