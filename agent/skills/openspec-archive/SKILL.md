---
name: openspec-archive
description: Archive a completed change — move its artifacts out of the active change directory, fold new capabilities into the canonical specs, record the change in the archive index, and commit and push it on the same branch. Run this during pre-merge preparation, after the human moved the card to `Code Review Aprovado` and before parking at `Em Merge`.
metadata:
  author: openspec
  version: "1.0"
  ported_from: "Fission-AI/OpenSpec skills/openspec-archive-change/SKILL.md"
  upstream_pin: "see openspec/openspec-version.yaml (source, version, commit)"
  ported_because: >
    The upstream skill declares `compatibility: Requires openspec CLI` and drives
    `openspec status`, `openspec instructions archive`, `openspec list` and
    `openspec archive`, plus an interactive prompt when the change is ambiguous.
    Neither the CLI nor a synchronous user exists here (design.md Decision 4):
    the Jira issue key names the change, and the mechanical move+merge is done by
    the `openspec_archive` tool. This port keeps the upstream ordering — verify
    completion, sync specs, move, summarise — and adds the two things this
    workflow needs and upstream has no concept of: the archive index entry and
    the commit/push that must land before the `Em Merge` gate.
---

Archive the change and get it onto the branch, before the card reaches `Em Merge`.

**Why it happens now and not after the merge.** `Em Merge` means "the automation has finished everything it needs to do and this PR is ready for a human to merge" (design.md Decision 6, revised). An archive that lands after the merge would be work outstanding at the moment a human is asked to accept the delivery, in a second PR nobody is watching. The archive ships in the same branch and the same PR as the implementation.

---

## 1. Confirm you are allowed to archive

All of these must hold. If any does not, stop and comment on the Jira card instead:

- The human code-review gate is passed — the card is in `Code Review Aprovado` (or the PR is approved/merged). Never archive from `Em Code Review`; the human has not decided yet.
- `openspec-verify` ran on the current state and left no unresolved CRITICAL finding.
- The working tree has no uncommitted implementation work. The archive commit must contain the archive, not a mix of archive and code.

## 2. Confirm the change is actually complete

Read `openspec/changes/<change>/tasks.md` and count the checkboxes, or call `openspec_status`.

Incomplete tasks do **not** block the archive — but they do have to be visible. If any box is still unchecked at this point, one of two things is true and you must say which in the summary and in the Jira comment: the task was deferred (say why), or it was done and never ticked (tick it now, in a commit, before archiving).

## 3. Move the artifacts and fold in the new capabilities

Call the `openspec_archive` tool with the change name. It does the mechanical work:

- moves every file under `openspec/changes/<change>/` to `openspec/changes/archive/<change>/`;
- for each `specs/<capability>/spec.md`, writes the `## ADDED Requirements` block into the canonical `openspec/specs/<capability>/spec.md` when that capability does not exist yet.

Read its return value; it is not a formality:

- `merged_capabilities` — capabilities now living in the canonical spec tree.
- `needs_manual_merge` — capabilities that **already existed** canonically. The tool deliberately does not apply MODIFIED / REMOVED / RENAMED deltas: getting that merge wrong silently corrupts the canonical spec. For each one, apply the delta by hand with `read_file` + `edit_file`, using the delta spec as the source of the change, and re-read the result. Leaving this list unhandled means the canonical spec no longer describes the system.
- `error` — nothing was archived. Do not continue, do not move the card; comment the error on the Jira card.

Then confirm `openspec/changes/<change>/` is gone and the archive directory holds the files.

> Divergence from upstream, on purpose: upstream prefixes the archived directory with `YYYY-MM-DD-`. The tool here keeps the change name as-is, and the date lives in the index entry from step 4 instead — one date, in one place, that a reader can sort by.

## 4. Record the change in the archive index

Append one row to `openspec/changes/archive/index.md` (create the file with this header if it does not exist yet):

```markdown
# OpenSpec Archive

| Date | Change | Jira | Summary |
|------|--------|------|---------|
| 2026-08-10 | ssai-88-fix-name-validation-status | SSAI-88 | Name-with-digit rejection now raises HTTPException 400 instead of escaping as a 500. |
```

Append, never rewrite: the index is the history of what this agent has shipped. One line, the actual date (`date -u +%Y-%m-%d` via `execute` — do not guess it), the Jira key, and a summary a person can read six months from now without opening the change.

## 5. Commit and push on the same branch

```bash
git add openspec/
git commit -m "chore(openspec): archive <change> for <ISSUE-KEY>"
git push origin <branch>
```

Same branch, same PR — never a new branch and never a second PR for the archive. Confirm the push actually landed (`git ls-remote --heads origin <branch>`, or check the PR picked up the commit) before treating this step as done.

If the commit or the push fails, the archive did not ship. Comment the failure on the Jira card, leave the card where it is, and end your turn.

## 6. Log the lifecycle event

Call `log_openspec_event("archived", detail=<change-name>, issue_key=<KEY>)` once the push has
landed, so the console's execution log records that this run reached the archive checkpoint.

## 7. Summarise, then hand off

Report:

```markdown
## Archive Complete

**Change:** <change-name>
**Jira:** <ISSUE-KEY>
**Archived to:** openspec/changes/archive/<change-name>/
**Capabilities merged:** <list, or "none — all deltas were modifications">
**Manually merged:** <list from needs_manual_merge, or "none">
**Tasks:** <X/Y complete — name anything deferred>
```

The archive is one part of pre-merge preparation, not the end of it. Documentation updates, the final checks, and the self-review of the pre-merge diff still have to happen (see the Pre-Merge Preparation section of the system prompt). Only when all of that is done and pushed do you call `jira_park_at_gate` for `Em Merge`, with the archive summary included in the comment so the person merging sees what was added after their approval.

---

## Guardrails

- Never archive before the human code-review gate is passed.
- Never leave `needs_manual_merge` unhandled — a capability that silently keeps its old canonical spec is a lie the next change will build on.
- Never archive a change whose `openspec/changes/<change>/` still holds work in progress that the branch does not contain.
- Never rewrite `index.md`; append.
- Never move the card to `Em Merge` if the archive, the docs, the checks, or the push failed. A stuck card with an explanation is recoverable; a card that advanced on a lie is not.
