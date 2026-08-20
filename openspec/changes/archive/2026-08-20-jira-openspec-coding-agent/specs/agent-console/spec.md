## ADDED Requirements

### Requirement: Console reports whether the agent is alive
The console SHALL display a single overall status and the time since the last poller tick, so a stopped poller is visible without reading server logs.

#### Scenario: Poller ticking normally
- **WHEN** the last tick arrived within two polling intervals
- **THEN** the console shows the derived status and the age of the last tick

#### Scenario: Poller stopped
- **WHEN** no tick has arrived for more than two polling intervals
- **THEN** the console shows a degraded status naming the poller as the cause

#### Scenario: No tick ever received
- **WHEN** the console has received no tick since starting
- **THEN** it says so explicitly rather than showing a healthy status

### Requirement: Console distinguishes working from waiting
The status SHALL separate `working` (the agent is executing) from `waiting` (the agent is parked on a human), because the two look identical from outside and require opposite responses.

#### Scenario: Agent implementing
- **WHEN** at least one run is executing
- **THEN** the status is `working`

#### Scenario: Agent parked at a gate
- **WHEN** no run is executing and at least one is parked or queued
- **THEN** the status is `waiting`, signalling that a human is the blocker

#### Scenario: Nothing to do
- **WHEN** there are no queued cards and no active runs
- **THEN** the status is `idle`

#### Scenario: Run ends without reaching waiting or done
- **WHEN** a run reported by the runtime-forced-termination hook ends without calling `jira_park_at_gate` and without completing the workflow
- **THEN** that run's status is `dead`, distinct from `working`, `waiting`, and `idle`, and it does not simply disappear from the active-runs list

### Requirement: Console shows the card queue
The console SHALL list cards sitting in the trigger column that do not yet have a run, with how long each has been waiting.

#### Scenario: Cards waiting to be picked up
- **WHEN** cards sit in `BACKLOG` without a thread
- **THEN** each appears with its key, summary, and time in queue

#### Scenario: Empty queue
- **WHEN** no card is waiting
- **THEN** the queue panel states that explicitly

### Requirement: Console shows active runs with time parked
Each active run SHALL display its issue key, current step, Jira column, elapsed time, and — when parked — how long it has been parked.

#### Scenario: Run parked at a gate
- **WHEN** a run is parked awaiting human approval
- **THEN** its entry shows the gate column and the time parked, exposing human bottlenecks

#### Scenario: Run in error
- **WHEN** a run has failed
- **THEN** its entry shows the error message distinctly from normal steps

### Requirement: Console shows a live execution log
The console SHALL display a rolling log of agent and poller events with timestamp, issue key, and message, distinguishing warnings and errors.

#### Scenario: New events arrive
- **WHEN** the agent posts log events while the page is open
- **THEN** they appear within one refresh interval and the view auto-scrolls unless the user has scrolled up

#### Scenario: Log exceeds retention
- **WHEN** more events arrive than the buffer holds
- **THEN** the oldest are evicted and the console keeps serving without error

### Requirement: Console reports token and cost usage per card
Every agent run SHALL carry standardized trace metadata (Jira issue key, thread, agent role, workflow stage, model, effort, routing mode, complexity tier, routing reason). The console SHALL expose, per card, the total tokens and cost of every run the card spans and an ordered timeline of those runs. Usage SHALL be collected after a run completes, never per token.

#### Scenario: One card spans several runs
- **WHEN** a card is worked on across several human-in-the-loop runs on different threads
- **THEN** its usage is reported as one total, aggregated by issue key across all of them, and broken down by model and by agent role

#### Scenario: Cost is unknown
- **WHEN** the tracing backend reports no cost and the model is absent from the fallback pricing table
- **THEN** the cost is reported as unknown, never as zero, and the number of runs missing a cost is reported alongside the total

#### Scenario: Routing decision recorded
- **WHEN** a run is dispatched, escalated, or completes
- **THEN** one execution-log line is written for the routing decision, one for the run's token total, and one for the card's updated cost

### Requirement: Console never exposes tracing credentials
No console endpoint SHALL return the tracing backend's API key or any other credential. The console SHALL NOT hold a tracing credential at all: it is fed usage by pushed events, and only the agent process talks to the tracing backend.

#### Scenario: Observability endpoint is read
- **WHEN** any observability endpoint is called
- **THEN** the response contains usage and routing data only, with no credential or backend endpoint in it

### Requirement: Console cannot affect the workflow
The console SHALL be a read-only display fed by events pushed to it. It SHALL NOT call Jira, LangGraph, or the agent, and a console failure SHALL NOT affect any run.

#### Scenario: Console is down
- **WHEN** the agent or poller pushes an event and the console is unreachable
- **THEN** the push fails silently within a short timeout and the run proceeds unaffected

#### Scenario: Console restarted
- **WHEN** the console process restarts and loses its in-memory state
- **THEN** it repopulates from subsequent events without any run being disturbed
