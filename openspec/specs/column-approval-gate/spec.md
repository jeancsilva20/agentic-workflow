## ADDED Requirements

### Requirement: A poller ticks continuously and detects trigger cards
A poller SHALL run on a fixed interval (default 60s) and SHALL launch one agent thread per card sitting in the `BACKLOG` column.

#### Scenario: Card moved to trigger column
- **WHEN** a Jira issue is moved to `BACKLOG` by a human
- **THEN** the next poller tick launches an agent thread whose id is derived from the issue key, and the workflow begins at PASSO 1

#### Scenario: No cards to pick up
- **WHEN** a tick finds no cards in the trigger column and no parked thread whose column changed
- **THEN** the poller records the tick and does nothing else

#### Scenario: Card already has a thread
- **WHEN** a tick finds a card in the trigger column that already has a live thread
- **THEN** no second thread is launched

#### Scenario: Duplicate tick
- **WHEN** two ticks run against the same board state
- **THEN** the second produces no additional threads or re-triggers

### Requirement: Agent moves card to indicate progress
The agent SHALL transition the Jira issue to the appropriate column at each workflow milestone.

#### Scenario: Move to development column
- **WHEN** the agent begins PASSO 1 (collect context)
- **THEN** the agent transitions the issue to `In Progress`

#### Scenario: Move to spec review column
- **WHEN** the agent completes spec generation and auto-review passes
- **THEN** the agent transitions the issue to `Em Revisão de Spec`

#### Scenario: Move to code review column
- **WHEN** the agent completes implementation and reviewer graph passes
- **THEN** the agent transitions the issue to `Em Code Review`

#### Scenario: Move to merge column
- **WHEN** the agent creates the pull request
- **THEN** the agent transitions the issue to `Em Merge`

#### Scenario: Move to concluded column
- **WHEN** the agent completes all post-merge steps
- **THEN** the agent transitions the issue to `Done`

### Requirement: Agent ends its run at a gate instead of blocking
On reaching an approval gate the agent SHALL commit its work, post a Jira comment, transition the card, mark the thread as parked, and **end the run**. It SHALL NOT sleep or block waiting for a human.

#### Scenario: Agent reaches the spec gate
- **WHEN** the agent finishes spec generation and auto-review
- **THEN** it commits the OpenSpec artifacts, comments on the issue, moves the card to `Em Revisão de Spec`, records the parked state in thread metadata, and the run ends

#### Scenario: Human takes hours to respond
- **WHEN** a card sits at a gate longer than the agent run time limit
- **THEN** no run is consuming time, and resumption is unaffected

### Requirement: Poller resumes parked threads on column change
Each tick SHALL check the current column of every parked thread's card and re-trigger the thread when it has changed, passing the new column and any comments added since parking.

#### Scenario: Human approves spec
- **WHEN** a parked card moves from `Em Revisão de Spec` to `Spec Aprovada`
- **THEN** the next tick re-triggers the thread and the agent resumes at PASSO 5 (implementation)

#### Scenario: Human requests spec adjustments
- **WHEN** a parked card moves from `Em Revisão de Spec` to `Ajustar Spec` with a comment
- **THEN** the next tick re-triggers the thread and the agent resumes at PASSO 3, incorporating the comment as feedback

#### Scenario: Human approves code
- **WHEN** a parked card moves from `Em Code Review` to `Code Review Aprovado`
- **THEN** the agent resumes at PASSO 8 (final tests + push + PR)

#### Scenario: Human requests code adjustments
- **WHEN** a parked card moves from `Em Code Review` to `Ajustar Code` with a comment
- **THEN** the agent resumes at PASSO 5, incorporating the comment as feedback

#### Scenario: Human merges PR
- **WHEN** a parked card moves from `Em Merge` to `Mergeado`
- **THEN** the agent resumes at PASSO 9 (archive spec)

#### Scenario: Card has not moved
- **WHEN** a tick finds a parked card still in its gate column
- **THEN** the thread is not re-triggered

#### Scenario: Sandbox lost while parked
- **WHEN** a resumed thread cannot reach its sandbox
- **THEN** the agent reports the failure as a Jira comment rather than silently restarting from scratch, and the committed branch remains intact

### Requirement: Agent signals auto-review exhaustion without a dedicated column
When an auto-review loop exhausts its cycles, the agent SHALL post a Jira comment listing what it could not resolve and SHALL park in the normal gate column for that phase. It SHALL NOT use a separate column for this case.

#### Scenario: Spec auto-review exhausted
- **WHEN** spec auto-review reaches its cycle limit with unresolved gaps
- **THEN** the agent posts a comment enumerating the gaps and transitions the issue to `Em Revisão de Spec`, entering the same waiting state as a clean spec

#### Scenario: Code auto-review exhausted
- **WHEN** code auto-review reaches its cycle limit with unresolved problems
- **THEN** the agent posts a comment enumerating the problems and transitions the issue to `Em Code Review`, entering the same waiting state as clean code

#### Scenario: Human responds to an exhaustion comment
- **WHEN** a human reads the exhaustion comment and moves the card to `Ajustar Spec` or `Ajustar Code` with guidance
- **THEN** the agent resumes exactly as it would for a human-initiated adjustment, incorporating the comment as feedback

### Requirement: Column names are configurable
The Jira column names used by the approval gate middleware SHALL be configurable via environment variables with sensible defaults.

#### Scenario: Custom column names
- **WHEN** `JIRA_COLUMN_SPEC_REVIEW` is set to `Revisão Técnica`
- **THEN** the agent uses `Revisão Técnica` instead of the default `Em Revisão de Spec`

#### Scenario: Default column names
- **WHEN** no custom column name environment variables are set
- **THEN** the agent uses the documented default column names

### Requirement: Jira workflow allows global transitions
The Jira project workflow SHALL permit every status to transition to every other status, because the agent's path through the board is not linear.

#### Scenario: Agent moves to a non-adjacent column
- **WHEN** the agent transitions an issue from `In Progress` directly to `Em Merge`
- **THEN** the transition succeeds without an intermediate move

#### Scenario: Human routes a card backwards
- **WHEN** a human moves a card from `Em Code Review` back to `Ajustar Spec`
- **THEN** the transition is permitted and the agent resumes at spec generation

### Requirement: Polling interval is configurable
The interval at which the agent polls Jira for column changes SHALL be configurable.

#### Scenario: Custom polling interval
- **WHEN** `JIRA_POLL_INTERVAL_SECONDS` is set to `30`
- **THEN** the poller ticks every 30 seconds

#### Scenario: Default polling interval
- **WHEN** `JIRA_POLL_INTERVAL_SECONDS` is not set
- **THEN** the poller ticks every 60 seconds

### Requirement: Agent reports runtime-forced termination
When a run ends because a runtime limit fired (model call cap, step limit, or wrap-up timeout) rather than the agent reaching a gate voluntarily, the system SHALL post a Jira comment naming the limit that was hit, instead of leaving the card silently unchanged.

#### Scenario: Run ends without parking
- **WHEN** the run terminates via `ModelCallLimitMiddleware` or the step limit before the agent has called `jira_park_at_gate`
- **THEN** a comment is posted to the issue naming the limit that was hit, and the console reflects `dead` instead of the run silently disappearing from the active list

#### Scenario: Wrap-up timeout produces a park
- **WHEN** `timeout_wrapup` fires and the agent complies by calling `jira_park_at_gate` before its turn ends
- **THEN** this counts as a normal gate park, not a runtime-forced termination — no separate comment or `dead` status is needed
