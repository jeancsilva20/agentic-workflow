from typing import Any

from ..utils.adf import markdown_to_jira_comment_body
from ..utils.jira import add_comment


async def jira_add_comment(
    issue_key: str, comment_body: str, truncate_pointer: str | None = None
) -> dict[str, Any]:
    """Post a Markdown-formatted comment to a Jira issue.

    The Markdown is converted to Atlassian Document Format and character-
    normalized (curly quotes, dashes, non-breaking spaces) before posting —
    Jira's comment endpoint requires ADF, not raw Markdown, and rejects those
    typographic characters outright.

    Args:
        issue_key: The Jira issue key to comment on, e.g. "SSAI-88".
        comment_body: Markdown-formatted comment text.
        truncate_pointer: Optional pointer (PR URL, spec file path) appended
            if the comment is truncated for exceeding Jira's size limit.

    Returns:
        Dictionary with 'success' (bool) key, or 'error' if credentials are
        unset or the request failed.
    """
    adf_body = markdown_to_jira_comment_body(comment_body, truncate_pointer=truncate_pointer)
    return await add_comment(issue_key, adf_body)
