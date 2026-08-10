# Proposal: SSAI-91 — Fix Client Name Validation Error Handling

## Why

The POST /clientes endpoint returns HTTP 500 (Internal Server Error) when a request contains a client name with digits (e.g., "João da Si4lva"). The backend validation logic raises an unhandled `RuntimeError` that escapes the application, violating HTTP semantics and the API's own error-handling convention. All other business-rule validations in the same function properly return HTTP 400 with structured error details.

## What Changes

- **Modified:** Client name validation in `ClienteService.criar_cliente()` now raises `HTTPException` with status 400 instead of `RuntimeError`, making the error response consistent with other validation failures (duplicate CPF, duplicate email).
- **Impact:** API consumers receive a proper 400 Bad Request response with a JSON error detail instead of a 500 Internal Server Error, enabling proper client-side handling and improving observability.

## Capabilities

### New Capabilities
(None — this is a fix to existing behavior, not a new feature.)

### Modified Capabilities
- `cliente-validacao` — corrected exception type and HTTP status code for name validation

## Impact

**Code affected:**
- `app/services/cliente_service.py` — `ClienteService.criar_cliente()` method, lines 12–16

**APIs affected:**
- `POST /clientes` — error response type changes from 500 to 400 with JSON detail

**Dependencies:**
- No new dependencies required; uses existing `fastapi.HTTPException`

**Test impact:**
- No existing test suite; the change will include new unit tests for this scenario
- Tests will verify: (1) valid names accept digits, OR (2) invalid names return 400 with proper detail, depending on the product decision resolved in design.md
