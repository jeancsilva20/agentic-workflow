from typing import Any

from ..utils.jira import get_issue


async def jira_get_issue(issue_key: str) -> dict[str, Any]:
    """Get a Jira issue by its key.

    Args:
        issue_key: The Jira issue key, e.g. "SSAI-88".

    Returns:
        Dictionary with 'issue' containing full issue details, or 'error' if
        Jira credentials are unset or the request failed.
    """
    return await get_issue(issue_key)
