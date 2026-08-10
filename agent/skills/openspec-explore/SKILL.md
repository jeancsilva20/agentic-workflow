---
name: openspec-explore
description: Enter explore mode - a thinking partner for exploring ideas, investigating problems, and clarifying requirements. Use before running openspec-propose on a Jira card, or when resuming a parked thread that needs to reconsider its approach. This is a reasoning procedure the model follows, not a file-writing tool — see design.md Decision 3.
metadata:
  author: openspec
  version: "1.0"
  ported_from: ".claude/skills/openspec-explore/SKILL.md"
  ported_because: >
    The shipped skill declares `compatibility: Requires openspec CLI`, and the
    sandbox this agent runs in has no `openspec` binary (Decision 4). This
    version drops every CLI call and reads/writes OpenSpec artifacts directly
    with the existing `read_file` / `write_file` / `ls` tools instead.
---

Enter explore mode. Think deeply. Follow the conversation wherever it goes.

**IMPORTANT: Explore mode is for thinking, not implementing.** You may read files, search code, and investigate the codebase, but you must NEVER write application code in this mode. You MAY create OpenSpec artifacts (proposals, designs, specs) once the shape of the problem is clear — that's capturing thinking, not implementing. Application code belongs to the **openspec-propose** skill's tasks.md and the implementation step (PASSO 5) that follows spec approval, not to this one.

**This is a stance, not a workflow.** There are no fixed steps, no required sequence, no mandatory outputs.

---

## The Stance

- **Curious, not prescriptive** — ask questions that emerge naturally
- **Grounded** — read the Jira card and the implicated code before forming an opinion; see the grounding rules below
- **Patient** — let the shape of the problem emerge rather than jumping to the first plausible fix
- **Honest about what's still open** — a question surfaced now is answered once, at the spec-review gate, by a human; a question silently resolved now may be answered wrong twice

---

## Grounding rules (mandatory, not optional)

These come from `prompts/spec-grounding.md` in this change and apply to every exploration:

1. **The Jira card is the source of intent.** Read the description, every acceptance criterion, every comment, and any attached logs or tracebacks — comments often carry the evidence the description only summarises.
2. **The repository is the source of truth about current behaviour.** A card describes what someone observed; the code describes what actually happens. If a traceback names a file and line, open that file and read the surrounding function, not just the line.
3. **When the two disagree, the code decides what *is*; the card decides what *should be*.**
4. **Alert-generated cards carry hypotheses, not requirements.** A "possible cause" or "recommendation" section on a monitoring-filed card was written without reading the code. Confirm or refute it against the repository and say which.
5. **Look at the neighbours.** Before proposing how something should behave, find how the codebase already handles the same class of situation. A rule handled one way in three places and differently in a fourth is usually a defect in the fourth, not a new pattern.
6. **Ambiguity belongs to the human.** If resolving the issue requires deciding what the product *should* do, do not choose. Surface the options with evidence for each in `design.md`, state a recommendation, and let the spec-review gate (APPROVAL 1) decide. There is no synchronous user to ask in this mode — this agent runs unattended between Jira column moves, so "ask the user" always means "write the question into design.md as an open decision," never an interactive prompt.

Signals you're facing a product decision, not a technical one: the card's recommendation and the codebase convention point different ways; the fix changes what inputs the system accepts or rejects; a reasonable person could argue for either behaviour; the answer depends on why a rule was written and nothing in the repo says why.

---

## What You Might Do

**Investigate the codebase**
- Read the file(s) the card's traceback or description names, plus their callers and siblings
- Identify the existing convention for this class of problem
- Surface hidden complexity before it becomes a mid-implementation surprise

**Compare options**
- When more than one fix is defensible, lay out the trade-offs plainly (a short table beats a paragraph)
- Recommend a path, but do not treat the recommendation as decided — that's what APPROVAL 1 is for

**Surface risks and unknowns**
- Confirmed defect vs. open product decision (see the worked example below) is the split that matters most
- Note anything a card assumes that the code contradicts

---

## Checking for existing context

There is no `openspec` CLI in this sandbox. Instead, read the change state directly:

1. List `openspec/changes/` in the target repository (`ls` or `glob`) to see if a change directory already exists for this Jira issue.
2. If one exists, read its artifacts directly — `proposal.md`, `design.md`, `specs/*/spec.md`, `tasks.md` — in that order, to pick up where a prior run (or a human) left off.
3. If none exists, this is a fresh exploration; the openspec-propose skill will create the directory.

## Worked example — SSAI-88

**Card says:** `POST /clientes` returns 500 in QA. Backend rejects `'João da Si4lva'` because the name contains a digit. Recommendation: *"adjust the validation to allow numbers or normalise the input."*

**Code says** (`app/services/cliente_service.py`, the file the traceback names):

```python
if re.search(r'\d', dados_cliente.nome):
    raise RuntimeError(...)                    # uncaught -> 500
if self.repository.buscar_por_cpf(...):
    raise HTTPException(status_code=400, ...)  # -> 400
if self.repository.buscar_por_email(...):
    raise HTTPException(status_code=400, ...)  # -> 400
```

**Reading the neighbours:** two sibling rules in the same function signal a business-rule violation with `HTTPException` and a 4xx. The name rule is the only one raising a bare `RuntimeError`, which escapes as a 500 — a defect against the file's own convention, and it is evidenced, not assumed.

**What must NOT be decided alone:** whether names containing digits should be accepted at all. The card's recommendation says yes; nothing in the repository explains why the rule exists. That is a product decision, not a technical one.

**The split:**
- *Confirmed defect* (implement it): the error type is wrong, not the rule. Raise `HTTPException` with an appropriate status.
- *Open decision for spec review* (surface it, don't resolve it): should the "no digits in a name" rule survive at all? Recommend keeping it (removing a validation is a wider blast radius than correcting a status code) but let the gate decide.

---

## Ending Exploration

There's no required ending. Exploration might:
- Flow straight into **openspec-propose** once the shape is clear
- Surface one or more open decisions to carry into `design.md` rather than resolve them here
- Conclude nothing needs building — say so in a Jira comment and stop

## Guardrails

- **Don't implement application code** — reading and understanding only, until propose has run and a spec exists
- **Don't fake understanding** — if something is unclear, read more code before writing anything down
- **Don't resolve product decisions** — write them as options for the gate, per the grounding rules above
- **Don't skip the card's comments** — the evidence is usually there, not in the description
