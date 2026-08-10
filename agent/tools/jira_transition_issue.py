from typing import Any

from ..utils.jira import JiraTransitionError, transition_to_column


async def jira_transition_issue(issue_key: str, column_name: str) -> dict[str, Any]:
    """Move a Jira issue to a target column by name.

    Args:
        issue_key: The Jira issue key to transition, e.g. "SSAI-88".
        column_name: The target column name, e.g. "Em Revisão de Spec".

    Returns:
        Dictionary with 'success' (bool), or 'success': False plus 'error'
        naming the available target columns when column_name does not
        resolve to a transition currently offered by the issue.
    """
    try:
        return await transition_to_column(issue_key, column_name)
    except JiraTransitionError as exc:
        return {"success": False, "error": str(exc)}
