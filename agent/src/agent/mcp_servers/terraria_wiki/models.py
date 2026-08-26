from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


WikiLanguage = Literal["zh", "en"]
WikiIntent = Literal[
    "general",
    "obtaining",
    "usage",
    "crafting",
    "summoning",
    "location",
    "drops",
    "mechanics",
]

VALID_INTENTS = frozenset(
    {
        "general",
        "obtaining",
        "usage",
        "crafting",
        "summoning",
        "location",
        "drops",
        "mechanics",
    }
)

PARSED_PAGE_SCHEMA_VERSION = 2


class ResolvedWikiPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    page_id: int
    lang: WikiLanguage
    source_url: str
    redirect_info: dict[str, str] | None = None


class SearchCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    page_id: int


class RawWikiPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    lang: WikiLanguage
    html: str
    source_url: str
    revision_id: int | None


class WikiSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str
    paragraphs: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_content(cls, value: object) -> object:
        if not isinstance(value, dict) or "paragraphs" in value:
            return value
        passages = value.get("passages")
        if not passages:
            content = value.get("content") or ""
            passages = [line.strip() for line in content.splitlines() if line.strip()]
        return {"heading": value.get("heading", ""), "paragraphs": passages}


class WikiTable(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


class ParsedWikiPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = PARSED_PAGE_SCHEMA_VERSION
    title: str
    lang: WikiLanguage
    summary: str
    sections: tuple[WikiSection, ...]
    tables: tuple[WikiTable, ...] = ()
    source_url: str
    revision_id: int | None


class WikiEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["paragraph", "table_row"]
    section: str
    content: str


class TerrariaKnowledgeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity: str
    title: str
    intent: WikiIntent
    lang: WikiLanguage
    resolved_lang: WikiLanguage
    evidence: tuple[WikiEvidence, ...]
    source_url: str
    revision_id: int | None
