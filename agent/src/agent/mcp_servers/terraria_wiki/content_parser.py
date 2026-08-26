import re
from collections import OrderedDict
from html.parser import HTMLParser

from agent.mcp_servers.terraria_wiki.errors import WikiErrorCode, WikiRetrievalError
from agent.mcp_servers.terraria_wiki.models import (
    ParsedWikiPage,
    RawWikiPage,
    WikiSection,
    WikiTable,
)


_SKIP_TAGS = {"script", "style", "nav", "footer", "noscript", "figure"}
_SKIP_CLASSES = {
    "mw-editsection",
    "navbox",
    "navigation-not-searchable",
    "toc",
    "catlinks",
    "printfooter",
}
_BLOCK_TAGS = {"p", "li"}
_HEADING_TAGS = {"h2", "h3", "h4"}


class _WikiHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.intro: list[str] = []
        self.sections: OrderedDict[str, list[str]] = OrderedDict()
        self.tables: list[WikiTable] = []
        self.current_heading: str | None = None
        self._heading_parts: list[str] | None = None
        self._block_parts: list[str] | None = None
        self._block_tag: str | None = None
        self._table_heading: str | None = None
        self._table_rows: list[tuple[tuple[str, bool], ...]] | None = None
        self._row_cells: list[tuple[str, bool]] | None = None
        self._cell_parts: list[str] | None = None
        self._cell_is_header = False
        self._skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        classes = set(dict(attrs).get("class", "").split())
        if self._skip_depth or tag in _SKIP_TAGS or classes & _SKIP_CLASSES:
            self._skip_depth += 1
            return
        if tag == "table" and self._table_rows is None:
            self._table_heading = self.current_heading
            self._table_rows = []
            return
        if self._table_rows is not None:
            if tag == "tr":
                self._row_cells = []
            elif tag in {"th", "td"} and self._row_cells is not None:
                self._cell_parts = []
                self._cell_is_header = tag == "th"
            elif tag == "br" and self._cell_parts is not None:
                self._cell_parts.append(" ")
            return
        if tag in _HEADING_TAGS:
            self._heading_parts = []
            return
        if tag in _BLOCK_TAGS and self._block_parts is None:
            self._block_tag = tag
            self._block_parts = []
            return
        if tag == "br" and self._block_parts is not None:
            self._block_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if self._table_rows is not None:
            if tag in {"th", "td"} and self._cell_parts is not None:
                text = _clean_text("".join(self._cell_parts))
                self._row_cells.append((text, self._cell_is_header))
                self._cell_parts = None
            elif tag == "tr" and self._row_cells is not None:
                cells = tuple(cell for cell in self._row_cells if cell[0])
                if cells:
                    self._table_rows.append(cells)
                self._row_cells = None
            elif tag == "table":
                self._finish_table()
            return
        if tag in _HEADING_TAGS and self._heading_parts is not None:
            heading = _clean_text("".join(self._heading_parts))
            self.current_heading = heading or None
            if self.current_heading is not None:
                self.sections.setdefault(self.current_heading, [])
            self._heading_parts = None
            return
        if tag == self._block_tag and self._block_parts is not None:
            text = _clean_text("".join(self._block_parts))
            if text:
                target = (
                    self.intro
                    if self.current_heading is None
                    else self.sections[self.current_heading]
                )
                if text not in target:
                    target.append(text)
            self._block_parts = None
            self._block_tag = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._cell_parts is not None:
            self._cell_parts.append(data)
            return
        if self._heading_parts is not None:
            self._heading_parts.append(data)
        if self._block_parts is not None:
            self._block_parts.append(data)

    def _finish_table(self) -> None:
        table_rows = self._table_rows or []
        header_index = next(
            (index for index, row in enumerate(table_rows) if any(cell[1] for cell in row)),
            None,
        )
        headers: tuple[str, ...] = ()
        rows: list[tuple[str, ...]] = []
        for index, row in enumerate(table_rows):
            values = tuple(cell[0] for cell in row)
            if index == header_index:
                headers = values
            elif not all(cell[1] for cell in row):
                rows.append(values)
        if rows:
            self.tables.append(
                WikiTable(
                    heading=self._table_heading or "",
                    headers=headers,
                    rows=tuple(rows),
                )
            )
        self._table_heading = None
        self._table_rows = None
        self._row_cells = None
        self._cell_parts = None


def _clean_text(value: str) -> str:
    text = re.sub(r"\[(?:\d+|编辑|edit)\]", "", value, flags=re.IGNORECASE)
    text = text.replace("\u200b", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip(" |\n\t")


class ContentParser:
    def parse(self, page: RawWikiPage) -> ParsedWikiPage:
        try:
            parser = _WikiHTMLParser()
            parser.feed(page.html)
            parser.close()
        except Exception as exception:
            raise WikiRetrievalError(
                WikiErrorCode.WIKI_PARSE_ERROR,
                f"无法解析 Wiki 页面: {page.title}",
            ) from exception

        summary = "\n".join(parser.intro)
        sections = tuple(
            WikiSection(
                heading=heading,
                paragraphs=tuple(blocks),
            )
            for heading, blocks in parser.sections.items()
            if blocks
        )
        if not summary and not sections and not parser.tables:
            raise WikiRetrievalError(
                WikiErrorCode.WIKI_PARSE_ERROR,
                f"Wiki 页面没有有效正文: {page.title}",
            )
        return ParsedWikiPage(
            title=page.title,
            lang=page.lang,
            summary=summary,
            sections=sections,
            tables=tuple(parser.tables),
            source_url=page.source_url,
            revision_id=page.revision_id,
        )
