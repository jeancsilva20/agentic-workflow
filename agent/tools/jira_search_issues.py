from typing import Any

from ..utils.jira import search_issues


async def jira_search_issues(
    jql: str,
    start_at: int = 0,
    max_results: int = 50,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Search Jira issues via JQL.

    Args:
        jql: A JQL query string, e.g. "project = SSAI AND status = BACKLOG".
        start_at: Pagination offset.
        max_results: Maximum results to return.
        fields: Optional list of fields to include in each returned issue.

    Returns:
        Dictionary with 'issues', 'total', and 'start_at'.
    """
    return await search_issues(jql, start_at=start_at, max_results=max_results, fields=fields)
