---
name: openspec-propose
description: Generate proposal.md, design.md, specs/*/spec.md, and tasks.md for a Jira card's change, in one pass. Use after openspec-explore has framed the problem, during PASSO 3 of the Jira workflow (see design.md "Complete Agent Workflow").
metadata:
  author: openspec
  version: "1.0"
  ported_from: ".claude/skills/openspec-propose/SKILL.md"
  ported_because: >
    The shipped skill drives the `openspec` CLI (`openspec new change`, `openspec
    status --json`, `openspec instructions <id> --json`) to scaffold the change
    and fetch each artifact's template/instruction. No CLI exists in this
    sandbox (Decision 4), so this version writes the directory structure
    directly with `write_file` and carries the `spec-driven` schema's
    templates and instructions inline below instead of fetching them.
---

Propose a change for the current Jira issue — write `proposal.md`, `specs/<capability>/spec.md`, `design.md` (when warranted), and `tasks.md` directly into `openspec/changes/<name>/` in the sandbox.

**Prerequisite:** run the **openspec-explore** procedure first (or at minimum: read the full Jira card — description, acceptance criteria, all comments — and the code it implicates). This skill assumes that grounding already happened; it does not re-derive it.

---

## 1. Determine the change name

Derive a kebab-case name from the Jira issue key and a short slug of the summary, e.g. issue `SSAI-142` "Allow digits in customer names" → `ssai-142-allow-digits-in-names`. Check whether `openspec/changes/<name>/` already exists (`ls`); if it does, this is a resume, not a fresh proposal — read what's there and continue from the first missing or incomplete artifact instead of starting over.

## 2. Scaffold the change directory

There is no `openspec new change` command here. Create the structure directly:

```
openspec/changes/<name>/.openspec.yaml
openspec/changes/<name>/proposal.md
openspec/changes/<name>/specs/<capability>/spec.md   (one per capability)
openspec/changes/<name>/design.md                     (when warranted, see step 5)
openspec/changes/<name>/tasks.md
```

`.openspec.yaml` content (matches every other change in this repo):

```yaml
schema: spec-driven
```

## 3. Write `proposal.md` — establishes WHY

Sections, filled in exactly this order:

- **Why** — 1-2 sentences: what problem does this solve, why now. Ground this in the card, not in the recommendation it contains (see grounding rule 4 in openspec-explore).
- **What Changes** — bullet list, specific about new capabilities, modifications, or removals. Mark anything breaking with **BREAKING**.
- **Capabilities**
  - **New Capabilities** — one entry per capability being introduced, kebab-case (e.g. `user-auth`), each becomes `specs/<name>/spec.md`.
  - **Modified Capabilities** — existing capabilities whose *requirements* change (not just their implementation). Check `openspec/specs/` for existing names; leave empty if nothing at the requirement level changes.
- **Impact** — affected code, APIs, dependencies, systems.

The Capabilities section is the contract between this file and the specs step — every capability named here needs a matching spec file next. Keep the whole document to 1-2 pages; implementation detail belongs in `design.md`, not here.

## 4. Write `specs/<capability>/spec.md` — establishes WHAT, one file per capability

Delta format, using `##` headers:
- **ADDED Requirements** — new capabilities
- **MODIFIED Requirements** — changed behavior; paste the ENTIRE existing requirement block from `openspec/specs/<capability>/spec.md` (if the capability already exists) and edit it, not just the diff — partial content loses detail at archive time
- **REMOVED Requirements** — include **Reason** and **Migration**
- **RENAMED Requirements** — `FROM:` / `TO:` only

Each requirement: `### Requirement: <name>` with SHALL/MUST language (avoid should/may), followed by one or more `#### Scenario: <name>` blocks in WHEN/THEN form. **Scenarios must use exactly four hashtags** — three hashtags or a bare bullet list is silently ignored by anything that later parses this file. Every requirement needs at least one scenario; every scenario should be a plausible test case.

Example:

```markdown
## ADDED Requirements

### Requirement: User can export data
The system SHALL allow users to export their data in CSV format.

#### Scenario: Successful export
- **WHEN** user clicks "Export" button
- **THEN** system downloads a CSV file with all user data
```

Per the grounding rules: every requirement here must trace to something in the card or in the code you read. If you cannot point at the source, it does not belong in the spec. Every acceptance criterion on the card must appear as a scenario; if one cannot be turned into a scenario, say why in `design.md` instead of silently dropping it.

## 5. Write `design.md` — establishes HOW (create only if warranted)

Create `design.md` only when at least one applies: the change is cross-cutting (multiple modules), it introduces a new external dependency or a real data-model change, it has security/performance/migration complexity, or there's ambiguity worth resolving in writing before code is touched. A one-file bugfix with an obvious shape does not need one.

Sections:
- **Context** — background, current state, constraints
- **Goals / Non-Goals**
- **Decisions** — key technical choices with rationale (why X over Y), alternatives considered
- **Risks / Trade-offs** — `[Risk] → Mitigation` pairs
- **Open Questions** — **this is where every product decision the grounding rules told you not to resolve goes.** Write the options with evidence for each, state a recommendation, and stop — the spec-review gate (APPROVAL 1) answers it, not you.

## 6. Write `tasks.md` — the implementation checklist

**Every task must be a literal checkbox** — `- [ ] X.Y Task description` — grouped under numbered `##` headings, ordered by dependency. This is the file `agent/tools/openspec_status.py` and the auto-review loop both read to compute progress; anything not in checkbox form is invisible to them.

```markdown
## 1. Setup

- [ ] 1.1 Create new module structure
- [ ] 1.2 Add the new dependency

## 2. Core Implementation

- [ ] 2.1 Implement the behavior
- [ ] 2.2 Add tests
```

Tasks should be small enough to finish in one self-review cycle and individually verifiable — you should be able to tell when a task is actually done, not just attempted.

## 7. Log the lifecycle event

Call `log_openspec_event("proposal_generated", detail=<change-name>, issue_key=<KEY>)` once every
artifact is on disk, so the console's execution log records that this run produced its spec.

## 8. Confirm before moving on

Re-read each file you wrote once, checking: every capability named in the proposal has a spec file; every spec requirement traces to card or code; every open product decision lives in `design.md`, not silently resolved; every task is a real checkbox. Then proceed to the spec self-review loop (PASSO 4) — this skill only authors the artifacts, it does not review them.

---

## Guardrails

- Create every artifact the change needs before moving to self-review — a proposal with no matching spec file is an incomplete hand-off, not a smaller one
- Never resolve a product decision to keep momentum — write it into `design.md` and let APPROVAL 1 decide (this is the one guardrail most worth repeating: there is no user to interactively ask in this agent, so "ask" always means "write it down")
- If a change directory for this issue already exists, treat this as a resume: read what's there, don't overwrite artifacts that already reflect a human's feedback from a prior `Ajustar Spec` cycle
- Verify each file actually exists after writing it before treating that artifact as done
