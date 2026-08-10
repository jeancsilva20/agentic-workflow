# Specification: Client Name Validation Error Handling

## MODIFIED Requirements

### Requirement: Client Creation Validates Name Format
The system SHALL validate client names during creation and reject invalid formats with an HTTP 400 (Bad Request) response and structured error detail, not an HTTP 500 error.

#### Scenario: Name with digit returns 400, not 500
- **WHEN** a POST /clientes request includes a name containing a digit (e.g., "João da Si4lva")
- **THEN** the system returns HTTP 400 Bad Request
- **AND** the response includes a JSON error detail with `detail` field describing the validation failure
- **AND** the response is NOT an HTTP 500 Internal Server Error

#### Scenario: Valid name succeeds
- **WHEN** a POST /clientes request includes a name without digits (e.g., "João da Silva")
- **AND** the email is valid (not duplicate)
- **AND** the CPF is valid (not duplicate)
- **THEN** the system returns HTTP 201 Created
- **AND** the client is successfully persisted

#### Scenario: Other validation errors return 400
- **WHEN** a POST /clientes request includes a valid name but a duplicate CPF
- **THEN** the system returns HTTP 400 Bad Request
- **AND** the response includes error detail about the duplicate CPF
- **WHEN** a POST /clientes request includes a valid name but a duplicate email
- **THEN** the system returns HTTP 400 Bad Request
- **AND** the response includes error detail about the duplicate email

### Requirement: Error Response Consistency
The system SHALL use `HTTPException` with appropriate status codes (4xx, 5xx) for all business-rule validations, not bare exceptions that escape the framework.

#### Scenario: All validation errors use HTTPException
- **WHEN** POST /clientes triggers any validation failure (name format, duplicate CPF, duplicate email)
- **THEN** the response is structured (JSON with `detail` field)
- **AND** the status code is in the 4xx range for client errors

## Decision Point (See design.md)

**DECISION 1: Should the "no digits in names" rule be removed or retained?**

The alert that triggered this card recommended removing the rule to allow digits in names. The code provides no explanation for why the rule exists. This is a product decision, not a technical one, and will be resolved during spec review (APPROVAL 1).

If the rule is **retained**: the current fix (raising HTTPException 400) is sufficient.
If the rule is **removed**: additional code changes are needed to delete the validation check entirely.
