from __future__ import annotations

from agent.utils.adf import (
    markdown_to_adf,
    markdown_to_jira_comment_body,
    normalize_text,
)


def test_normalize_text_replaces_typographic_characters() -> None:
    nasty = "“configuração” — revisão–édita ‘ok’ espaço aqui"
    normalized = normalize_text(nasty)

    assert "“" not in normalized
    assert "”" not in normalized
    assert "‘" not in normalized
    assert "’" not in normalized
    assert "—" not in normalized
    assert "–" not in normalized
    assert " " not in normalized
    assert normalized == "\"configuração\" - revisão-édita 'ok' espaço aqui"


def test_markdown_to_adf_heading_and_paragraph() -> None:
    doc = markdown_to_adf("# Title\n\nSome body text.")

    assert doc["type"] == "doc"
    assert doc["version"] == 1
    assert doc["content"][0] == {
        "type": "heading",
        "attrs": {"level": 1},
        "content": [{"type": "text", "text": "Title"}],
    }
    assert doc["content"][1]["type"] == "paragraph"
    assert doc["content"][1]["content"][0]["text"] == "Some body text."


def test_markdown_to_adf_fenced_code_block_with_language() -> None:
    doc = markdown_to_adf("```python\nprint('hi')\n```")

    code_node = doc["content"][0]
    assert code_node["type"] == "codeBlock"
    assert code_node["attrs"] == {"language": "python"}
    assert code_node["content"] == [{"type": "text", "text": "print('hi')"}]


def test_markdown_to_adf_bullet_list() -> None:
    doc = markdown_to_adf("- first\n- second")

    list_node = doc["content"][0]
    assert list_node["type"] == "bulletList"
    assert len(list_node["content"]) == 2
    assert list_node["content"][0]["type"] == "listItem"
    assert list_node["content"][0]["content"][0]["content"][0]["text"] == "first"


def test_markdown_to_adf_ordered_list() -> None:
    doc = markdown_to_adf("1. first\n2. second")

    list_node = doc["content"][0]
    assert list_node["type"] == "orderedList"
    assert len(list_node["content"]) == 2


def test_markdown_to_adf_inline_marks() -> None:
    doc = markdown_to_adf("Some **bold**, *italic*, `code`, and a [link](https://example.com).")

    tokens = doc["content"][0]["content"]
    bold = next(t for t in tokens if t["text"] == "bold")
    italic = next(t for t in tokens if t["text"] == "italic")
    code = next(t for t in tokens if t["text"] == "code")
    link = next(t for t in tokens if t["text"] == "link")

    assert bold["marks"] == [{"type": "strong"}]
    assert italic["marks"] == [{"type": "em"}]
    assert code["marks"] == [{"type": "code"}]
    assert link["marks"] == [{"type": "link", "attrs": {"href": "https://example.com"}}]


def test_markdown_to_adf_empty_input_produces_valid_doc() -> None:
    doc = markdown_to_adf("")

    assert doc == {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": ""}]}],
    }


def _flatten_text(doc: dict) -> str:
    return "".join(
        text_node.get("text", "")
        for node in doc["content"]
        for text_node in node.get("content", [])
    )


def test_markdown_to_jira_comment_body_truncates_oversized_input() -> None:
    huge = "x" * 40_000
    body = markdown_to_jira_comment_body(huge, truncate_pointer="PR #123")

    rendered_text = _flatten_text(body)
    assert "truncated" in rendered_text
    assert "PR #123" in rendered_text
    assert len(rendered_text) < 40_000


def test_markdown_to_jira_comment_body_leaves_small_input_untouched() -> None:
    body = markdown_to_jira_comment_body("short and sweet")

    assert body["content"][0]["content"][0]["text"] == "short and sweet"
