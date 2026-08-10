# Design — Corrigir 500 em POST /clientes ao cadastrar nome com número

## Context

`app/services/cliente_service.py::criar_cliente` executa três validações de negócio antes de persistir um novo cliente:

```python
if re.search(r'\d', dados_cliente.nome):
    raise RuntimeError(...)                          # -> não tratado -> 500
if self.repository.buscar_por_cpf(dados_cliente.cpf):
    raise HTTPException(status_code=400, ...)         # -> 400
if self.repository.buscar_por_email(dados_cliente.email):
    raise HTTPException(status_code=400, ...)         # -> 400
```

Não há um exception handler global para `RuntimeError` em `app/main.py` (apenas o handler genérico de `Exception`, que loga e retorna 500 — ver `LogService`/middleware de correlação). Por isso, a validação de nome se comporta de forma diferente das duas vizinhas na mesma função: entrada rejeitada pelo mesmo tipo de motivo (regra de negócio no cadastro), mas com um status HTTP incompatível com o padrão REST esperado (erro do cliente, não do servidor).

O projeto não possui suíte de testes (`tests/` inexistente, nenhuma dependência de teste em `requirements.txt`) — ver Harness Report (`SSAI-90-harness-report.md`).

## Goals / Non-Goals

**Goals**
- Fazer com que `POST /clientes` retorne 400 (não 500) quando o nome contém um número, mantendo a mensagem de erro atual.
- Alinhar o tratamento de erro dessa validação com o padrão já estabelecido pelas validações de CPF/e-mail duplicados no mesmo método.
- Cobrir o método `criar_cliente` com testes unitários mínimos, já que nenhum existe hoje.

**Non-Goals**
- Não é objetivo desta mudança decidir se nomes com números devem ou não ser aceitos (ver Open Questions).
- Não é objetivo introduzir um exception handler global para `RuntimeError`/exceções não tratadas em `app/main.py` — o escopo é a correção pontual no service, consistente com o padrão local já existente (`HTTPException` levantada diretamente no service, sem handler intermediário).
- Não é objetivo normalizar/sanitizar a entrada de nome (ex.: remover números automaticamente) — isso mudaria silenciosamente o dado do cliente e não foi solicitado nem pelo card nem evidenciado no código.

## Decisions

1. **Trocar `RuntimeError` por `HTTPException(status_code=400, detail=...)`, reaproveitando a mensagem de erro atual.** Alternativa considerada: criar um exception handler global para `RuntimeError` em `app/main.py`. Rejeitada porque nenhuma outra validação de negócio no serviço usa esse padrão — todas as demais levantam `HTTPException` diretamente — e um handler global adicionaria uma segunda convenção para o mesmo problema, exatamente o tipo de inconsistência que este fix está corrigindo.
2. **Manter a validação de nome com número como está (apenas corrigir o tipo de erro).** A remoção ou alteração da regra de negócio (permitir números no nome) é uma decisão de produto sem evidência no código ou nos critérios do card — não decidida aqui (ver Open Questions).
3. **Adicionar `pytest` + `httpx` (via `fastapi.testclient.TestClient`, já transitivo de `starlette`) como dependências de desenvolvimento**, criando `tests/` com um teste focado em `ClienteService.criar_cliente`. Alternativa considerada: testar via `TestClient` na camada de rota. Optou-se por testar o service diretamente (unit test, com repositório mockado) porque a causa raiz e o comportamento a corrigir estão inteiramente no service, e testes de rota exigiriam um banco de dados (PostgreSQL) não disponível no sandbox de execução (ver Harness Report).

## Risks / Trade-offs

- **[Risco] Nenhuma suíte de testes existente** → **Mitigação:** esta mudança adiciona a baseline mínima de `pytest` escopada ao service afetado, não uma suíte completa do projeto (fora do escopo desta correção).
- **[Risco] Consumidores da API que hoje tratam esse caso como 500 (retry automático, alertas de "erro de servidor")** → **Mitigação:** a mudança é estritamente uma correção de contrato (o dado já era rejeitado; muda-se apenas de "falha do servidor" para "requisição inválida do cliente"), que é o comportamento correto esperado de uma API REST; nenhum consumidor deveria depender de receber 500 para uma entrada inválida.

## Open Questions

**Devem nomes com números continuar sendo rejeitados no cadastro de clientes?**

- O alerta (SSAI-90) sugere, como hipótese não confirmada, "ajustar validação para permitir números ou normalizar a entrada" — ou seja, tornar `"João da Si4lva"` aceitável.
- O código não documenta por que essa regra existe (sem comentário, sem teste, sem menção em `README.md`). Não há evidência de que seja uma exigência de negócio deliberada ou um placeholder/defeito de digitação (a mensagem de erro atual sugere preocupação com "cadastro potencialmente inconsistente", o que indica intenção deliberada de proteção de qualidade de dado).
- **Opções:**
  1. **Manter a regra (recomendado)** — apenas corrigir o tipo de erro (400 em vez de 500). Menor raio de impacto; não remove uma validação de negócio existente sem justificativa clara para removê-la.
  2. **Remover a regra** — passaria a aceitar números em nomes, atendendo à recomendação do alerta. Maior raio de impacto: mudaria o que a API aceita como entrada válida, sem uma justificativa de negócio documentada.
- **Recomendação:** manter a opção 1 nesta mudança. Se o negócio decidir que nomes com números devem ser aceitos, isso deveria ser uma mudança à parte, com sua própria justificativa registrada.

Esta decisão fica para a APROVAÇÃO 1 (revisão de spec) — não resolvida silenciosamente aqui.
