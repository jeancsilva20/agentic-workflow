# Corrigir 500 em POST /clientes ao cadastrar nome com número

## Why

Um alerta de monitoramento (SSAI-90) reportou que `POST /clientes` em QA retornou HTTP 500 em 3 chamadas amostradas, todas rejeitando o mesmo tipo de entrada: um nome de cliente contendo um número (ex.: `"João da Si4lva"`). Investigação do código confirma a causa: em `app/services/cliente_service.py::criar_cliente`, a validação de "nome contém número" levanta um `RuntimeError` não tratado, que escapa como HTTP 500 em vez de um erro de cliente (4xx). As duas validações de negócio vizinhas no mesmo método (CPF duplicado, e-mail duplicado) levantam corretamente `HTTPException(status_code=400, ...)`. Isto é um defeito de tipo de erro contra a própria convenção do arquivo, não a introdução de uma regra nova.

A recomendação do alerta ("ajustar validação para permitir números ou normalizar a entrada") é uma hipótese de monitoramento, não uma decisão de produto confirmada pelo código ou pelo card — ver `design.md` para a decisão em aberto correspondente.

## What Changes

- Corrigir `ClienteService.criar_cliente` para levantar `HTTPException(status_code=400, ...)` em vez de `RuntimeError` quando o nome do cliente contém um número, alinhando-se com o padrão já usado pelas validações de CPF e e-mail duplicados no mesmo método.
- Preservar a mensagem de erro existente (mesmo texto do alerta), apenas mudando o tipo/status do erro.
- Adicionar testes unitários para o método `criar_cliente` cobrindo: nome com número (agora 400, não 500), CPF duplicado (400), e-mail duplicado (400), e criação bem-sucedida (sem números no nome). O projeto não possui nenhuma suíte de testes hoje — esta mudança introduz a baseline mínima de `pytest` para este service.

## Capabilities

### New Capabilities
- `cadastro-clientes` — não existe ainda um capability canônico em `openspec/specs/` para o cadastro de clientes; esta mudança introduz seus requisitos formalmente (incluindo os dois já satisfeitos hoje, CPF e e-mail duplicados, documentados aqui para registrar o padrão de erro que a correção do nome passa a seguir), com foco na correção do requisito de validação de nome numérico.

### Modified Capabilities
(nenhuma — o capability ainda não existe em `openspec/specs/`)

## Impact

- **Código afetado:** `app/services/cliente_service.py` (método `criar_cliente`).
- **API:** `POST /clientes` — mudança de status HTTP de 500 para 400 quando o nome contém número; contrato de erro (`detail` da `HTTPException`) alinhado ao padrão das demais validações da rota.
- **Testes:** novo diretório `tests/` com baseline `pytest` (o projeto não tem nenhum hoje — ver Harness Report).
- **Dependências:** nenhuma nova dependência de produção; `pytest` (e `httpx`, já usado pelo FastAPI `TestClient` via `starlette`) como dependência de desenvolvimento.
- **Sem impacto em banco de dados/migrations.**
