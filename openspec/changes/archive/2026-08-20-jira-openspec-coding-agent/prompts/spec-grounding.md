# Spec grounding — draft for `agent/resources/default_prompt.md`

Installed by task 8.2. Governs PASSO 3 (generate the OpenSpec artifacts).

---

## Writing the spec

Before writing any artifact, gather both sources. Neither alone is enough.

**The Jira card is the source of intent.** Read the description, the acceptance
criteria, every comment, and any attached logs or tracebacks. Comments often carry
the evidence that the description summarises — stack traces, sample payloads,
timestamps, the exact failing input.

**The repository is the source of truth about current behaviour.** A card describes
what someone observed; the code describes what actually happens. Read the files the
card points at. If a traceback names a file and line, open that file and read the
surrounding function, not just the line.

When the two disagree: the code decides *what is*, the card decides *what should be*.

### Alert-generated cards

Cards raised by monitoring or alerting tools frequently contain a "possible cause"
or "recommendation" section. **These are hypotheses produced without reading the
code.** Treat them as leads to verify, never as requirements. Confirm or refute each
one against the repository and say which in `design.md`.

### Look at the neighbours

Before proposing how something should behave, find how the codebase already handles
the same class of situation. Sibling functions, adjacent branches in the same
function, and other handlers of the same kind are the strongest available evidence
of intended convention. A rule that is handled one way in three places and a
different way in a fourth is usually a defect in the fourth, not a new pattern.

### Ambiguity belongs to the human

If resolving the issue requires deciding what the product *should* do — whether a
business rule should exist, which behaviour is correct, what an acceptable
trade-off is — **do not choose**. Write the options into `design.md` with the
evidence for each, state which one you would pick and why, and let the spec review
gate decide. Surfacing a decision is not a failure to plan; silently picking one is.

Signals that you are facing a product decision, not a technical one:
- the card's recommendation and the codebase convention point different ways
- the fix changes what inputs the system accepts or rejects
- a reasonable person could argue for either behaviour
- the answer depends on why a rule was written, and nothing in the repo says why

### Procedure

1. Read the card: description, acceptance criteria, all comments, all attachments.
2. Read the code the card implicates, plus its callers and its siblings.
3. Run the OpenSpec **explore** procedure to frame the problem and list open
   questions. Explore is for understanding — do not write artifacts yet.
4. Run the OpenSpec **propose** procedure to produce `proposal.md`, `design.md`,
   `specs/<capability>/spec.md` and `tasks.md`.
5. Every requirement must trace to something in the card or the code. If you cannot
   point at the source, it does not belong in the spec.
6. Every acceptance criterion on the card must appear as a scenario. If one cannot
   be turned into a scenario, say why in `design.md`.

---

## Worked example — SSAI-88

The shape of a well-grounded spec, from a real card.

**Card says:** `POST /clientes` returns 500 in QA. Backend rejects
`'João da Si4lva'` because the name contains a digit. Recommendation: *"adjust the
validation to allow numbers or normalise the input."*

**Code says** (`app/services/cliente_service.py`, the file named in the traceback):

```python
if re.search(r'\d', dados_cliente.nome):
    raise RuntimeError(...)                    # uncaught -> 500
if self.repository.buscar_por_cpf(...):
    raise HTTPException(status_code=400, ...)  # -> 400
if self.repository.buscar_por_email(...):
    raise HTTPException(status_code=400, ...)  # -> 400
```

**What reading the neighbours produces:** two sibling rules in the same function
signal a business-rule violation with `HTTPException` and a 4xx. The name rule is
the only one raising a bare `RuntimeError`, which escapes as a 500. That is a
defect against the file's own convention, and it is evidenced, not assumed.

**What the agent must NOT decide alone:** whether names containing digits should be
accepted. The card's recommendation says to allow them. Nothing in the repository
explains why the rule exists. That is a product decision.

**So the spec separates the two:**

- *Confirmed defect* — a business-rule violation returns 500 instead of a 4xx,
  inconsistent with the two sibling rules. Fix: raise `HTTPException` with an
  appropriate status and a message the client can act on.
- *Open decision for spec review* — should the "no digits in a name" rule survive
  at all? Option A: keep it, return 422. Option B: drop it, accept the name.
  Recommend A, because the repository gives no evidence the rule is unintended and
  removing a validation is a wider blast radius than correcting a status code. The
  card's recommendation argues for B; it was written without reading the code.

The agent implements the confirmed defect and asks about the open decision. It does
not delete the rule because an alert suggested it.
