## ADDED Requirements

### Requirement: Persistência de logs de erro no PostgreSQL
O sistema SHALL gravar todos os erros (status code >= 400) no banco de dados PostgreSQL utilizando o Loguru com um sink customizado, além de exibi-los no console.

#### Scenario: Erro inesperado (500) é gravado no banco
- **WHEN** uma exceção não tratada ocorre durante o processamento de uma requisição
- **THEN** o sistema SHALL registrar um log no banco com level ERROR, message contendo a mensagem da exceção, traceback completo, endpoint, method, status_code 500, correlation_id da requisição e module onde ocorreu
- **AND** o sistema SHALL exibir o mesmo log no console

#### Scenario: Erro de regra de negócio (400) é gravado no banco
- **WHEN** um HTTPException com status_code 400 é levantado (ex: CPF duplicado)
- **THEN** o sistema SHALL registrar um log no banco com level WARNING, message contendo o detail da exceção, endpoint, method, status_code 400, correlation_id da requisição e module onde ocorreu
- **AND** o sistema SHALL exibir o mesmo log no console

#### Scenario: Erro de recurso não encontrado (404) é gravado no banco
- **WHEN** um HTTPException com status_code 404 é levantado (ex: cliente não encontrado)
- **THEN** o sistema SHALL registrar um log no banco com level WARNING, message contendo o detail da exceção, endpoint, method, status_code 404, correlation_id da requisição e module onde ocorreu

#### Scenario: Requisição bem-sucedida não gera log de erro
- **WHEN** uma requisição é processada com sucesso (status code 2xx)
- **THEN** o sistema SHALL NOT gravar nenhum log na tabela de erros

### Requirement: Tabela logs_erro no PostgreSQL
O sistema SHALL criar uma tabela `logs_erro` no PostgreSQL via migration Alembic com os campos necessários para auditoria de erros.

#### Scenario: Migration cria a tabela logs_erro
- **WHEN** a migration Alembic é executada
- **THEN** a tabela `logs_erro` SHALL ser criada com as colunas: id (PK, auto-increment), timestamp (datetime, default now), level (varchar), message (text), correlation_id (varchar), endpoint (varchar), method (varchar), status_code (integer), traceback (text), module (varchar)

#### Scenario: Migration de rollback remove a tabela
- **WHEN** a migration Alembic é revertida
- **THEN** a tabela `logs_erro` SHALL ser removida do banco de dados

### Requirement: Sink customizado do Loguru para PostgreSQL
O sistema SHALL implementar um sink customizado do Loguru que persiste os logs diretamente no PostgreSQL utilizando uma sessão dedicada do SQLAlchemy, independente da sessão da requisição.

#### Scenario: Sink escreve no banco com sucesso
- **WHEN** o Loguru emite um log de erro
- **THEN** o sink SHALL abrir uma sessão dedicada do SQLAlchemy, inserir o registro na tabela `logs_erro` e fechar a sessão

#### Scenario: Falha na escrita do sink não quebra a aplicação
- **WHEN** o sink tenta gravar no banco e ocorre um erro de conexão ou escrita
- **THEN** o sink SHALL capturar o erro silenciosamente e registrar no console, sem propagar a exceção para a aplicação

### Requirement: Configuração do Loguru no startup da aplicação
O sistema SHALL configurar o Loguru durante o startup da aplicação FastAPI com dois sinks ativos simultaneamente: console (stdout) e PostgreSQL.

#### Scenario: Loguru é configurado no startup
- **WHEN** a aplicação FastAPI inicia
- **THEN** o Loguru SHALL ter o sink de console configurado com formato legível (timestamp, level, message)
- **AND** o Loguru SHALL ter o sink de PostgreSQL configurado para gravar apenas logs de level ERROR ou superior, bem como WARNING para erros 4xx

#### Scenario: Substituição dos prints do middleware
- **WHEN** o middleware de correlation ID processa uma requisição
- **THEN** o sistema SHALL usar o Loguru em vez de `print()` para registrar o início e fim da requisição
- **AND** o correlation_id SHALL ser incluído como context binding do Loguru (extra={"correlation_id": ...})

### Requirement: Exception handler global para captura de erros
O sistema SHALL registrar exception handlers globais no FastAPI para capturar HTTPExceptions (4xx) e exceções genéricas (5xx), logando os erros antes de retornar a resposta.

#### Scenario: HTTPException é capturada e logada
- **WHEN** um HTTPException é levantado em qualquer rota
- **THEN** o exception handler SHALL registrar o log via Loguru com os dados da exceção
- **AND** SHALL retornar a resposta HTTP normalmente (sem alterar o status code ou body)

#### Scenario: Exceção não tratada é capturada e logada
- **WHEN** uma exceção genérica (não HTTPException) é levantada em qualquer rota
- **THEN** o exception handler SHALL registrar o log via Loguru com level ERROR e traceback completo
- **AND** SHALL retornar HTTP 500 com mensagem genérica "Erro interno do servidor"

#### Scenario: Correlation ID é propagado para o log de erro
- **WHEN** um erro ocorre durante uma requisição que já passou pelo middleware de correlation ID
- **THEN** o log de erro SHALL incluir o correlation_id da requisição nos campos do registro

### Requirement: Rota de consulta de logs com filtro por data
O sistema SHALL expor um endpoint `GET /api/v1/logs` que retorna os logs de erro persistidos no PostgreSQL, com suporte a filtragem por intervalo de datas (data inicial e data final), level e status_code.

#### Scenario: Listar todos os logs sem filtro
- **WHEN** uma requisição `GET /api/v1/logs` é feita sem parâmetros de filtro
- **THEN** o sistema SHALL retornar todos os registros da tabela `logs_erro` ordenados por timestamp decrescente

#### Scenario: Filtrar logs por intervalo de datas
- **WHEN** uma requisição `GET /api/v1/logs?data_inicio=2025-01-01&data_fim=2025-01-31` é feita
- **THEN** o sistema SHALL retornar apenas os logs cujo timestamp está entre `data_inicio` (inclusive) e `data_fim` (inclusive)

#### Scenario: Filtrar logs por level
- **WHEN** uma requisição `GET /api/v1/logs?level=ERROR` é feita
- **THEN** o sistema SHALL retornar apenas os logs cujo level corresponde ao informado

#### Scenario: Filtrar logs por status_code
- **WHEN** uma requisição `GET /api/v1/logs?status_code=500` é feita
- **THEN** o sistema SHALL retornar apenas os logs cujo status_code corresponde ao informado

#### Scenario: Filtrar logs combinando data, level e status_code
- **WHEN** uma requisição `GET /api/v1/logs?data_inicio=2025-01-01&data_fim=2025-01-31&level=ERROR&status_code=500` é feita
- **THEN** o sistema SHALL retornar apenas os logs que atendam a todos os critérios simultaneamente

#### Scenario: Nenhum log encontrado com os filtros
- **WHEN** uma requisição `GET /api/v1/logs` com filtros que não correspondem a nenhum registro
- **THEN** o sistema SHALL retornar HTTP 200 com lista vazia
