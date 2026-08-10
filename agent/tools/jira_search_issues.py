from typing import Any

from ..utils.jira import search_issues


async def jira_search_issues(
    jql: str,
    next_page_token: str | None = None,
    max_results: int = 50,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Search Jira issues via JQL.

    Args:
        jql: A JQL query string, e.g. "project = SSAI AND status = BACKLOG".
        next_page_token: Opaque pagination token from a previous page
            (the new /search/jql endpoint paginates by token, not offset).
        max_results: Maximum results to return.
        fields: Optional list of fields to include in each returned issue.

    Returns:
        Dictionary with 'issues' and 'next_page_token' (None on the last page).
    """
    return await search_issues(
        jql, next_page_token=next_page_token, max_results=max_results, fields=fields
    )
