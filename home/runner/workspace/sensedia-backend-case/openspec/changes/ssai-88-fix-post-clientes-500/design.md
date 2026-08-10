## Context

`POST /api/v1/clientes` is handled by `cliente_router.criar_cliente` → `ClienteService.criar_cliente` → `ClienteRepository.criar` (Router → Service → Repository → Model, the consistent layering across this codebase). `app/main.py` registers two global exception handlers: `HTTPException` → logs at `WARNING`/`ERROR` (by status code) and returns the exception's own status/detail; bare `Exception` → logs at `ERROR` and always returns `500` with a generic body. `ClienteService.criar_cliente` currently has three validation branches:

```python
if re.search(r'\d', dados_cliente.nome):
    raise RuntimeError(...)                                          # -> falls to generic handler -> 500
if self.repository.buscar_por_cpf(dados_cliente.cpf):
    raise HTTPException(status_code=400, detail="Já existe um cliente cadastrado com este CPF.")
if self.repository.buscar_por_email(dados_cliente.email):
    raise HTTPException(status_code=400, detail="Já existe um cliente cadastrado com este E-mail.")
```

The FA alert's own "possible causes" section suggested the validation itself was wrong ("ajustar validação para permitir números"). Reading the code shows a narrower, evidenced problem: the *rule* is applied consistently with the other two checks in intent (reject invalid input), but the *error-handling mechanism* it uses is not — it's the only one of the three that doesn't raise `HTTPException`.

## Goals / Non-Goals

**Goals:**
- Make `POST /clientes` return a 4xx (not 500) when the name contains a digit, consistent with the file's own convention for business-rule validation failures.
- Add the repository's first unit tests, covering `ClienteService.criar_cliente`'s three validation branches plus the success path.

**Non-Goals:**
- Deciding whether names containing digits should be rejected at all (see Open Questions).
- Introducing a validation framework, request-schema-level validators, or normalizing/stripping digits from input — out of scope for a status-code fix.
- Adding a test framework/config beyond what this change's own tests need (see Risks).

## Decisions

### 1. Raise `HTTPException(status_code=400, ...)` instead of `RuntimeError`
**Decision:** Replace the `RuntimeError` with `HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=...)`, reusing the existing exception message text (translated to a client-facing detail).

**Rationale:** Matches the two sibling checks in the same method exactly — same exception type, same status code family, same place in the flow (before the mutating `self.repository.criar(...)` call). No new pattern is introduced.

**Alternatives considered:**
- *422 Unprocessable Entity* instead of 400 — more semantically precise for a validation failure, but the two existing sibling checks in this method both use 400, and matching the local convention outranks a marginally more correct status code that would make this one check inconsistent with its neighbors again, just differently.
- *Move the check into the Pydantic schema (`ClienteCreate`) as a `@validator`* — would give a 422 automatically and fail before reaching the service layer at all. Rejected for this change because it changes the response shape (Pydantic's built-in validation error format, not the app's own `{"detail": ...}` convention) and enlarges the blast radius beyond the confirmed defect; worth considering separately if the digit-rejection rule survives APPROVAL 1.

### 2. Test approach: unit test `ClienteService` with a mocked session, no live DB
**Decision:** Add `tests/test_cliente_service.py` using `pytest`, constructing `ClienteService(MagicMock())` and mocking `repository.buscar_por_cpf` / `buscar_por_email` directly, per the pattern verified during harness detection.

**Rationale:** The repository has no test suite and no live Postgres reachable from the sandbox; this is the only way to verify the fix without deploying a database. `ClienteService.criar_cliente`'s logic is fully exercisable this way since none of its three validation branches touch the DB before the exception is raised (the CPF/e-mail checks call `self.repository.*`, which is trivially mocked).

**Alternatives considered:**
- *Integration test against a real/test Postgres* — more realistic, but no DB is available in this sandbox or declared anywhere in CI; out of scope for this fix.
- *`pytest` as an added dependency* — the project's `requirements.txt` has no dev-dependencies split; `pytest` will be listed under a new `requirements-dev.txt` rather than mixed into the production `requirements.txt`, so the runtime image is unaffected.

## Risks / Trade-offs

- **[No test runner or CI gate exists yet]** → This change adds `pytest` as the first, minimal dev-dependency and a `tests/` directory; it does not attempt to build out a broader test/CI baseline (out of scope), but the pattern this change establishes (mock the repository, no live DB) is reusable for future coverage of `ApoliceService` and others.
- **[Changing the response body for this failure]** → Any QA/monitoring dashboard or client integration keyed on the exact string `"Erro interno do servidor"` for this specific input will see a different message and status code. This is the intended fix (a 500 alert should not have been firing for a client input error in the first place), not a regression.

## Open Questions

**Should a client name containing a digit be rejected at all?**

- The FA alert's own recommendation says the opposite: relax the validation to allow numbers, or normalize the input.
- Nothing in `app/services/cliente_service.py`, `app/models/models.py`, or the rest of the repository explains *why* the digit rule exists — there's no comment, no related requirement elsewhere, and no similar rule applied to other fields.
- Per the grounding rules, this is a product decision, not a technical one: a reasonable person could argue either way, and the answer depends on intent nobody has recorded.
- **Recommendation:** keep the rule as-is for this change. Correcting the status code (500 → 400) already resolves the alert (a 500 should never fire for a client-input validation failure); relaxing or removing the rule is a separate, larger decision with its own blast radius (e.g., names like "João da Si4lva" — likely a typo/OCR artifact rather than a legitimately numeric name — becoming acceptable going forward) that deserves its own card if the business decides the rule is wrong.
- This is left for APPROVAL 1 to confirm or override; if overridden, the spec's `ADDED Requirements` below should be revisited before implementation.
