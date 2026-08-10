# cadastro-clientes

## MODIFIED Requirements

### Requirement: Validação de nome do cliente ao cadastrar
O sistema SHALL rejeitar a criação de um cliente cujo nome contenha um ou mais números, retornando um erro de requisição inválida do cliente (HTTP 400) com uma mensagem explicando o motivo — nunca um erro de servidor (HTTP 500).

#### Scenario: Nome contém número
- **WHEN** uma requisição `POST /clientes` é enviada com `nome` contendo ao menos um dígito (ex.: `"João da Si4lva"`)
- **THEN** a API responde com status HTTP 400
- **AND** o corpo da resposta contém uma mensagem indicando que o nome contém número e o cadastro não pôde ser realizado
- **AND** nenhum cliente é persistido no banco de dados

#### Scenario: Nome sem número é aceito
- **WHEN** uma requisição `POST /clientes` é enviada com `nome` sem nenhum dígito, CPF e e-mail ainda não cadastrados
- **THEN** a API responde com status HTTP 201
- **AND** o cliente é persistido e retornado no corpo da resposta

### Requirement: Validação de CPF duplicado ao cadastrar (sem alteração de comportamento)
O sistema SHALL rejeitar a criação de um cliente cujo CPF já esteja cadastrado, retornando HTTP 400. Este requisito já era satisfeito antes desta mudança; é reafirmado aqui apenas para documentar o padrão de erro que a correção do nome passa a seguir.

#### Scenario: CPF já cadastrado
- **WHEN** uma requisição `POST /clientes` é enviada com um `cpf` que já existe em outro cliente cadastrado
- **THEN** a API responde com status HTTP 400
- **AND** nenhum novo cliente é persistido

### Requirement: Validação de e-mail duplicado ao cadastrar (sem alteração de comportamento)
O sistema SHALL rejeitar a criação de um cliente cujo e-mail já esteja cadastrado, retornando HTTP 400. Este requisito já era satisfeito antes desta mudança; é reafirmado aqui apenas para documentar o padrão de erro que a correção do nome passa a seguir.

#### Scenario: E-mail já cadastrado
- **WHEN** uma requisição `POST /clientes` é enviada com um `email` que já existe em outro cliente cadastrado
- **THEN** a API responde com status HTTP 400
- **AND** nenhum novo cliente é persistido
