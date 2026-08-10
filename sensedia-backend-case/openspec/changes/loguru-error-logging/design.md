## Context

A aplicação é uma API FastAPI (CRUD de Clientes e Apólices) com PostgreSQL via SQLAlchemy + Alembic. Atualmente usa `print()` no middleware de correlation ID e não possui logging estruturado. O objetivo é integrar o Loguru para persistir erros (4xx e 5xx) no PostgreSQL, mantendo saída no console.

**Estado atual:**
- Middleware gera `correlation_id` via `uuid4` e usa `print()`
- Services levantam `HTTPException` para erros de regra de negócio (400, 404)
- Não há exception handler global; exceções não tratadas geram 500 genérico do FastAPI
- Arquitetura em camadas: Routers → Services → Repositories → Models

## Goals / Non-Goals

**Goals:**
- Persistir logs de erro (status >= 400) no PostgreSQL com campos completos
- Manter logging no console simultaneamente
- Capturar HTTPExceptions (4xx) e exceções genéricas (5xx) via exception handlers globais
- Propagar correlation_id nos logs de erro
- Usar sessão SQLAlchemy dedicada para o sink (independente da sessão da requisição)

**Non-Goals:**
- Rotação automática ou purge de logs antigos
- Logs de info/debug no banco (apenas erros)
- Substituir o sistema de correção de bugs existentes (o log é para auditoria)

## Decisions

### 1. Loguru com sink customizado para PostgreSQL
**Decisão:** Criar uma função sink que recebe o `Message` do Loguru e insere diretamente no banco via `SessionLocal()`.

**Alternativas consideradas:**
- *Python logging + SQLAlchemy handler*: Mais verboso, sem contexto extra nativo. Loguru simplifica o binding de `correlation_id` via `extra`.
- *Loguru + loguru-sinks-postgres*: Biblioteca de terceiro não mantida, risco de incompatibilidade.
- *Logs estruturados em arquivo + logrotate*: Não atende ao requisito de persistência em banco.

### 2. Sessão dedicada no sink
**Decisão:** O sink abre e fecha sua própria `SessionLocal()` a cada chamada, sem compartilhar contexto com a sessão da requisição.

**Rationale:** Evita conflitos de transação e deadlock quando o erro ocorre no meio de uma transação. O sink grava de forma autônoma.

### 3. Exception handlers globais no FastAPI
**Decisão:** Registrar `@app.exception_handler(HTTPException)` e `@app.exception_handler(Exception)` no `main.py`.

**Rationale:** Centraliza a captura de erros em um único ponto, garantindo que todo erro passe pelo Loguru antes de retornar a resposta. Evita espalhar `try/except` nos services.

### 4. Level mapping por status code
**Decisão:**
- Status 4xx → Level WARNING (erro de cliente/regra de negócio)
- Status 5xx → Level ERROR (erro interno)

**Rationale:** Diferencia erros esperados de erros inesperados, facilitando filtragem e alertas.

### 5. Context binding do correlation_id
**Decisão:** Usar `logger.bind(correlation_id=correlation_id)` no middleware para que todos os logs dentro da requisição incluam automaticamente o correlation_id.

**Rationale:** O Loguru suporta `bind()` que propaga o contexto para todas as chamadas subsequentes, evitando passagem manual.

### 6. Estrutura de arquivos
- `app/models/models.py` — adicionar `LogErro`
- `app/core/logging_config.py` — configuração do Loguru e sink PostgreSQL (novo arquivo)
- `app/routers/log_router.py` — rota de consulta de logs com filtros (novo arquivo)
- `app/repositories/log_repo.py` — repositório de logs com filtros por data, level e status_code (novo arquivo)
- `app/services/log_service.py` — service de logs (novo arquivo)
- `app/schemas/schemas.py` — adicionar `LogErroResponse`
- `app/main.py` — registrar handlers, configurar startup, substituir prints, registrar rota de logs
- `alembic/versions/` — nova migration

### 7. Rota de consulta de logs com filtro por data
**Decisão:** Criar `GET /api/v1/logs` com query params opcionais: `data_inicio`, `data_fim`, `level`, `status_code`. Retorna lista de logs ordenados por timestamp decrescente.

**Alternativas consideradas:**
- *Paginação obrigatória*: Para o escopo do case, não é necessário. Pode ser adicionada futuramente.
- *Filtro apenas por data*: O usuário pediu filtro por data, mas adicionamos também level e status_code como filtros opcionais por serem triviais e úteis para auditoria.

**Rationale:** Segue a mesma arquitetura em camadas (Router → Service → Repository) das demais rotas, mantendo consistência.

## Risks / Trade-offs

- **[Sink pode falhar se o banco estiver indisponível]** → O sink captura exceções silenciosamente e registra no console; a aplicação continua funcionando.
- **[Overhead de I/O no banco a cada erro]** → Aceitável para volume esperado do case. Em alta escala, considerar batch insert ou fila assíncrona.
- ** [Tabela logs_erro cresce indefinidamente]** → Fora do escopo deste change. Recomenda-se criar job de purge futuro.
- ** [Sessão dedicada por log pode exaurir connections]** → A sessão é aberta e fechada imediatamente após o insert, liberando a conexão.

## Migration Plan

1. Adicionar `loguru` ao `requirements.txt` e instalar
2. Criar modelo `LogErro` em `app/models/models.py`
3. Gerar migration Alembic: `alembic revision --autogenerate -m "adiciona tabela logs_erro"`
4. Aplicar migration: `alembic upgrade head`
5. Criar `app/core/logging_config.py` com sink e configuração
6. Atualizar `app/main.py` com exception handlers, configuração do Loguru e substituição dos prints
7. Testar manualmente: provocar erro 400, 404 e 500 e verificar registros no banco

**Rollback:** `alembic downgrade -1` remove a tabela; remover o código do Loguru reverte ao estado anterior.

## Open Questions

Nenhuma pendente — todas as decisões foram alinhadas com o solicitante.
