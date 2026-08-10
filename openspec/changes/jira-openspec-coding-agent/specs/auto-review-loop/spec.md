## ADDED Requirements

### Requirement: Agent self-reviews spec before requesting human approval
The agent SHALL review its own generated OpenSpec artifacts for completeness and correctness before transitioning the issue to the spec review column.

#### Scenario: Spec passes self-review on first attempt
- **WHEN** the agent reviews a complete spec covering all acceptance criteria, edge cases, and constraints
- **THEN** the agent proceeds to the spec approval gate

#### Scenario: Spec fails self-review with minor gaps
- **WHEN** the agent finds missing edge cases in the spec
- **THEN** the agent returns to spec generation to fill the gaps and increments the review cycle counter

#### Scenario: Spec self-review stops with gaps remaining
- **WHEN** the agent stops iterating on the spec while gaps remain
- **THEN** the agent posts a Jira comment summarising the remaining gaps and moves the issue to `Em Revisão de Spec`, the same gate column used when the spec passes
- **NOTE** the system prompt asks for at most 3 cycles, but the count is guidance and is not enforced — see design.md Decision 5. What is required is that the agent never parks silently.

### Requirement: Agent self-reviews code before requesting human approval
The agent SHALL review its own implemented code against the OpenSpec specification before invoking the reviewer graph.

#### Scenario: Code passes self-review on first attempt
- **WHEN** the agent reviews code that fully implements the spec, passes lint, and passes tests
- **THEN** the agent proceeds to invoke the reviewer graph

#### Scenario: Code fails self-review with test failures
- **WHEN** the agent finds failing tests during self-review
- **THEN** the agent returns to implementation to fix the failures and increments the review cycle counter

#### Scenario: Code fails self-review with missing acceptance criteria
- **WHEN** the agent finds unimplemented acceptance criteria during self-review
- **THEN** the agent returns to implementation to implement the missing criteria and increments the review cycle counter

#### Scenario: Code self-review stops with issues remaining
- **WHEN** the agent stops iterating on the code while issues remain
- **THEN** the agent posts a Jira comment summarising the remaining issues and moves the issue to `Em Code Review`, the same gate column used when the code passes
- **NOTE** the 3-cycle target is guidance, not an enforced limit — see design.md Decision 5.

### Requirement: Self-review cycles are logged, not enforced
The agent SHALL emit a console log event per self-review cycle so that iteration depth is observable after the fact. The system SHALL NOT depend on the cycle count for correctness.

#### Scenario: Agent iterates more than the guidance
- **WHEN** the agent runs more self-review cycles than the prompt suggests
- **THEN** each cycle appears in the execution log, and the run is bounded only by the runtime's own model-call and time limits

#### Scenario: Agent iterates fewer than the guidance
- **WHEN** the agent judges the spec or code complete after a single cycle
- **THEN** it proceeds to the gate without artificial extra cycles

### Requirement: Self-review checks spec coverage
During spec self-review, the agent SHALL verify that the specification covers all items from the Jira issue's acceptance criteria.

#### Scenario: All acceptance criteria covered
- **WHEN** the Jira issue has 5 acceptance criteria and the spec addresses all 5
- **THEN** the coverage check passes

#### Scenario: Missing acceptance criterion
- **WHEN** the Jira issue has 5 acceptance criteria and the spec addresses only 4
- **THEN** the agent identifies the missing criterion as a gap

### Requirement: Self-review checks scenario completeness
During spec self-review, the agent SHALL verify that each requirement has happy path, sad path, and edge case scenarios.

#### Scenario: Requirement has all scenario types
- **WHEN** a requirement has scenarios for successful operation, error handling, and boundary conditions
- **THEN** the scenario completeness check passes

#### Scenario: Requirement missing sad path
- **WHEN** a requirement has happy path and edge case scenarios but no error handling scenario
- **THEN** the agent identifies the missing sad path as a gap

### Requirement: Self-review checks implementation fidelity
During code self-review, the agent SHALL verify that every task in `tasks.md` is implemented and every requirement in the spec is satisfied.

#### Scenario: All tasks implemented
- **WHEN** all tasks in `tasks.md` are marked as complete and all spec requirements have corresponding code
- **THEN** the implementation fidelity check passes

#### Scenario: Unimplemented task
- **WHEN** a task in `tasks.md` is not marked complete
- **THEN** the agent identifies the unimplemented task as an issue

### Requirement: Self-review checks test coverage
During code self-review, the agent SHALL verify that tests exist for all modified code paths and that all tests pass.

#### Scenario: Adequate test coverage
- **WHEN** all modified functions have corresponding tests and all tests pass
- **THEN** the test coverage check passes

#### Scenario: Missing test for new function
- **WHEN** a new function has no corresponding test
- **THEN** the agent identifies the missing test as an issue

### Requirement: Review iteration is bounded by the runtime, not by a counter
The system prompt SHALL target roughly 3 self-review cycles for both spec and code review. No component SHALL count or enforce them, and no behaviour SHALL depend on the count being accurate.

#### Scenario: Self-review converges
- **WHEN** the agent's checks pass on any cycle
- **THEN** the agent proceeds to the next workflow step without further cycles

#### Scenario: Agent hands over around the target
- **WHEN** the agent has iterated about three times and issues remain
- **THEN** it stops, comments what is unresolved, and parks at the gate

#### Scenario: Agent exceeds the target
- **WHEN** the agent iterates past the suggested number
- **THEN** nothing intervenes on the count; the run is bounded only by `ModelCallLimitMiddleware`, `timeout_wrapup`, and the step limit, and each extra cycle is visible in the execution log
