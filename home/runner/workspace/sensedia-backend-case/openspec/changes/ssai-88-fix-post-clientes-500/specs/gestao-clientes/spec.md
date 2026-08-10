## ADDED Requirements

### Requirement: Client name containing a digit MUST be rejected with a client error, not a server error
When `POST /clientes` is called with a `nome` that contains at least one digit, the system SHALL reject the request with an `HTTPException` carrying a `4xx` status code (not an uncaught exception that resolves to `500`), and SHALL NOT persist the client record.

#### Scenario: Name with a digit returns 400, not 500
- **WHEN** a client POSTs to `/api/v1/clientes` with `nome` = "João da Si4lva" (containing a digit) and otherwise-valid `email`/`cpf`
- **THEN** the response status is `400 Bad Request`
- **AND** the response body's `detail` field describes that the name contains a number
- **AND** no `Cliente` row is created
- **AND** the error is logged at `WARNING` level (via the existing `HTTPException` handler), not `ERROR`

### Requirement: Duplicate CPF and duplicate e-mail validations remain unchanged
The system SHALL continue to reject a `POST /clientes` request with `400 Bad Request` when the `cpf` or `email` already belongs to an existing client, exactly as before this change.

#### Scenario: Duplicate CPF still returns 400
- **WHEN** a client POSTs to `/api/v1/clientes` with a `cpf` that already exists for another client, and a `nome` containing no digits
- **THEN** the response status is `400 Bad Request` with detail `"Já existe um cliente cadastrado com este CPF."`

#### Scenario: Duplicate e-mail still returns 400
- **WHEN** a client POSTs to `/api/v1/clientes` with an `email` that already exists for another client, and a `nome` containing no digits and a `cpf` not already in use
- **THEN** the response status is `400 Bad Request` with detail `"Já existe um cliente cadastrado com este E-mail."`

### Requirement: A valid client registration still succeeds
The system SHALL create a new `Cliente` record and return `201 Created` when `nome` contains no digits, and `cpf`/`email` are not already registered.

#### Scenario: Successful registration
- **WHEN** a client POSTs to `/api/v1/clientes` with a `nome` containing no digits, and a `cpf`/`email` not already in use
- **THEN** the response status is `201 Created`
- **AND** the response body contains the created client's `id`, `nome`, `email`, and `cpf`
