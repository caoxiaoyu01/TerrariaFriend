import re

from agent.mcp_servers.terraria_wiki.models import (
    ParsedWikiPage,
    WikiIntent,
    WikiLanguage,
    WikiEvidence,
    WikiTable,
)


MAX_EVIDENCE_CHARS = 1500
MAX_SELECTED_EVIDENCE = 5
MIN_TARGET_EVIDENCE = 3

_LOW_VALUE_HEADINGS: dict[WikiLanguage, tuple[str, ...]] = {
    "zh": ("备注", "花絮", "历史", "版本历史", "更新历史"),
    "en": ("notes", "trivia", "history", "version history"),
}
_HISTORY_HEADINGS: dict[WikiLanguage, tuple[str, ...]] = {
    "zh": ("历史", "版本历史", "更新历史"),
    "en": ("history", "version history"),
}
_VARIANT_HEADINGS: dict[WikiLanguage, tuple[str, ...]] = {
    "zh": ("变体", "其他实体", "其他版本"),
    "en": ("variants", "other entities", "other versions"),
}

INTENT_KEYWORDS: dict[WikiLanguage, dict[str, tuple[str, ...]]] = {
    "zh": {
        "obtaining": (
            "获得",
            "获取",
            "来源",
            "找到",
            "宝箱",
            "掉落",
            "购买",
            "钓鱼",
            "几率",
            "概率",
            "生成",
            "制作",
            "合成",
        ),
        "usage": ("用于", "用途", "使用", "装备", "效果", "作用"),
        "crafting": ("制作", "合成", "配方", "材料", "制作站"),
        "summoning": ("召唤", "触发", "生成", "出现", "条件"),
        "location": ("位置", "位于", "找到", "生成于", "生物群系", "地层", "地下", "地表"),
        "drops": ("掉落", "掉率", "战利品", "概率"),
        "mechanics": ("机制", "行为", "条件", "规则", "效果", "阶段"),
    },
    "en": {
        "obtaining": (
            "obtain",
            "source",
            "found",
            "chest",
            "drop",
            "purchase",
            "fishing",
            "chance",
            "spawn",
            "craft",
        ),
        "usage": ("used in", "uses", "usage", "equip", "effect", "function"),
        "crafting": ("crafting", "recipe", "ingredient", "crafting station", "material"),
        "summoning": ("summon", "trigger", "spawn", "appear", "condition"),
        "location": ("location", "located", "found", "spawns in", "biome", "layer", "underground", "surface"),
        "drops": ("drops", "drop rate", "loot", "chance"),
        "mechanics": ("mechanics", "behavior", "condition", "rule", "effect", "phase"),
    },
}

TABLE_INTENT_KEYWORDS: dict[WikiLanguage, dict[str, tuple[str, ...]]] = {
    "zh": {
        "obtaining": ("获得", "来源", "宝箱", "掉落", "购买", "钓鱼", "几率", "概率"),
        "usage": ("用于", "用途", "效果"),
        "crafting": ("制作", "合成", "配方", "产物", "材料", "制作站"),
        "summoning": ("召唤", "触发", "条件", "召唤物"),
        "location": ("位置", "生成", "生物群系", "地层"),
        "drops": ("掉落", "掉落物", "战利品", "物品", "数量", "几率", "概率"),
        "mechanics": ("机制", "行为", "阶段", "条件"),
    },
    "en": {
        "obtaining": ("obtain", "source", "chest", "drop", "purchase", "fishing", "chance"),
        "usage": ("used in", "usage", "effect"),
        "crafting": ("crafting", "recipe", "result", "ingredient", "crafting station"),
        "summoning": ("summon", "trigger", "condition", "summoning item"),
        "location": ("location", "spawn", "biome", "layer"),
        "drops": ("drop", "loot", "item", "quantity", "rate", "chance"),
        "mechanics": ("mechanics", "behavior", "phase", "condition"),
    },
}


class RelevantContentSelector:
    def select(
        self,
        page: ParsedWikiPage,
        intent: WikiIntent,
    ) -> tuple[WikiEvidence, ...]:
        if intent == "general":
            candidates = self._general_evidence(page)
        else:
            candidates = self._intent_evidence(page, intent)
        return _limit_evidence(candidates)

    @staticmethod
    def _general_evidence(page: ParsedWikiPage) -> list[WikiEvidence]:
        evidence = (
            [
                WikiEvidence(
                    type="paragraph",
                    section="概述" if page.lang == "zh" else "Summary",
                    content=page.summary,
                )
            ]
            if page.summary
            else []
        )
        normal_sections = [
            section
            for section in page.sections
            if not _is_low_value_heading(section.heading, page.lang)
        ]
        candidates = normal_sections or list(page.sections)
        for section in candidates:
            for paragraph in section.paragraphs:
                evidence.append(
                    WikiEvidence(
                        type="paragraph",
                        section=section.heading,
                        content=paragraph,
                    )
                )
                if len(evidence) >= MIN_TARGET_EVIDENCE:
                    return evidence
        return evidence

    def _intent_evidence(
        self,
        page: ParsedWikiPage,
        intent: WikiIntent,
    ) -> list[WikiEvidence]:
        keywords = INTENT_KEYWORDS[page.lang][intent]
        scored = self._paragraph_evidence(page, intent, keywords)
        scored.extend(self._table_evidence(page, intent, keywords))
        scored.sort(key=lambda item: (-item[0], item[1]))

        selected: list[WikiEvidence] = []
        seen: set[tuple[str, str, str]] = set()
        for score, _, candidate in scored:
            identity = (candidate.type, candidate.section, candidate.content)
            if score <= 0 or identity in seen:
                continue
            selected.append(candidate)
            seen.add(identity)
            if len(selected) >= MAX_SELECTED_EVIDENCE:
                return selected

        if len(selected) < MIN_TARGET_EVIDENCE and page.summary:
            summary = WikiEvidence(
                type="paragraph",
                section="概述" if page.lang == "zh" else "Summary",
                content=page.summary,
            )
            identity = (summary.type, summary.section, summary.content)
            if identity not in seen:
                selected.append(summary)
                seen.add(identity)

        if len(selected) < MIN_TARGET_EVIDENCE:
            for section in page.sections:
                if _is_low_value_heading(section.heading, page.lang):
                    continue
                for paragraph in section.paragraphs:
                    candidate = WikiEvidence(
                        type="paragraph",
                        section=section.heading,
                        content=paragraph,
                    )
                    identity = (candidate.type, candidate.section, candidate.content)
                    if identity in seen:
                        continue
                    selected.append(candidate)
                    seen.add(identity)
                    if len(selected) >= MIN_TARGET_EVIDENCE:
                        return selected
        return selected

    def _paragraph_evidence(
        self,
        page: ParsedWikiPage,
        intent: WikiIntent,
        keywords: tuple[str, ...],
    ) -> list[tuple[int, int, WikiEvidence]]:
        evidence: list[tuple[int, int, WikiEvidence]] = []
        order = 0
        for section in page.sections:
            if _is_history_heading(section.heading, page.lang):
                continue
            heading_bonus = self._heading_score(section.heading, keywords)
            penalty = _heading_penalty(section.heading, page.lang)
            for paragraph in section.paragraphs:
                body_score = self._text_score(paragraph, keywords)
                if body_score == 0:
                    order += 1
                    continue
                contextual_penalty = penalty + _paragraph_penalty(
                    paragraph,
                    intent,
                    page.lang,
                )
                score = body_score * 4 + heading_bonus - contextual_penalty
                evidence.append(
                    (
                        score,
                        order,
                        WikiEvidence(
                            type="paragraph",
                            section=section.heading,
                            content=paragraph,
                        ),
                    )
                )
                order += 1
        return evidence

    def _table_evidence(
        self,
        page: ParsedWikiPage,
        intent: WikiIntent,
        keywords: tuple[str, ...],
    ) -> list[tuple[int, int, WikiEvidence]]:
        evidence: list[tuple[int, int, WikiEvidence]] = []
        order = len(page.sections) * 1000
        table_keywords = TABLE_INTENT_KEYWORDS[page.lang][intent]
        for table in page.tables:
            table_score = self._table_type_score(table, table_keywords)
            if table_score == 0 or _is_history_heading(table.heading, page.lang):
                continue
            penalty = _heading_penalty(table.heading, page.lang)
            for row in table.rows:
                row_text = " | ".join(row)
                body_score = self._text_score(row_text, keywords)
                score = table_score + body_score * 4 - penalty
                evidence.append(
                    (
                        score,
                        order,
                        WikiEvidence(
                            type="table_row",
                            section=table.heading or "表格",
                            content=_format_table_row(table, row),
                        ),
                    )
                )
                order += 1
        return evidence

    @staticmethod
    def _table_type_score(
        table: WikiTable,
        keywords: tuple[str, ...],
    ) -> int:
        context = f"{table.heading} {' '.join(table.headers)}".casefold()
        return sum(10 for keyword in keywords if keyword.casefold() in context)

    @staticmethod
    def _heading_score(heading: str, keywords: tuple[str, ...]) -> int:
        lowered = heading.casefold()
        return sum(4 for keyword in keywords if keyword.casefold() in lowered)

    @staticmethod
    def _text_score(text: str, keywords: tuple[str, ...]) -> int:
        lowered = text.casefold()
        return sum(min(lowered.count(keyword.casefold()), 3) for keyword in keywords)


def _truncate_compact(text: str, max_chars: int) -> str:
    compact = re.sub(r"[ \t]+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    candidate = compact[:max_chars]
    boundaries = [candidate.rfind(mark) for mark in ("。", "！", "？", ".", "!", "?", "\n")]
    boundary = max(boundaries)
    if boundary >= int(max_chars * 0.6):
        return candidate[: boundary + 1].rstrip()
    return candidate.rstrip()


def _limit_evidence(candidates: list[WikiEvidence]) -> tuple[WikiEvidence, ...]:
    selected: list[WikiEvidence] = []
    used_chars = 0
    for candidate in candidates[:MAX_SELECTED_EVIDENCE]:
        remaining = MAX_EVIDENCE_CHARS - used_chars - len(candidate.section)
        if remaining <= 0:
            break
        content = _truncate_compact(candidate.content, remaining)
        if not content:
            continue
        selected.append(candidate.model_copy(update={"content": content}))
        used_chars += len(candidate.section) + len(content)
    return tuple(selected)


def _is_low_value_heading(heading: str, lang: WikiLanguage) -> bool:
    lowered = heading.casefold()
    return any(value.casefold() in lowered for value in _LOW_VALUE_HEADINGS[lang])


def _is_history_heading(heading: str, lang: WikiLanguage) -> bool:
    lowered = heading.casefold()
    return any(value.casefold() in lowered for value in _HISTORY_HEADINGS[lang])


def _heading_penalty(heading: str, lang: WikiLanguage) -> int:
    penalty = 6 if _is_low_value_heading(heading, lang) else 0
    lowered = heading.casefold()
    if any(value.casefold() in lowered for value in _VARIANT_HEADINGS[lang]):
        penalty += 6
    return penalty


def _paragraph_penalty(
    paragraph: str,
    intent: WikiIntent,
    lang: WikiLanguage,
) -> int:
    lowered = paragraph.casefold()
    rare_terms = ("罕见", "极少数") if lang == "zh" else ("rarely", "rare")
    other_entity_terms = ("另见", "参见", "变体") if lang == "zh" else ("see also", "variant")
    penalty = 4 if intent == "location" and any(term in lowered for term in rare_terms) else 0
    if any(term in lowered for term in other_entity_terms):
        penalty += 5
    return penalty


def _format_table_row(table: WikiTable, row: tuple[str, ...]) -> str:
    if table.headers:
        pairs = [
            f"{header}: {value}"
            for header, value in zip(table.headers, row, strict=False)
        ]
        if len(row) > len(table.headers):
            pairs.extend(row[len(table.headers) :])
        return "；".join(pairs)
    return " | ".join(row)
