## Why

A aplicação atualmente utiliza `print()` para logging no middleware de correlation ID, sem nenhuma persistência estruturada de erros. Erros inesperados (500) e erros de regra de negócio (4xx) não são registrados de forma auditável. A integração do Loguru com um sink customizado para PostgreSQL permitirá rastreabilidade completa, facilitando diagnóstico e auditoria.

## What Changes

- Adicionar `loguru` ao `requirements.txt`
- Criar modelo `LogErro` (tabela `logs_erro`) com campos: id, timestamp, level, message, correlation_id, endpoint, method, status_code, traceback, module
- Criar migration Alembic para a nova tabela `logs_erro`
- Criar sink customizado do Loguru que persiste logs no PostgreSQL via SessionLocal do SQLAlchemy
- Configurar Loguru no startup da aplicação com dois sinks: console (stdout) e PostgreSQL
- Substituir os `print()` do middleware de correlation ID por chamadas do Loguru
- Adicionar exception handler global para capturar e logar HTTPExceptions (4xx) e exceções não tratadas (5xx) antes de retornar a resposta
- Integrar o correlation_id do middleware nos logs de erro
- Adicionar rota `GET /api/v1/logs` para consultar logs persistidos no banco, com filtros opcionais por intervalo de datas (data_inicio, data_fim), level e status_code

## Capabilities

### New Capabilities
- `error-logging`: Persistência de logs de erro (4xx e 5xx) no PostgreSQL via Loguru com sink customizado, incluindo correlation_id, endpoint, method, status_code, traceback e module

### Modified Capabilities
<!-- Nenhuma capability existente é modificada -->

## Impact

- **Dependências:** Nova dependência `loguru` no requirements.txt
- **Banco de dados:** Nova tabela `logs_erro` (via migration Alembic)
- **Arquivos afetados:**
  - `requirements.txt` - adicionar loguru
  - `app/models/models.py` - adicionar modelo LogErro
  - `app/core/database.py` - adicionar sink customizado do Loguru
  - `app/main.py` - configurar Loguru no startup, substituir prints, adicionar exception handlers, registrar rota de logs
  - `app/routers/log_router.py` - nova rota de consulta de logs com filtros
  - `app/repositories/log_repo.py` - repositório de logs com filtros
  - `app/services/log_service.py` - service de logs
  - `app/schemas/schemas.py` - schema LogErroResponse
  - `alembic/versions/` - nova migration para tabela logs_erro
- **APIs:** Nova rota `GET /api/v1/logs` para consulta de logs com filtros opcionais (data_inicio, data_fim, level, status_code)
- **Performance:** Inserção de log no banco em cada erro; uso de sessão dedicada para evitar conflitos com a sessão da requisição
