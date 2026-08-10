# ssai-88-fix-post-clientes-500

## Why

An FA alert (SSAI-88) fired for `POST /clientes` in QA: more than 5 calls returned `500 Internal Server Error`. The traceback shows `ClienteService.criar_cliente` (`app/services/cliente_service.py:12-16`) raising a bare `RuntimeError` when the client's `nome` contains a digit — an uncaught exception that falls through to the generic `Exception` handler in `app/main.py`, which always returns 500. Every other business-rule violation in the same function (duplicate CPF, duplicate e-mail) raises `HTTPException` with an explicit 4xx status. The name-digit check is the only one that doesn't follow that convention, and it is what turns an expected validation failure into an internal-server-error alert.

## What Changes

- Change the name-validation branch in `ClienteService.criar_cliente` to raise `HTTPException(status_code=400, detail=...)` instead of a bare `RuntimeError`, matching the convention already used by the CPF and e-mail checks in the same method.
- Keep the underlying business rule (names containing digits are rejected) unchanged — whether that rule itself should exist is a separate, open product decision recorded in `design.md`, not resolved by this change.

## Capabilities

### New Capabilities
- `gestao-clientes` — this is the first OpenSpec change to formalize requirements for the `POST /clientes` client-registration flow; no prior spec exists under `openspec/specs/`.

### Modified Capabilities
- (none — `openspec/specs/` has no existing capabilities to modify)

## Impact

- **Code:** `app/services/cliente_service.py` (`criar_cliente` method only).
- **API:** `POST /api/v1/clientes` — response status for a name containing digits changes from `500` to `400`; response body changes from the generic `{"detail": "Erro interno do servidor"}` to a specific `{"detail": "..."}` message describing the validation failure.
- **Logging:** the error is now logged at `WARNING` (4xx path in `http_exception_handler`) instead of `ERROR` (5xx path in `generic_exception_handler`) — consistent with how the CPF/e-mail duplicate checks are already logged.
- **Dependencies:** none added.
- **Tests:** no test suite exists in the repository yet; this change adds the repo's first unit tests, scoped to `ClienteService.criar_cliente`, using `pytest` with a mocked DB session (no live database required).
