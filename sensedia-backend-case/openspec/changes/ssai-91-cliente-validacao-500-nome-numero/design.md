# Design: Client Name Validation Error Handling (SSAI-91)

## Context

**Current State:**
The POST /clientes endpoint fails with HTTP 500 when a client name contains digits. The backend service raises an unhandled `RuntimeError` in `ClienteService.criar_cliente()` (line 12–16 of `app/services/cliente_service.py`):

```python
if re.search(r'\d', dados_cliente.nome):
    raise RuntimeError(
        f"Não é possível cadastrar o cliente '{dados_cliente.nome}': "
        f"nome contém número, indicando cadastro potencialmente inconsistente."
    )
```

This exception is not caught by FastAPI's exception handlers, so it propagates as a 500 response.

**What Should Happen:**
All validation errors in this function should return HTTP 400 (Bad Request) with structured error detail. The two sibling checks (duplicate CPF, duplicate email) already do this correctly.

**Confirmed Defect:**
The name validation uses the wrong exception type. This is a **technical defect** against the file's own convention, evidenced by the neighboring code.

## Goals

- **Primary:** Fix the exception type in name validation to return HTTP 400 instead of 500
- **Secondary:** Ensure the error response is consistent with other business-rule validation failures
- **Verification:** Add unit tests to prevent regression

## Non-Goals

- Deciding whether the "no digits in names" rule should exist at all (that is a product decision, see DECISION 1 below)
- Refactoring the entire validation layer
- Changing CPF or email validation behavior

## Decisions

**DECISION 1: Exception Type**
- **Chosen:** Raise `HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="...")` instead of `RuntimeError`
- **Rationale:** Consistency with sibling validations in the same function; FastAPI catches HTTPException and converts it to a proper JSON response
- **Evidence:** Code inspection of `ClienteService.criar_cliente()` shows two other validations already follow this pattern
- **Alternative considered:** Catch RuntimeError in a middleware — rejected because it would hide the pattern violation and make the layer boundary unclear

## Risks & Trade-offs

| Risk | Mitigation |
|------|-----------|
| Changing exception type might affect callers outside this function | Code inspection shows `criar_cliente` is only called from the router, which does not catch RuntimeError; no external callers. Safe to change. |
| The error message text is informative; must not be lost | Error message will be preserved in the `detail` field of the HTTPException |
| Removing the validation rule entirely (alternative fix) would need product approval | The rule is kept as-is; only the exception type changes. Removal is a separate decision. |

## Open Questions

**DECISION 1: Should the "no digits in names" rule be removed or retained?**

The alert that triggered SSAI-91 recommended: *"adjust the validation to allow numbers or normalize the input."* This suggests removing or weakening the rule.

**Options:**

1. **Keep the rule, fix the exception type (current proposal)**
   - *Evidence:* The rule exists in the code; no evidence explains why
   - *Pro:* Minimal change, only fixes the HTTP status code
   - *Con:* Does not address the original alert's recommendation

2. **Remove the rule entirely**
   - *Evidence:* The alert recommended allowing numbers; the field is a free-text `nome` with no documented constraint
   - *Pro:* Fixes the root cause (rejects legitimate input)
   - *Con:* Wider blast radius; must verify no other code depends on this constraint

3. **Weaken the rule (warn, don't reject)**
   - *Evidence:* Error message suggests "potentially inconsistent" — this could be logged but not rejected
   - *Pro:* Preserves intent (flag suspicious names) without blocking the request
   - *Con:* Changes business logic, not just error handling

**Recommendation:** Start with option 1 (keep the rule, fix the exception type). If the product decision is to remove or weaken the rule, that is a second, separate change. The current defect (500 instead of 400) is confirmed and can be fixed independently.

**Resolution:** Gate at APPROVAL 1 (spec review) — the review comment will clarify whether the rule should be kept, removed, or weakened.

## Implementation Notes

- **File to change:** `app/services/cliente_service.py`
- **Lines affected:** 12–16
- **Tests needed:** 
  1. POST /clientes with a name containing a digit → HTTP 400, not 500
  2. POST /clientes with valid name → HTTP 201 (existing behavior preserved)
  3. POST /clientes with duplicate CPF → HTTP 400 (existing behavior preserved)
  4. POST /clientes with duplicate email → HTTP 400 (existing behavior preserved)
- **Framework context:** FastAPI exception handling, Pydantic v2 validation, SQLAlchemy session

## Additional Context

- **Related issue:** SSAI-90 (cloned from this alert, reached "Em Revisão de Spec")
- **Architecture:** The service layer handles business-rule validation; the router delegates to the service via dependency injection
- **ORM:** SQLAlchemy 2.0 + Alembic (no schema changes needed)
- **No existing test suite:** Tests will be added as part of this change (see tasks.md)
