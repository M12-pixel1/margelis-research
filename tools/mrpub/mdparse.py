"""Markdown parsing shared by the PDF renderer, the site renderer and the checks.

A note file has two parts separated by the first top-level thematic break (---):
the title block (series, title, subtitle, author, affiliation, label) and the body.
Renderers build their own title block from note.yaml; `check` verifies that the
Markdown title block says the same thing.
"""
from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .common import PipelineError, strip_number


def parser() -> MarkdownIt:
    # html=False: raw HTML in a note is escaped, never passed through.
    return MarkdownIt("commonmark", {"html": False, "typographer": False}).enable("table")


def parse(text: str) -> list[Token]:
    return parser().parse(text)


def split_title_block(tokens: list[Token]) -> tuple[list[Token], list[Token]]:
    for i, tok in enumerate(tokens):
        if tok.type == "hr" and tok.level == 0:
            return tokens[:i], tokens[i + 1:]
    raise PipelineError("title block separator '---' not found")


def inline_text(tok: Token) -> str:
    parts = []
    for child in tok.children or []:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type == "softbreak":
            parts.append(" ")
        elif child.type == "hardbreak":
            parts.append("\n")
    return "".join(parts)


def plain_text(tokens: list[Token]) -> str:
    lines = []
    for tok in tokens:
        if tok.type == "inline":
            lines.append(inline_text(tok))
        elif tok.type in ("fence", "code_block"):
            lines.append(tok.content)
    return "\n".join(lines)


def headings(tokens: list[Token], level: int = 2) -> list[str]:
    out = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.tag == f"h{level}":
            out.append(inline_text(tokens[i + 1]))
    return out


def sections(tokens: list[Token]) -> dict[str, str]:
    """Map level-2 heading (without number prefix) -> plain text of that section."""
    result: dict[str, list[Token]] = {}
    current = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open" and tok.tag == "h2":
            current = strip_number(inline_text(tokens[i + 1]))
            result[current] = []
            i += 3
            continue
        if current is not None:
            result[current].append(tok)
        i += 1
    return {k: plain_text(v) for k, v in result.items()}


def links(tokens: list[Token]) -> list[str]:
    out = []
    for tok in tokens:
        for child in tok.children or []:
            if child.type == "link_open":
                out.append(child.attrs.get("href", ""))
    return out


def unsupported_tokens(tokens: list[Token]) -> list[str]:
    """Token types the renderers do not handle (raw HTML, images, ...)."""
    allowed_block = {
        "heading_open", "heading_close", "paragraph_open", "paragraph_close", "inline",
        "bullet_list_open", "bullet_list_close", "ordered_list_open", "ordered_list_close",
        "list_item_open", "list_item_close", "fence", "code_block", "hr",
        "table_open", "table_close", "thead_open", "thead_close", "tbody_open", "tbody_close",
        "tr_open", "tr_close", "th_open", "th_close", "td_open", "td_close",
    }
    allowed_inline = {
        "text", "softbreak", "hardbreak", "strong_open", "strong_close", "em_open", "em_close",
        "code_inline", "link_open", "link_close",
    }
    bad = []
    for tok in tokens:
        if tok.type not in allowed_block:
            bad.append(tok.type)
        for child in tok.children or []:
            if child.type not in allowed_inline:
                bad.append(child.type)
    return sorted(set(bad))
