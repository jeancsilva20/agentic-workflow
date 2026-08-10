## Context

`POST /clientes` está retornando HTTP 500 em QA. O card SSAI-88 é gerado por alerta de monitoramento e traz uma hipótese ("ajustar a validação para permitir números"), não um requisito confirmado. A leitura do código (`app/services/cliente_service.py::criar_cliente`) mostra que a causa raiz é o *tipo* de exceção levantado pela regra "nome contém número" (`RuntimeError`, não capturado, vira 500), não a regra em si — as duas regras de negócio seguintes no mesmo método (CPF e email duplicados) e a regra equivalente em `ApoliceService` usam `HTTPException` com status 4xx.

O repositório não tem, hoje, nenhum test runner declarado (`requirements.txt` não lista `pytest` nem `unittest` como dependência explícita — `unittest` é biblioteca nativa e não precisa de dependência), nenhum linter/formatter, e nenhuma pasta `tests/`.

## Goals / Non-Goals

**Goals:**
- Corrigir o tipo de exceção da regra de nome para eliminar o 500 indevido.
- Cobrir esse comportamento (e os comportamentos-irmãos já corretos) com testes automatizados.

**Non-Goals:**
- Decidir se a regra "nome não pode conter número" deve ser removida, afrouxada, ou ter sua mensagem revisada — não há evidência no repositório sobre a motivação original da regra.
- Adicionar validação de nome em `atualizar_cliente` (ela não existe lá hoje e não é o que o card reporta).
- Introduzir um framework de lint/format/type-check onde nenhum existe — fora do escopo deste bugfix pontual; ver `python-quality` para quando isso for proposto.

## Decisions

- **Tipo de exceção:** `HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=...)`, no mesmo padrão das duas verificações seguintes no método. Alternativa considerada e rejeitada: `status_code=422` (erro de validação de payload) — rejeitada porque a validação depende de estado de negócio verificado imperativamente dentro do service (não é uma validação de schema Pydantic declarativa), e o repositório já reserva 400 para esse tipo de regra nas linhas vizinhas.
- **Mensagem de erro:** preservar o texto em português já usado ("Não é possível cadastrar o cliente '<nome>': nome contém número...") como `detail`, apenas trocando o mecanismo de exceção — minimiza a superfície da mudança.

## Risks / Trade-offs

- [Risco] Mudar de 500 para 400 é uma mudança de comportamento observável para qualquer cliente do Gateway que hoje trate esse caso especificamente como "erro genérico interno". → Mitigação: 500 nunca foi um contrato documentado para esse caso (é a falha que o card está reportando); 400 é estritamente mais correto e mais informativo (`detail` explica o motivo). Não há endpoint de contrato OpenAPI publicado que declare 500 aqui.
- [Risco] Não existe teste ou tooling hoje; adicionar testes agora usando uma escolha de framework pode conflitar com uma decisão futura de arquitetura de testes do time. → Mitigação: usar `unittest` (biblioteca nativa da stdlib, decisão abaixo), reduz a superfície de nova dependência; migrar depois é um custo pequeno e localizado.

## Open Questions

### 1. A regra "nome não pode conter número" deve continuar existindo?
- **Opção A — manter a regra (recomendado):** o alerta recomenda removê-la, mas essa recomendação foi escrita sem ler o código e não tem evidência de motivação de negócio documentada no repositório. Remover uma validação de negócio já em produção tem um raio de impacto maior do que corrigir um status code, e não há como saber, sem essa spec, se a regra existe por exigência de algum sistema downstream (ex.: emissão de apólice, integração com o Gateway).
- **Opção B — remover a regra:** seguiria a recomendação do alerta ao pé da letra, permitindo nomes com números (ex.: nomes com sufixos, apelidos, etc.). Risco: se a regra existir por um motivo de negócio não documentado, isso reabriria um problema já resolvido antes.
- **Recomendação:** Opção A. Este change implementa apenas a correção do tipo de exceção; a remoção/alteração da regra em si, se desejada, deveria ser um card e uma spec separados, com a motivação de negócio explicitada por quem pediu a regra originalmente.

### 2. Qual framework de teste usar, já que o projeto não declara nenhum?
- **Opção A — `unittest` (biblioteca nativa, recomendado):** zero dependência nova; roda com `python -m unittest`; suficiente para os quatro cenários de `criar_cliente` descritos no spec, que não exigem fixtures complexas.
- **Opção B — `pytest`:** mais expressivo e o padrão de fato no ecossistema Python, mas introduz uma dependência nova (`pytest` + `pytest-mock` ou similar) num projeto que hoje não declara nenhuma, para um bugfix pontual de 4 cenários.
- **Recomendação:** Opção A (`unittest`) para este change, dado o tamanho do escopo (correção pontual + 4 cenários). Se um baseline de testes mais amplo for desejado para o projeto como um todo, isso é uma decisão de tooling separada (ver `python-quality`), não algo a decidir dentro de um bugfix.
