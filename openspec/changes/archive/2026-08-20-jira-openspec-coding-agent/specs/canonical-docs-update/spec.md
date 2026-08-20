## ADDED Requirements

### Requirement: Agent updates living specification after merge
After the implementation PR is merged, the agent SHALL update the canonical specification files under `openspec/specs/<capability>/spec.md` to reflect the implemented state.

#### Scenario: New capability spec created
- **WHEN** a change introduces a new capability and the PR is merged
- **THEN** the agent creates or updates `openspec/specs/<capability>/spec.md` with the final, implemented specification

#### Scenario: Existing capability spec updated
- **WHEN** a change modifies an existing capability and the PR is merged
- **THEN** the agent updates the existing `openspec/specs/<capability>/spec.md` with the delta changes

### Requirement: Agent updates AGENTS.md when conventions change
If the implementation introduces new coding conventions, patterns, or architectural decisions, the agent SHALL update the repository's `AGENTS.md` file.

#### Scenario: New convention introduced
- **WHEN** the implementation establishes a new error handling pattern not documented in AGENTS.md
- **THEN** the agent adds the pattern to AGENTS.md

#### Scenario: No convention changes
- **WHEN** the implementation follows existing conventions documented in AGENTS.md
- **THEN** the agent does not modify AGENTS.md

### Requirement: Agent updates API documentation when public interfaces change
If the implementation modifies public APIs, the agent SHALL update the corresponding API documentation files.

#### Scenario: New endpoint added
- **WHEN** the implementation adds a new REST endpoint
- **THEN** the agent updates the API documentation to include the new endpoint

#### Scenario: Existing endpoint modified
- **WHEN** the implementation changes the request or response schema of an existing endpoint
- **THEN** the agent updates the API documentation to reflect the new schema

### Requirement: Documentation updates are submitted as a separate PR
All documentation updates SHALL be committed to a separate branch and submitted as a separate pull request, distinct from the implementation PR.

#### Scenario: Docs PR created after merge
- **WHEN** the implementation PR is merged
- **THEN** the agent creates a new branch, commits documentation updates, and opens a separate PR titled `docs: update canonical specs for <JIRA-KEY>`

#### Scenario: Docs PR references original issue
- **WHEN** the agent creates the documentation PR
- **THEN** the PR description includes a link to the original Jira issue and the merged implementation PR

### Requirement: Agent archives completed OpenSpec change
After documentation is updated, the agent SHALL archive the OpenSpec change artifacts from `changes/<JIRA-KEY>/` to `changes/archive/<JIRA-KEY>/`.

#### Scenario: Successful archive
- **WHEN** the agent calls `openspec_archive` for a merged and documented change
- **THEN** artifacts are moved to the archive directory and the change index reflects the archived status

### Requirement: Agent handles documentation update failures gracefully
If documentation update fails (e.g., merge conflict, permission issue), the agent SHALL report the failure in the Jira issue and not block workflow completion.

#### Scenario: Docs update fails due to conflict
- **WHEN** the agent attempts to update canonical docs and encounters a merge conflict
- **THEN** the agent posts a comment on the Jira issue describing the conflict and continues to the archive step
