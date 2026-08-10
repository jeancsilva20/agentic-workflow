## Context

A API é um FastAPI (CRUD de Clientes e Apólices) com PostgreSQL via SQLAlchemy + Alembic. Um change anterior (`openspec/changes/loguru-error-logging/`, nunca arquivado, mas já mergeado ao `main` nos commits `9493384`, `6751930`, `297f5a1`) implementou logging estruturado com `loguru`: sink de console, sink customizado que persiste erros na tabela `logs_erro` via uma `SessionLocal()` dedicada, e handlers globais para `HTTPException` e `Exception`.

SSAI-89 pede para "melhorar cenários de erros e logs" e para usar bibliotecas nativas do Python "para garantir qualidade do código". Não há comentários no card e não há critérios de aceite explícitos além da descrição — a análise de código (harness + exploração) identificou três inconsistências confirmadas e duas decisões de produto/arquitetura que ficam abertas abaixo.

## Goals / Non-Goals

**Goals:**
- Corrigir as inconsistências de tipo de exceção e cobertura de logging encontradas na análise (ver proposal.md "What Changes", itens 1–3).
- Responder de forma explícita, com opções e evidências, ao pedido do card por bibliotecas nativas — sem decidir unilateralmente o alcance da mudança.
- Manter os contratos HTTP existentes (nenhuma rota muda de comportamento externo).

**Non-Goals:**
- Reescrever a camada de persistência de logs (schema da tabela `logs_erro` permanece igual).
- Adicionar rotação/purge de logs antigos (fora do escopo, já registrado como non-goal no change anterior).
- Arquivar o change `loguru-error-logging` pré-existente (é dívida técnica anterior a este card; será avaliado separadamente, não bloqueia este change).

## Decisions

### 1. Corrigir `RuntimeError` → `HTTPException(400)` em `ClienteService.criar_cliente`
**Decisão:** trocar o tipo de exceção para `HTTPException(status_code=400, detail=...)`, igual às duas regras de negócio imediatamente abaixo no mesmo método.

**Evidência:** `app/services/cliente_service.py:12-16` é a única regra do arquivo (e do `ApoliceService`) que levanta uma exceção crua; toda vizinha usa `HTTPException`. Isso não é uma decisão de produto (não muda o que a regra aceita ou rejeita), é uma correção de um defeito confirmado contra a própria convenção do arquivo.

**Alternativa considerada:** remover a regra "nome não pode ter número" (a recomendação implícita de um card de alerta típico seguiria essa linha). **Rejeitada** aqui: nada no código ou no card de SSAI-89 pede a remoção da regra de negócio; card se limita a pedir melhoria de logs/erros. Mudar a regra de validação em si é uma mudança de escopo maior e não está sendo pedida.

### 2. Handler para `RequestValidationError` (422)
**Decisão:** registrar `@app.exception_handler(RequestValidationError)` em `app/main.py`, logando (console + Postgres) com level WARNING, status_code 422, message com os erros de validação resumidos, e retornando o mesmo formato de resposta que o FastAPI já usa por padrão (não alterar o body/status que o cliente da API recebe).

**Evidência:** `RequestValidationError` não é subclasse de `HTTPException`; o FastAPI já registra um handler default para ela antes de qualquer handler genérico de `Exception` do app ter chance de rodar. Logo, hoje, uma requisição malformada (ex.: CPF ausente, email invalido) nunca aparece na tabela `logs_erro` nem no console formatado pelo Loguru — só no 422 que o cliente HTTP recebe. Isso é uma lacuna real de "análise de erros", que é exatamente o que o card pede.

**Rationale:** mantém consistência arquitetural com os demais handlers já existentes (mesmo padrão: capturar, logar, repassar a resposta).

### 3. Remover `print()` de dentro do sink Postgres
**Decisão:** o fallback de erro do `postgres_sink` (`app/core/logging_config.py:27,31`) passa a usar `logger` do próprio sistema de logging (Loguru, ou o módulo `logging` nativo, dependendo da Decisão 4) **direcionado apenas ao sink de console** — nunca ao sink Postgres, para não criar recursão (uma falha ao gravar log de erro não deve tentar gravar outro log de erro no mesmo caminho que já falhou).

**Rationale:** hoje, se o Postgres cair, os erros do próprio sink ficam fora do formato/nível estruturado do resto da aplicação — o que dificulta exatamente a "facilidade de análise" que o card pede.

### 4. [ABERTA] Migração de `loguru` para o módulo nativo `logging`
O card pede explicitamente para "usar libs nativas do python para garantir qualidade do código". A stack de logging atual é 100% `loguru` (terceiros).

**Opções:**
- **A — Manter `loguru`.** Menor esforço, menor risco de regressão; mas não atende ao pedido explícito do card.
- **B — Migrar totalmente para o módulo `logging` da stdlib.** Substitui `logger.add(sys.stdout, ...)` por um `StreamHandler` + `Formatter`, o `postgres_sink` por um `logging.Handler` customizado (`emit()` faz o insert), e `logger.bind(correlation_id=...)` por `contextvars` + um `logging.Filter`/`LoggerAdapter` que injeta o `correlation_id` em cada registro. Atende ao pedido explícito do card; remove uma dependência de terceiros do `requirements.txt`. Custo: reescreve toda a superfície de logging (`app/main.py`, `app/core/logging_config.py`), maior superfície de revisão.
- **C — Híbrido:** manter `loguru` só para o sink de Postgres (já testado em produção) e usar `logging` nativo apenas em código novo (ex.: o handler de `RequestValidationError`). Atende parcialmente ao pedido, mas cria duas formas de logar erro no mesmo processo — inconsistente e provavelmente pior para "facilitar análises" do que qualquer uma das opções acima.

**Recomendação:** Opção B. O card pede a migração de forma explícita (não é uma hipótese de um card de alerta), a stdlib `logging` cobre integralmente as capacidades hoje usadas (formatação, handlers customizados, binding de contexto via `LoggerAdapter`/`contextvars`), e a Opção C piora a consistência que o card quer melhorar. Fica para APROVAÇÃO 1 confirmar o alcance antes da implementação, dado que é uma reescrita cross-cutting.

### 5. [ABERTA] Framework de testes para os testes novos deste change
Não há nenhum test runner declarado no repositório (nem `pytest`, nem `unittest` configurado em CI — não há CI). O card pede bibliotecas nativas para "garantir qualidade do código", o que sugere preferir `unittest` (stdlib) a `pytest` (terceiros) para os testes que este change adiciona.

**Opções:**
- **A — `unittest`** (stdlib): sem nova dependência; API mais verbosa; roda com `python -m unittest`.
- **B — `pytest`**: mais expressivo, fixtures mais simples, mas é uma nova dependência de terceiros — o oposto do que o card pede.

**Recomendação:** Opção A (`unittest`), coerente com o pedido do card e sem introduzir uma dependência nova só para testes. Fica para APROVAÇÃO 1 confirmar.

## Risks / Trade-offs

- **[Migrar de `loguru` para `logging` nativo (se aprovado) tem maior superfície de regressão]** → cobrir com testes unitários novos (handler de exceção, filtro de correlation_id, sink Postgres) antes de remover `loguru` do `requirements.txt`.
- **[Handler de `RequestValidationError` pode mudar acidentalmente o body/status 422 que o cliente recebe]** → reusar exatamente o formato de resposta que o `RequestValidationError` default do FastAPI já produz (`{"detail": [...]}`), apenas adicionando o efeito colateral de logging.
- **[Fallback do sink logando para o sink de console pode ainda assim falhar (ex.: stdout fechado)]** → aceitável; é estritamente melhor que `print()` direto e o comportamento de "silenciar e não propagar para a aplicação" (já um requisito confirmado do change anterior) continua valendo.
- **[Este change convive com o change `loguru-error-logging` não arquivado]** → não é bloqueante; o arquivamento desse change antigo é dívida pré-existente e será avaliado como um problema separado, fora do escopo de SSAI-89.

## Migration Plan

1. Corrigir o tipo de exceção em `ClienteService.criar_cliente` (Decisão 1).
2. Adicionar o handler de `RequestValidationError` em `app/main.py` (Decisão 2).
3. Remover os `print()` do `postgres_sink`, substituindo por log no sink de console (Decisão 3).
4. Aplicar a Decisão 4 (migração de logging) e a Decisão 5 (framework de teste) conforme aprovado em APROVAÇÃO 1.
5. Testar manualmente (ou via teste automatizado, dependendo da Decisão 5): erro 400 (nome com número), 404, 422 (payload invalido) e 500 — confirmar que todos aparecem no console e (exceto quando o Postgres não está acessível) na tabela `logs_erro`.

**Rollback:** cada item é uma mudança de código isolada e reversível via `git revert`; nenhuma migration de banco é necessária para este change.

## Open Questions

1. Decisão 4 — migrar de `loguru` para `logging` nativo: alcance total (Opção B, recomendada) ou manter `loguru` (Opção A)?
2. Decisão 5 — testes novos em `unittest` (recomendada) ou `pytest`?
