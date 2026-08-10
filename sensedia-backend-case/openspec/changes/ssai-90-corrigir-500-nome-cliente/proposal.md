## Why

Um alerta de monitoramento (SSAI-90) reportou que `POST /clientes` retornou HTTP 500 em QA para clientes cujo nome contém números (ex.: `'João da Si4lva'`). A causa raiz, confirmada em `app/services/cliente_service.py::criar_cliente`, é que a validação de nome levanta um `RuntimeError` não tratado — que escapa para o handler genérico de exceções e vira 500 — enquanto as duas regras de negócio vizinhas na mesma função (CPF duplicado, e-mail duplicado) levantam `HTTPException(status_code=400, ...)` corretamente. O alerta descreve um problema real (500 indevido), mas sua causa é o tipo de erro usado, não necessariamente a regra de negócio em si (ver `design.md` para a decisão em aberto sobre a regra).

## What Changes

- Corrigir `ClienteService.criar_cliente` para levantar `HTTPException(status_code=400, ...)` em vez de `RuntimeError` quando o nome do cliente contém um número, alinhando com o padrão já usado pelas validações de CPF e e-mail duplicados na mesma função.
- Adicionar testes unitários para o método `criar_cliente`, cobrindo o caso do nome com número (agora 400, não mais 500) e os casos de regressão já existentes (CPF duplicado, e-mail duplicado, criação bem-sucedida).

## Capabilities

### New Capabilities
- `cadastro-clientes`: esta é a primeira vez que a capability de cadastro de clientes é formalizada em OpenSpec (não existe ainda em `openspec/specs/`). O spec documenta o comportamento de criação de cliente relevante a este change — a validação de nome (o defeito corrigido) e as validações vizinhas de CPF/e-mail duplicados (comportamento existente, inalterado, incluído para dar contexto e cobertura de regressão).

### Modified Capabilities
<!-- Nenhuma capability existente em openspec/specs/ é modificada; cadastro-clientes ainda não existia como capability canônica -->

## Impact

- **Código afetado:** `app/services/cliente_service.py` (método `criar_cliente`)
- **APIs:** `POST /api/v1/clientes` — mesmo endpoint, mudança apenas no status code e formato do erro retornado quando o nome contém número (de 500 genérico para 400 com `detail` estruturado, no mesmo formato usado pelos outros erros de validação do endpoint)
- **Testes:** novo módulo de testes unitários para `ClienteService.criar_cliente` (o projeto não possui suíte de testes hoje — ver `harness/SSAI-90-harness-report.md`); usa `unittest` da biblioteca padrão, sem adicionar dependências novas
- **Dependências:** nenhuma nova dependência
- **Banco de dados:** nenhuma alteração de schema/migration
