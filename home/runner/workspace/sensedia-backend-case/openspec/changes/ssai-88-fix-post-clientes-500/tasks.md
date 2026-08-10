## 1. Fix the defect

- [ ] 1.1 In `app/services/cliente_service.py`, replace the bare `RuntimeError` in `criar_cliente`'s digit-check branch with `HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=...)`, reusing the existing message text as the `detail`.
- [ ] 1.2 Confirm `HTTPException` and `status` are already imported in that file (they are, for the sibling checks) — no new import needed.

## 2. Tests

- [ ] 2.1 Add `requirements-dev.txt` with `pytest` (pinned version) as the repo's first dev-dependency.
- [ ] 2.2 Create `tests/test_cliente_service.py` with a mocked `Session`/repository (no live DB) covering:
  - name with a digit → `HTTPException` with `status_code == 400`
  - duplicate CPF → `HTTPException` with `status_code == 400` (unchanged behavior)
  - duplicate e-mail → `HTTPException` with `status_code == 400` (unchanged behavior)
  - valid input → `repository.criar` is called and its return value is returned
- [ ] 2.3 Run `pytest -q` against the new test file and confirm all tests pass.

## 3. Verification

- [ ] 3.1 Manually trace the fix through `app/main.py`'s `http_exception_handler` to confirm a name with a digit now logs at `WARNING` and returns `{"detail": ...}` with status 400 (no live server run needed — read the handler code against the new exception type).
- [ ] 3.2 Run `openspec-verify` against this change once implemented, before requesting code review.
