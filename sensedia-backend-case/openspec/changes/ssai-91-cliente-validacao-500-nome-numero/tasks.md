# Tasks: Client Name Validation Error Handling (SSAI-91)

## 1. Fix the Exception Type in Service

- [ ] 1.1 Update `app/services/cliente_service.py` to raise `HTTPException(status_code=400, detail="...")` instead of `RuntimeError` for name validation
- [ ] 1.2 Verify the error message is preserved in the exception detail
- [ ] 1.3 Verify import of `HTTPException` and `status` is present

## 2. Add Unit Tests

- [ ] 2.1 Create `tests/` directory and `conftest.py` with fixtures for database session and test client
- [ ] 2.2 Create `tests/test_cliente_service.py` with tests for `ClienteService.criar_cliente()`
- [ ] 2.3 Add test: name with digit returns HTTP 400 (not 500)
- [ ] 2.4 Add test: valid name returns HTTP 201
- [ ] 2.5 Add test: duplicate CPF returns HTTP 400 (regression check)
- [ ] 2.6 Add test: duplicate email returns HTTP 400 (regression check)

## 3. Verify Integration

- [ ] 3.1 Run the test suite to confirm all tests pass
- [ ] 3.2 Verify no syntax errors or import issues in the updated service
- [ ] 3.3 Verify the router still works correctly with the updated service

## 4. Commit and Prepare for Review

- [ ] 4.1 Commit changes with message describing the fix
- [ ] 4.2 Push to the feature branch
- [ ] 4.3 Ensure branch is pushed to origin

## 5. Code Quality

- [ ] 5.1 Run formatter/linter once established in the baseline
- [ ] 5.2 Confirm no code quality issues introduced
