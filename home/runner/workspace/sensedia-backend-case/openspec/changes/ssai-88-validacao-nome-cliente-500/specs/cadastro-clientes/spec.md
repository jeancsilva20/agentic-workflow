## ADDED Requirements

### Requirement: Erro de validação de negócio no cadastro de cliente retorna 4xx, não 500
Ao criar um cliente via `POST /clientes`, toda violação de regra de negócio detectada em `ClienteService.criar_cliente` SHALL ser sinalizada por meio de `HTTPException` com um status code 4xx apropriado, nunca por uma exceção não tratada que resulte em HTTP 500.

#### Scenario: Nome contendo número retorna 400
- **WHEN** uma requisição `POST /clientes` é feita com um `nome` que contém ao menos um dígito (ex.: `"João da Si4lva"`)
- **THEN** o sistema SHALL responder HTTP 400 com um `detail` explicando que o nome não pode conter números
- **AND** o sistema SHALL NOT responder HTTP 500 nem propagar uma exceção não tratada

#### Scenario: CPF duplicado continua retornando 400
- **WHEN** uma requisição `POST /clientes` é feita com um `cpf` já cadastrado para outro cliente
- **THEN** o sistema SHALL responder HTTP 400 com `detail` "Já existe um cliente cadastrado com este CPF."

#### Scenario: Email duplicado continua retornando 400
- **WHEN** uma requisição `POST /clientes` é feita com um `email` já cadastrado para outro cliente
- **THEN** o sistema SHALL responder HTTP 400 com `detail` "Já existe um cliente cadastrado com este E-mail."

#### Scenario: Cadastro válido continua retornando 201
- **WHEN** uma requisição `POST /clientes` é feita com `nome` sem números, `cpf` e `email` inéditos
- **THEN** o sistema SHALL criar o cliente e responder HTTP 201 com os dados do cliente criado
