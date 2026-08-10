## ADDED Requirements

### Requirement: Consistência do tipo de exceção nas regras de negócio de Clientes
O sistema SHALL levantar `HTTPException` com um status code 4xx apropriado para toda violação de regra de negócio no cadastro de clientes, sem exceção — nenhuma regra de negócio SHALL levantar um tipo de exceção que escape do handler de `HTTPException` da aplicação.

#### Scenario: Nome de cliente contendo número retorna 400, não 500
- **WHEN** um `POST /api/v1/clientes` é feito com um `nome` contendo ao menos um dígito
- **THEN** a API SHALL responder com status 400 e um `detail` explicando que o nome não pode conter números
- **AND** o erro SHALL ser registrado (console e Postgres) como um erro 4xx, do mesmo modo que os erros de CPF/e-mail duplicado

### Requirement: Erros de validação de payload (422) são registrados
O sistema SHALL capturar `RequestValidationError` (erros de validação de corpo/query de requisição do FastAPI) através de um exception handler global e registrar o erro (console e, quando o Postgres estiver acessível, na tabela `logs_erro`) com os mesmos campos usados para os demais erros 4xx: `correlation_id`, `endpoint`, `method`, `status_code` (422) e `module`.

#### Scenario: Payload inválido ao criar cliente é logado
- **WHEN** um `POST /api/v1/clientes` é feito com um campo obrigatório ausente ou um formato inválido (ex.: `email` sem `@`)
- **THEN** a API SHALL responder 422 com o mesmo formato de erro que o FastAPI já produz por padrão (sem alterar o body/status para o cliente da API)
- **AND** o sistema SHALL registrar um log com level WARNING, status_code 422, correlation_id da requisição e module referente à rota chamada

#### Scenario: Payload inválido ao criar apólice é logado
- **WHEN** um `POST /api/v1/apolices` é feito com um campo obrigatório ausente ou tipo inválido
- **THEN** a API SHALL responder 422 com o formato padrão do FastAPI
- **AND** o sistema SHALL registrar o mesmo tipo de log descrito no cenário anterior

### Requirement: Fallback de falha do sink de Postgres não usa saída não estruturada
Quando o sink de persistência de logs no PostgreSQL falhar (conexão indisponível, erro de escrita), o sistema SHALL registrar essa falha através do sistema de logging estruturado da aplicação (não via `print()` bruto), direcionado exclusivamente ao sink de console, para evitar recursão sobre o próprio sink que falhou.

#### Scenario: Falha ao gravar log de erro no Postgres é reportada de forma estruturada
- **WHEN** o sink de Postgres tenta persistir um log e a conexão com o banco falha
- **THEN** o sistema SHALL registrar essa falha através do logger da aplicação, com level ERROR, direcionado apenas ao console
- **AND** o sistema SHALL NOT tentar gravar essa falha de volta na tabela `logs_erro`
- **AND** a exceção original que gerou o log de erro SHALL continuar sendo respondida normalmente ao cliente da API (a falha do sink nunca deve propagar e quebrar a requisição)
