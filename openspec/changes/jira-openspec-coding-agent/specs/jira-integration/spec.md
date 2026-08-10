## ADDED Requirements

### Requirement: Agent can read Jira issue details
The agent SHALL retrieve a Jira issue by its key, including title, description, acceptance criteria, status, assignee, and custom fields.

#### Scenario: Read existing issue
- **WHEN** the agent calls `jira_get_issue` with a valid issue key (e.g., `JIRA-1234`)
- **THEN** the system returns a structured object containing the issue title, description, status, assignee, and all visible fields

#### Scenario: Read non-existent issue
- **WHEN** the agent calls `jira_get_issue` with an invalid or non-existent issue key
- **THEN** the system returns an error indicating the issue was not found

### Requirement: Agent can search Jira issues
The agent SHALL search Jira issues by free-text query, project, status, or assignee.

#### Scenario: Search by project
- **WHEN** the agent calls `jira_search_issues` with a project key filter
- **THEN** the system returns a list of matching issues with key, title, and status

#### Scenario: Search with no results
- **WHEN** the agent calls `jira_search_issues` with criteria matching no issues
- **THEN** the system returns an empty list

### Requirement: Agent can read Jira issue comments
The agent SHALL retrieve all comments on a Jira issue, including author, timestamp, and body.

#### Scenario: Read comments on issue with discussion
- **WHEN** the agent calls `jira_get_comments` for an issue that has comments
- **THEN** the system returns a list of comments ordered by creation time, each with author, timestamp, and body

#### Scenario: Read comments on issue with no comments
- **WHEN** the agent calls `jira_get_comments` for an issue with no comments
- **THEN** the system returns an empty list

### Requirement: Agent can add comments to Jira issues
The agent SHALL accept a Markdown body and SHALL convert it to Atlassian Document Format before posting, because Jira REST v3 does not accept Markdown.

#### Scenario: Post comment with plan summary
- **WHEN** the agent calls `jira_add_comment` with an issue key and a Markdown body containing the OpenSpec plan summary
- **THEN** the body is converted to ADF and the comment is posted to the issue, visible to all project members

#### Scenario: Post comment containing typographic characters
- **WHEN** the Markdown body contains curly quotes, en/em dashes, non-breaking spaces or accented Portuguese text
- **THEN** those characters are normalised before the request and Jira does not return `INVALID_INPUT` or HTTP 400

#### Scenario: Post comment exceeding size limit
- **WHEN** the agent attempts to post a comment exceeding the Jira comment size limit
- **THEN** the body is truncated and a pointer to the pull request or spec file is appended

### Requirement: Agent can transition Jira issues between columns by name
The agent SHALL move a Jira issue to a target column identified by its display name. Because the Jira REST API accepts only a transition id, the client SHALL resolve the name to an id before performing the move.

#### Scenario: Move to spec review column
- **WHEN** the agent calls `jira_transition_issue` with issue key `JIRA-1234` and target column `Em Revisão de Spec`
- **THEN** the client fetches the available transitions, resolves `Em Revisão de Spec` to its transition id, performs the transition, and the issue status changes

#### Scenario: Target column not reachable from current status
- **WHEN** the target column name does not appear among the transitions available from the issue's current status
- **THEN** the system returns an error naming the requested column and listing the columns that are reachable

#### Scenario: Target column name unknown
- **WHEN** the target column name does not exist in the project workflow
- **THEN** the system returns an error distinguishing an unknown column from an unreachable one

### Requirement: Jira tools degrade gracefully when credentials are absent
The agent SHALL start without Jira tools if Jira credentials are unconfigured, and SHALL notify the user of the limitation.

#### Scenario: Credentials not configured
- **WHEN** `JIRA_BASE_URL`, `JIRA_EMAIL` or `JIRA_API_TOKEN` is not set
- **THEN** the agent starts without Jira tools and includes a notification in the system prompt that Jira integration is unavailable

### Requirement: Jira tokens never reach the sandbox
Jira authentication credentials SHALL be managed server-side in the LangGraph process and SHALL NOT be placed in the sandbox environment.

#### Scenario: Sandbox command execution
- **WHEN** the agent executes any command in the sandbox
- **THEN** no Jira API token or credential is present in environment variables, files, or command output
