## 1. Corrigir tipo de exceção em Clientes

- [ ] 1.1 Em `app/services/cliente_service.py`, trocar o `RuntimeError` da regra "nome contém número" por `HTTPException(status_code=400, detail=...)`
- [ ] 1.2 Confirmar (manualmente ou via teste) que o erro passa a ser logado como 4xx (console e Postgres, quando acessível), igual às regras de CPF/e-mail duplicado

## 2. Registrar erros de validação de payload (422)

- [ ] 2.1 Adicionar `@app.exception_handler(RequestValidationError)` em `app/main.py`, reaproveitando o formato de resposta default do FastAPI
- [ ] 2.2 Logar (console + Postgres) o erro 422 com `correlation_id`, `endpoint`, `method`, `status_code`, `module`
- [ ] 2.3 Confirmar que o body/status code 422 retornado ao cliente da API não muda

## 3. Corrigir fallback do sink de Postgres

- [ ] 3.1 Remover os `print()` de `app/core/logging_config.py` (linhas do fallback de erro do `postgres_sink`)
- [ ] 3.2 Substituir por uma chamada ao logger da aplicação direcionada apenas ao sink de console (sem recursão sobre o sink Postgres)

## 4. Decisão 4 — migração de logging (conforme aprovado em APROVAÇÃO 1)

- [ ] 4.1 Se aprovada a Opção B (migração total): substituir a configuração de console do Loguru por um `logging.StreamHandler` + `Formatter` equivalente
- [ ] 4.2 Se aprovada a Opção B: substituir o `postgres_sink` do Loguru por um `logging.Handler` customizado com o mesmo comportamento (sessão dedicada, captura silenciosa de falha)
- [ ] 4.3 Se aprovada a Opção B: substituir `logger.bind(correlation_id=...)` por um mecanismo de contexto nativo (`contextvars` + `logging.Filter` ou `LoggerAdapter`) que injete o `correlation_id` em cada log
- [ ] 4.4 Se aprovada a Opção B: atualizar todos os call sites (`app/main.py`, `app/core/logging_config.py`) para usar `logging` em vez de `loguru`, e remover `loguru` de `requirements.txt`
- [ ] 4.5 Se rejeitada (mantém `loguru`): registrar a decisão final em `design.md` e não abrir tarefas de migração

## 5. Testes (framework conforme Decisão 5)

- [ ] 5.1 Escrever teste cobrindo: nome de cliente com número retorna 400 (não 500) e é logado como 4xx
- [ ] 5.2 Escrever teste cobrindo: payload inválido em `POST /clientes` e `POST /apolices` retorna 422 e gera log correspondente
- [ ] 5.3 Escrever teste cobrindo: falha simulada do sink de Postgres não propaga exceção e não usa `print()`
- [ ] 5.4 Se aprovada a Opção B (Decisão 4): escrever teste cobrindo o novo handler de logging (console) e o filtro/adapter de correlation_id

## 6. Validação final

- [ ] 6.1 Rodar lint/format aplicável (nenhum configurado hoje — se um baseline for adicionado, rodar aqui)
- [ ] 6.2 Rodar os testes novos deste change
- [ ] 6.3 Revisar o diff completo contra cada requisito de `specs/error-logging/spec.md`
