## Why

O alerta SSAI-88 reporta que `POST /clientes` retorna HTTP 500 em QA ao tentar cadastrar `'João da Si4lva'`. O card, gerado por monitoramento, recomenda "ajustar a validação para permitir números" — mas essa recomendação nunca leu o código. Lendo `app/services/cliente_service.py::criar_cliente` (arquivo apontado pelo próprio traceback do alerta): a regra "nome contém número" levanta `raise RuntimeError(...)` sem captura, que escapa do handler de `HTTPException` de `app/main.py` e cai no handler genérico de `Exception`, retornando 500. As duas regras de negócio seguintes, no mesmo método — CPF duplicado e email duplicado — levantam `HTTPException(status_code=400, ...)`. `ApoliceService.criar_apolice` segue o mesmo padrão (`HTTPException(status_code=404, ...)` para cliente não encontrado). A regra do nome é a única exceção ao padrão do próprio arquivo: o defeito confirmado é o **tipo de exceção usado**, não a existência da regra em si.

Se a regra "nome não pode conter número" deve continuar existindo é uma decisão de produto que o card não sustenta com evidência — nada no repositório explica por que a regra foi criada. Essa pergunta fica registrada em `design.md` para a APROVAÇÃO 1 decidir; este change corrige apenas o tipo de exceção, preservando o comportamento de rejeitar nomes com números.

## What Changes

- Corrigir `ClienteService.criar_cliente`: a verificação de "nome contém número" passa a levantar `HTTPException(status_code=400, detail=...)` em vez de `RuntimeError`, alinhando com as duas regras de negócio seguintes no mesmo método e com o padrão usado em `ApoliceService`.
- Adicionar testes unitários para `ClienteService.criar_cliente` cobrindo: nome com número (400, não 500), CPF duplicado (400), email duplicado (400) e criação bem-sucedida.
- **[Decisão aberta — ver `design.md`]** Não decidir, neste change, se a regra "nome não pode conter número" deveria ser removida/alterada — o alerta recomenda isso, mas o repositório não documenta a motivação da regra. Mantém-se a regra, apenas com o status code correto.

## Capabilities

### New Capabilities
- `cadastro-clientes`: cobre as regras de negócio e o contrato de erro de `POST /clientes` (e das operações de escrita relacionadas em `ClienteService`) — nenhum `openspec/specs/cadastro-clientes/spec.md` existe hoje.

### Modified Capabilities
<!-- Nenhuma capability canônica existe em openspec/specs/ ainda; nada a modificar formalmente. -->

## Impact

- **Arquivos afetados:**
  - `app/services/cliente_service.py` — trocar `RuntimeError` por `HTTPException(400)` na validação de nome
  - Novo arquivo de teste unitário para `ClienteService` (framework a definir — ver `design.md`)
- **APIs:** `POST /clientes` (e `PUT`/`PATCH /clientes/{id}`, que reusam a mesma validação de nome via `criar_cliente`/`atualizar_cliente` — ver nota abaixo) passam a responder 400 em vez de 500 quando o nome contém número; nenhuma rota nova.
- **Banco de dados:** nenhuma alteração de schema.
- **Dependências:** nenhuma nova dependência.
- **Compatibilidade:** mudança de status code de 500 para 400 no caso de nome com número — não é breaking no sentido de contrato documentado (a API nunca declarou 500 como resposta esperada para esse caso), mas é uma mudança de comportamento observável para quem hoje trata esse caso como erro genérico.

Nota: `ClienteService.atualizar_cliente` não chama a validação de nome hoje (`criar_cliente` é o único ponto que valida `nome`); esse change não introduz a validação em `atualizar_cliente` porque isso amplia o escopo do defeito confirmado — fica fora do escopo, sem ser resolvido silenciosamente (ver `design.md`).
