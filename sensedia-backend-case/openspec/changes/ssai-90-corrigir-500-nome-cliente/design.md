## Context

`POST /api/v1/clientes` (`app/routers/cliente_router.py` → `app/services/cliente_service.py::criar_cliente`) valida, nesta ordem: (1) se o nome contém algum dígito, (2) se o CPF já existe, (3) se o e-mail já existe. As duas últimas levantam `HTTPException(status_code=400, ...)`, capturadas pelo handler `@app.exception_handler(HTTPException)` em `app/main.py`, que retorna 400 com `{"detail": ...}`. A primeira levanta `RuntimeError`, que não é uma `HTTPException` e por isso cai no handler genérico `@app.exception_handler(Exception)`, retornando sempre 500 com `{"detail": "Erro interno do servidor"}` — e sendo logado como `ERROR` (ver `openspec/changes/loguru-error-logging`), quando na verdade é um erro de entrada do cliente, não um erro interno do sistema.

O alerta SSAI-90 (gerado por monitoramento, não por um humano lendo o código) recomenda "ajustar a validação para permitir números ou normalizar o input". Essa recomendação é uma hipótese do alerta, não um requisito confirmado no código ou na descrição do card — ver regra de fundamentação nº 4. O código não documenta por que a regra "nome sem número" existe; não há teste, comentário ou histórico de commit explicando a motivação de negócio.

## Goals / Non-Goals

**Goals:**
- Eliminar o 500 indevido: erro de validação de entrada do cliente deve resultar em 4xx, nunca em 500.
- Manter o comportamento de negócio observável idêntico para os dois outros casos de validação (CPF duplicado, e-mail duplicado) — não são afetados por esta mudança.
- Adicionar cobertura de teste para o método que hoje não tem nenhuma (ver harness report).

**Non-Goals:**
- Decidir se a regra "nome não pode conter número" deve continuar existindo, ser flexibilizada ou normalizar a entrada — ver "Open Questions" abaixo.
- Alterar a resposta de sucesso ou o schema de `ClienteCreate`/`ClienteResponse`.
- Introduzir um framework de testes novo (usa-se `unittest` da biblioteca padrão; ver harness report — o projeto não declara `pytest` nem qualquer outro runner).

## Decisions

### 1. Corrigir o tipo de erro, não a regra de negócio
**Decisão:** trocar `raise RuntimeError(...)` por `raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=...)` no bloco de validação de nome, mantendo o texto da mensagem (adaptado para `detail`).

**Alternativas consideradas:**
- *Remover a validação de nome inteiramente*: resolveria o 500, mas descartaria uma regra de negócio existente sem evidência de que ela deveria deixar de existir — maior raio de impacto do que o necessário para corrigir o defeito relatado.
- *Normalizar o input (remover números do nome antes de salvar)*: mudaria silenciosamente o dado do cliente sem consentimento; é uma decisão de produto mais invasiva que a simples correção de status code, e não está evidenciada como necessária pelo card.
- *Capturar `RuntimeError` genericamente no handler global e mapear para 400*: mascararia outros `RuntimeError`s não relacionados (bugs reais) como erros de cliente 4xx, o que é pior para observabilidade.

**Rationale:** a correção mínima e evidenciada pelo próprio código (dois vizinhos usando `HTTPException` 400) é trocar o tipo de exceção. É reversível e não decide a questão de produto em aberto.

### 2. Testes com `unittest` da biblioteca padrão, sem novas dependências
**Decisão:** os testes usam `unittest.TestCase` e `unittest.mock.MagicMock` para simular o repositório (`ClienteRepository`), sem necessidade de banco de dados real nem de `pytest`/`httpx`.

**Rationale:** o harness confirmou que o projeto não tem suíte de testes, runner ou dependências de teste declaradas. A validação de nome ocorre antes de qualquer chamada ao repositório, então um teste unitário do `ClienteService` com um repositório mockado é suficiente e não exige infraestrutura (Postgres) indisponível neste sandbox. Evita adicionar uma dependência nova (`pytest`) quando a biblioteca padrão resolve o problema.

## Risks / Trade-offs

- **[A mensagem de erro atual expõe o nome completo do cliente no `detail` de uma resposta 400]** → Já era o comportamento antes desta mudança (a mensagem já citava o nome); manter o texto inalterado preserva o comportamento observável e evita introduzir uma mudança de comportamento não solicitada. Se a exposição do nome em mensagens de erro for uma preocupação, é um assunto separado deste card.
- **[Testes cobrem apenas a camada de serviço, não um teste de integração via `TestClient`]** → Aceitável dado que o defeito e a correção estão inteiramente na camada de serviço; um teste de integração exigiria banco de dados ou mocks adicionais no `Depends(get_db)`, fora do escopo mínimo desta correção.

## Open Questions

**A regra "nome do cliente não pode conter números" deve continuar existindo?**

- **Evidência a favor de manter:** é a única leitura defensável do código atual — a regra existe e é aplicada deliberadamente (não é um bug de digitação). Não há evidência de que ela esteja quebrando um fluxo legítimo de negócio; o exemplo do alerta (`'João da Si4lva'`) parece um dado de teste sintético, não um nome real reportado por um cliente.
- **Evidência a favor de remover/flexibilizar:** a recomendação do alerta de monitoramento sugere permitir números ou normalizar a entrada. No entanto, essa recomendação foi gerada sem leitura do código-fonte (é uma hipótese automática, não uma decisão de produto documentada) e nomes com números são raros no mundo real (sufixos como "2º", ou nomes de empresas/pessoas jurídicas se este cadastro um dia cobrir PJ) — não há indicação no repositório de que este cadastro cubra esse caso.
- **Recomendação:** manter a regra como está (rejeitar números no nome), apenas corrigindo o status code retornado. Alterar ou remover a regra é uma decisão de produto que este change não deve tomar; se a APROVAÇÃO 1 (revisão de spec) decidir flexibilizar a regra, é uma mudança separada e maior de escopo, não parte desta correção de bug.
