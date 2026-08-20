## ADDED Requirements

### Requirement: Explore precedes propose
The agent SHALL run the OpenSpec explore procedure before the propose procedure. Explore frames the problem and lists open questions; it SHALL NOT write change artifacts.

#### Scenario: Explore surfaces an open question
- **WHEN** exploration finds a question whose answer changes the shape of the solution
- **THEN** that question is carried into `design.md` as an open decision rather than being answered silently during propose

#### Scenario: Propose without explore
- **WHEN** the agent has not explored the card and the implicated code
- **THEN** it does not begin writing artifacts

### Requirement: Specs are grounded in both the card and the code
The agent SHALL read the Jira card (description, acceptance criteria, comments and attachments) and the implicated repository code before writing any artifact. Every requirement in a generated spec SHALL trace to something in one of those two sources.

#### Scenario: Traceback names a file
- **WHEN** a card comment contains a stack trace naming a source file and line
- **THEN** the agent opens that file and reads the enclosing function and its siblings before proposing a fix

#### Scenario: Acceptance criterion has no scenario
- **WHEN** an acceptance criterion on the card cannot be expressed as a scenario
- **THEN** the agent records why in `design.md` rather than dropping it silently

#### Scenario: Requirement with no source
- **WHEN** a proposed requirement cannot be traced to the card or the code
- **THEN** it is not included in the spec

### Requirement: Alert recommendations are treated as hypotheses
Cards raised by monitoring tools often contain a "possible cause" or "recommendation". The agent SHALL treat these as leads to verify against the code, never as requirements.

#### Scenario: Recommendation contradicted by the code
- **WHEN** the card recommends a change that the repository's own conventions argue against
- **THEN** the agent records both positions in `design.md` with evidence, and does not follow the recommendation by default

### Requirement: Product decisions are escalated, not resolved
When resolving the issue requires deciding what the product should do — whether a business rule should exist, which of two defensible behaviours is correct — the agent SHALL present the options with evidence and a recommendation, and SHALL let the spec review gate decide.

#### Scenario: Fix changes what input is accepted
- **WHEN** a candidate fix would change which inputs the system accepts or rejects
- **THEN** the agent writes the options into `design.md`, states its recommendation and the reasoning, and does not implement that part until the spec is approved

#### Scenario: Confirmed defect alongside an open decision
- **WHEN** a card contains both an evidenced defect and an undecided product question
- **THEN** the spec separates them, so the defect can be implemented while the question is answered at the gate

### Requirement: Agent can generate OpenSpec proposal artifact
The agent SHALL generate a `proposal.md` file in `/workspace/openspec/changes/<JIRA-KEY>/` containing the problem statement, scope, and impact of the change.

#### Scenario: Generate proposal from Jira context
- **WHEN** the agent calls `openspec_propose` with a Jira issue key and the issue context
- **THEN** a `proposal.md` file is created at `/workspace/openspec/changes/<JIRA-KEY>/proposal.md` with sections for Why, What Changes, and Impact

#### Scenario: Proposal directory already exists
- **WHEN** the agent calls `openspec_propose` for a Jira key that already has an OpenSpec directory
- **THEN** the existing files are preserved and the agent is notified that artifacts already exist

### Requirement: Agent can generate OpenSpec design artifact
The agent SHALL generate a `design.md` file containing architecture decisions, trade-offs, and technical approach.

#### Scenario: Generate design after proposal
- **WHEN** the agent calls `openspec_propose` with design generation enabled
- **THEN** a `design.md` file is created with sections for Context, Decisions, Risks, and Migration Plan

### Requirement: Agent can generate OpenSpec specification artifacts
The agent SHALL generate specification files under `specs/<capability>/spec.md` for each capability identified in the proposal.

#### Scenario: Generate specs for multiple capabilities
- **WHEN** the agent identifies 3 capabilities in the proposal
- **THEN** 3 spec files are created at `specs/<capability-1>/spec.md`, `specs/<capability-2>/spec.md`, `specs/<capability-3>/spec.md`

#### Scenario: Spec file contains required sections
- **WHEN** a spec file is generated
- **THEN** it SHALL contain ADDED Requirements with at least one `### Requirement:` block and at least one `#### Scenario:` per requirement

### Requirement: Agent can generate OpenSpec tasks artifact
The agent SHALL generate a `tasks.md` file containing an ordered, atomic list of implementation tasks derived from the spec.

#### Scenario: Generate tasks from spec
- **WHEN** the agent calls `openspec_propose` with tasks generation enabled
- **THEN** a `tasks.md` file is created with numbered, checkbox-format tasks, each representing a single atomic unit of work

### Requirement: Agent can validate OpenSpec completeness
The agent SHALL validate that generated specs cover happy paths, sad paths, edge cases, constraints, and acceptance criteria from the Jira issue.

#### Scenario: Spec passes validation
- **WHEN** the agent calls `openspec_validate` on a complete spec
- **THEN** the system returns `{"valid": true, "gaps": []}`

#### Scenario: Spec has gaps
- **WHEN** the agent calls `openspec_validate` on a spec missing edge cases
- **THEN** the system returns `{"valid": false, "gaps": [{"severity": "high", "description": "Missing edge case: ..."}]}`

### Requirement: Agent can read OpenSpec status
The agent SHALL read the current state of OpenSpec artifacts for a change, returning which artifacts exist and their completeness.

#### Scenario: Read status of in-progress change
- **WHEN** the agent calls `openspec_status` for a change with proposal and design complete but specs pending
- **THEN** the system returns a structured status showing proposal=done, design=done, specs=pending, tasks=pending

### Requirement: Agent can archive completed OpenSpec change
The agent SHALL move completed OpenSpec artifacts from `changes/<JIRA-KEY>/` to `changes/archive/<JIRA-KEY>/` and update the change index.

#### Scenario: Archive after merge
- **WHEN** the agent calls `openspec_archive` for a merged change
- **THEN** artifacts are moved to the archive directory and the change index is updated

### Requirement: OpenSpec artifacts are versioned in the feature branch
All OpenSpec artifacts SHALL be committed to the feature branch `feat/spec-<JIRA-KEY>-*` and included in the pull request.

#### Scenario: Artifacts in PR
- **WHEN** the agent creates a pull request
- **THEN** the PR includes all OpenSpec artifacts under `openspec/changes/<JIRA-KEY>/`
