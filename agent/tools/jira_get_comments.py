from typing import Any

from ..utils.jira import get_comments


async def jira_get_comments(issue_key: str) -> dict[str, Any]:
    """Get all comments on a Jira issue.

    Args:
        issue_key: The Jira issue key, e.g. "SSAI-88".

    Returns:
        Dictionary with 'comments' (list of comment objects).
    """
    return await get_comments(issue_key)
