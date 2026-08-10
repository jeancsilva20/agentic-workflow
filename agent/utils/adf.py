"""Markdown -> Atlassian Document Format (ADF) conversion for Jira comments.

Covers the pragmatic subset the agent actually emits (tasks.md §2.4):
headings, paragraphs, bullet/ordered lists, fenced code blocks, links, and
inline code/bold/italic. Anything unrecognised falls through as a plain
paragraph rather than raising — this is not a full CommonMark implementation.
"""

from __future__ import annotations

import re
from typing import Any

# --- Character normalization -------------------------------------------
#
# Ported from the Sensedia AI Gateway project's `_pre_validate_add_comment` /
# `_normalize_text` (src/ai_gateway/services/agent_service.py). LLM-generated
# Portuguese text reliably contains these typographic characters, and Jira's
# comment endpoint rejects them with `INVALID_INPUT` / HTTP 400 if left as-is
# — confirmed against the real API by the connectivity spike (task 0.7,
# `scripts/spike_jira.py`).

_CHAR_MAP = {
    "“": '"',  # left curly double quote
    "”": '"',  # right curly double quote
    "‘": "'",  # left curly single quote
    "’": "'",  # right curly single quote
    "—": "-",  # em dash
    "–": "-",  # en dash
    " ": " ",  # non-breaking space
}


def normalize_text(text: str) -> str:
    """Replace typographic characters Jira's comment endpoint rejects."""
    for char, replacement in _CHAR_MAP.items():
        text = text.replace(char, replacement)
    return text


# --- Truncation ----------------------------------------------------------
#
# Jira Cloud does not publish an exact comment-body character limit; this is
# a conservative practical ceiling with headroom, not a documented constant.

_MAX_COMMENT_CHARS = 32_000


def _truncate(text: str, pointer: str | None) -> str:
    if len(text) <= _MAX_COMMENT_CHARS:
        return text
    suffix = f"\n\n... (truncated; see {pointer})" if pointer else "\n\n... (truncated)"
    return text[: _MAX_COMMENT_CHARS - len(suffix)] + suffix


# --- Markdown -> ADF -------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^```(\w*)\s*$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\d+\.\s+(.*)$")

_INLINE_PATTERN = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\*\*(?P<bold>[^*]+)\*\*"
    r"|\[(?P<link_text>[^\]]+)\]\((?P<link_href>[^)]+)\)"
    r"|(?<!\*)\*(?P<italic>[^*]+)\*(?!\*)"
    r"|_(?P<italic2>[^_]+)_"
)


def _inline_nodes(text: str) -> list[dict[str, Any]]:
    """Tokenize one line/paragraph of inline Markdown into ADF text nodes."""
    tokens: list[dict[str, Any]] = []
    pos = 0
    for m in _INLINE_PATTERN.finditer(text):
        if m.start() > pos:
            plain = text[pos : m.start()]
            if plain:
                tokens.append({"type": "text", "text": plain})
        if m.group("code"):
            tokens.append({"type": "text", "text": m.group("code"), "marks": [{"type": "code"}]})
        elif m.group("bold"):
            tokens.append({"type": "text", "text": m.group("bold"), "marks": [{"type": "strong"}]})
        elif m.group("link_text"):
            tokens.append(
                {
                    "type": "text",
                    "text": m.group("link_text"),
                    "marks": [{"type": "link", "attrs": {"href": m.group("link_href")}}],
                }
            )
        elif m.group("italic") or m.group("italic2"):
            italic_text = m.group("italic") or m.group("italic2")
            tokens.append({"type": "text", "text": italic_text, "marks": [{"type": "em"}]})
        pos = m.end()
    if pos < len(text):
        remainder = text[pos:]
        if remainder:
            tokens.append({"type": "text", "text": remainder})
    if not tokens:
        tokens.append({"type": "text", "text": text})
    return tokens


def markdown_to_adf(markdown: str) -> dict[str, Any]:
    """Convert a Markdown string to an ADF document."""
    text = normalize_text(markdown)
    lines = text.split("\n")
    content: list[dict[str, Any]] = []
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            joined = " ".join(paragraph_buffer).strip()
            if joined:
                content.append({"type": "paragraph", "content": _inline_nodes(joined)})
            paragraph_buffer.clear()

    i = 0
    while i < len(lines):
        line = lines[i]

        fence_match = _FENCE_RE.match(line)
        if fence_match:
            flush_paragraph()
            language = fence_match.group(1)
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not _FENCE_RE.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            code_node: dict[str, Any] = {
                "type": "codeBlock",
                "content": [{"type": "text", "text": "\n".join(code_lines)}] if code_lines else [],
            }
            if language:
                code_node["attrs"] = {"language": language}
            content.append(code_node)
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            content.append(
                {
                    "type": "heading",
                    "attrs": {"level": level},
                    "content": _inline_nodes(heading_match.group(2).strip()),
                }
            )
            i += 1
            continue

        bullet_match = _BULLET_RE.match(line)
        ordered_match = _ORDERED_RE.match(line)
        if bullet_match or ordered_match:
            flush_paragraph()
            list_type = "bulletList" if bullet_match else "orderedList"
            item_pattern = _BULLET_RE if bullet_match else _ORDERED_RE
            items: list[dict[str, Any]] = []
            while i < len(lines) and item_pattern.match(lines[i]):
                item_text = item_pattern.match(lines[i]).group(1).strip()
                items.append(
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": _inline_nodes(item_text)}],
                    }
                )
                i += 1
            content.append({"type": list_type, "content": items})
            continue

        if not line.strip():
            flush_paragraph()
            i += 1
            continue

        paragraph_buffer.append(line.strip())
        i += 1

    flush_paragraph()

    if not content:
        content.append({"type": "paragraph", "content": [{"type": "text", "text": ""}]})

    return {"type": "doc", "version": 1, "content": content}


def markdown_to_jira_comment_body(
    markdown: str, *, truncate_pointer: str | None = None
) -> dict[str, Any]:
    """Convert Markdown to an ADF document ready for the Jira add-comment call.

    Truncates the source Markdown (not the built ADF tree) when it exceeds
    the practical comment size limit, appending a pointer to the PR or spec
    file so nothing is silently dropped without a trace (tasks.md §2.3).
    """
    truncated = _truncate(markdown, truncate_pointer)
    return markdown_to_adf(truncated)
