---
name: openspec-verify
description: Verify the implementation on the branch actually matches the change's OpenSpec artifacts — requirements, scenarios, tasks checklist, design decisions — and surface every divergence before the run is handed to a human code review. Run this at the end of PASSO 6 (code self-review), after the code is written and before parking at `Em Code Review`.
metadata:
  author: openspec
  version: "1.0"
  ported_from: "Fission-AI/OpenSpec skills/openspec-verify-change/SKILL.md"
  upstream_pin: "see openspec/openspec-version.yaml (source, version, commit)"
  ported_because: >
    The upstream skill declares `compatibility: Requires openspec CLI` and drives
    `openspec status`, `openspec instructions apply` and `openspec list` to locate
    artifacts. There is no openspec binary in this sandbox (design.md Decision 4),
    and no synchronous user to prompt for a change name — the Jira issue key
    determines the change. This port keeps the three verification dimensions
    (completeness, correctness, coherence) and the CRITICAL/WARNING/SUGGESTION
    severity model, and replaces every CLI call with `ls` / `read_file` / `grep`
    / `execute`.
---

Verify that what is on the branch matches what the spec promised.

**This is a reasoning and code-reading step, not a binary.** Nothing executes this skill for you and no tool returns a pass/fail. You read the artifacts, you read the code, and you decide — using `ls`, `glob`, `read_file`, `grep` and `execute` (for tests and lint). `openspec_validate` checks the artifacts' *structure*; it says nothing about whether the code matches them. That is this skill's job.

---

## 1. Locate the change and load its artifacts

There is no `openspec list` here. Read the change directly:

1. `ls openspec/changes/` and pick the directory for this Jira issue (its name starts with the issue key slug — see openspec-propose step 1). If more than one matches, the active change is the one whose `tasks.md` has unchecked boxes; say which you picked before continuing.
2. Read, in this order: `proposal.md`, `specs/*/spec.md` (every capability), `design.md` (if present), `tasks.md`.
3. Note which artifacts are missing — verification degrades gracefully (see below), but a missing artifact is itself worth reporting.

Announce the change name you are verifying. A verification report against the wrong change is worse than none.

## 2. Build the report in three dimensions

Every finding gets a severity:

- **CRITICAL** — must be fixed before the code-review gate.
- **WARNING** — should be fixed; name it explicitly in the gate comment if it survives.
- **SUGGESTION** — worth doing, not blocking.

When you are uncertain, downgrade: prefer SUGGESTION over WARNING and WARNING over CRITICAL. A false CRITICAL costs a human's time at the gate; a missed SUGGESTION costs nothing.

### Completeness — is everything the spec asked for actually there?

- **Tasks checklist.** Read every `- [ ]` / `- [x]` in `tasks.md`. For each unchecked task, decide which it is: *not done* (CRITICAL — implement it, or explain in the gate comment why it is deferred) or *done but unmarked* (fix the checkbox — an unmarked completed task makes `openspec_status` and the gate comment lie). Never tick a box for work that is not on the branch.
- **Requirement coverage.** For each `### Requirement:` in each spec file, find the code that implements it. `grep` for the identifiers, endpoints, error types and field names the requirement names. A requirement with no corresponding code is CRITICAL: "Requirement not implemented: `<name>`".

### Correctness — does the code do what the requirement says?

- **Requirement → implementation mapping.** For each requirement, record `path/to/file.py:<lines>` where it is satisfied, then read those lines and compare against the requirement's wording. Status codes, exception types, field names and boundary conditions are the usual divergences. Divergence found → WARNING (or CRITICAL when the requirement's core promise is broken), with the file:line reference.
- **Scenario coverage.** Each `#### Scenario:` is a test case in prose. For each one, check both that the code handles the WHEN condition and that a test exercises it. Run the relevant tests with `execute` — do not infer from reading that they pass. A scenario with no test is a WARNING; a scenario the code does not handle at all is CRITICAL.

### Coherence — does it hold together?

- **Design decisions.** For each decision in `design.md`, check the implementation actually followed it. If the code took a different path, that is a WARNING with two acceptable resolutions (see step 3) — never leave the two contradicting each other.
- **Open Questions.** If `design.md` has unresolved Open Questions, confirm the implementation did not quietly answer one. If it did, that is CRITICAL: the human answered a different question at the spec gate than the one the code decided.
- **Project patterns.** Compare the new code against how the target repository already handles the same class of problem (layer boundaries, error handling, naming, test layout — see the `context:` block in `openspec/config.yaml`). Glaring deviation → SUGGESTION. Do not nitpick style the repo does not enforce.

## 3. Resolve every divergence — do not just report it

A divergence has exactly two honest resolutions:

1. **Fix the code** so it matches the spec. This is the default when the spec still reflects what the human approved.
2. **Update the spec** to match the code — only when the implementation revealed the spec was wrong, and only with the rationale written into `design.md` (a new Decision, or an amendment to an existing one). Silently editing a requirement to match whatever got built defeats the gate the human already passed.

If the divergence is a product decision (the spec and the code both defensible, nothing in the repo says which is right), resolve neither: write it into `design.md` Open Questions and name it in the gate comment.

After any fix, **re-run this verification from step 1** on the changed state. Verification against a stale reading is not verification. Call `log_review_cycle("code", <n>, <outcome>)` after each pass so the drift is visible in the console log.

## 4. Report

Emit the report as part of your run output, then carry its summary into the Jira gate comment:

```markdown
## Verification Report: <change-name>

| Dimension    | Result                                   |
|--------------|------------------------------------------|
| Completeness | X/Y tasks done, N/M requirements covered |
| Correctness  | N/M requirements verified, S scenarios tested |
| Coherence    | Design followed / K divergences          |

### CRITICAL
- <finding> — `file.py:123` — <specific recommendation>

### WARNING
- ...

### SUGGESTION
- ...
```

Every finding names a file and line where one applies, and a specific action. "Consider reviewing the service layer" is not a finding.

**Graceful degradation.** Only `tasks.md` present → verify task completion, and report the missing spec as a finding. Tasks + specs, no design → verify completeness and correctness, note that coherence was partially skipped. Always state which checks were skipped and why.

## 5. Gate

- **No CRITICAL findings** → verification passed. Call `log_openspec_event("verification_passed", detail=<change-name>, issue_key=<KEY>)` and proceed to the reviewer graph / the `Em Code Review` gate.
- **Any CRITICAL finding** → the gate is blocked. Fix, then re-verify. If you exhaust your self-review guidance with a CRITICAL still standing, park at `Em Code Review` anyway (that is the exhaustion path) — but the gate comment MUST enumerate each unresolved CRITICAL. Parking silently on a known divergence is the one failure this whole skill exists to prevent.

Include the scorecard and the unresolved findings in the `jira_park_at_gate` comment body, so the human reviewing the code starts from what the automation already knows.

---

## Guardrails

- Never mark a task `- [x]` for work that is not on the branch.
- Never edit a requirement to match the code without recording why in `design.md`.
- Never claim a scenario is covered because the code "looks right" — run the test.
- Never park at `Em Code Review` with an unresolved CRITICAL that the comment does not name.
- Verify the state that is committed. Uncommitted work in the sandbox does not survive a parked gate.
