## ADDED Requirements

### Requirement: Rejeição de nome de cliente contendo números retorna erro de cliente (4xx)
O sistema SHALL rejeitar a criação de um cliente cujo nome contenha algum caractere numérico, retornando um erro de requisição do cliente (HTTP 400) com uma mensagem explicativa no campo `detail`, e SHALL NOT retornar um erro interno do servidor (HTTP 500) para esse caso.

#### Scenario: Nome com número retorna 400, não 500
- **WHEN** uma requisição `POST /api/v1/clientes` é feita com um `nome` contendo pelo menos um dígito (ex.: `"João da Si4lva"`)
- **THEN** o sistema SHALL responder com status HTTP 400
- **AND** o corpo da resposta SHALL conter um campo `detail` explicando que o nome não pode conter números
- **AND** o sistema SHALL NOT responder com status HTTP 500

#### Scenario: Nome com número não persiste o cliente
- **WHEN** uma requisição `POST /api/v1/clientes` é feita com um `nome` contendo algum dígito
- **THEN** o sistema SHALL NOT chamar as verificações de CPF/e-mail duplicado nem persistir nenhum registro na tabela `clientes`

#### Scenario: Nome sem números segue o fluxo normal de criação
- **WHEN** uma requisição `POST /api/v1/clientes` é feita com um `nome` que não contém nenhum dígito, CPF e e-mail inéditos
- **THEN** o sistema SHALL prosseguir com as validações de CPF e e-mail duplicados e, se ambas passarem, SHALL criar o cliente normalmente com status HTTP 201

### Requirement: Verificação de CPF duplicado na criação de cliente
O sistema SHALL impedir a criação de um cliente cujo CPF já esteja cadastrado, retornando HTTP 400 com uma mensagem explicativa.

#### Scenario: CPF duplicado retorna 400
- **WHEN** uma requisição `POST /api/v1/clientes` é feita com um `cpf` que já pertence a outro cliente cadastrado, e o `nome` não contém números
- **THEN** o sistema SHALL responder com status HTTP 400 e `detail` indicando que já existe um cliente cadastrado com aquele CPF

### Requirement: Verificação de e-mail duplicado na criação de cliente
O sistema SHALL impedir a criação de um cliente cujo e-mail já esteja cadastrado, retornando HTTP 400 com uma mensagem explicativa.

#### Scenario: E-mail duplicado retorna 400
- **WHEN** uma requisição `POST /api/v1/clientes` é feita com um `email` que já pertence a outro cliente cadastrado, e o `nome` não contém números e o `cpf` é inédito
- **THEN** o sistema SHALL responder com status HTTP 400 e `detail` indicando que já existe um cliente cadastrado com aquele e-mail
