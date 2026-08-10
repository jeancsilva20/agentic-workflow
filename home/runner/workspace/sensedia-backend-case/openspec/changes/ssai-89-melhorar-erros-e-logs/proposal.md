## Why

SSAI-89 pede para melhorar os cenários de erro e os logs da API "para facilitar análises", e priorizar bibliotecas nativas do Python para garantir qualidade de código. Lendo o código (não apenas a intenção do card): existem hoje três lacunas concretas nesses cenários — (1) `ClienteService.criar_cliente` levanta `RuntimeError` puro para a regra "nome com número", que escapa do handler de `HTTPException` e vira um 500 indiferenciado, inconsistente com toda regra de negócio irmã no mesmo arquivo e no `ApoliceService`, que usam `HTTPException`; (2) erros de validação de payload (422, `RequestValidationError` do FastAPI) não passam pelos handlers customizados da aplicação, então nunca são persistidos na tabela `logs_erro` nem aparecem no console formatado — ficam invisíveis para quem for analisar erros depois; (3) o próprio sink do Loguru (`app/core/logging_config.py`) usa `print()` bruto para reportar suas próprias falhas de escrita, fora do sistema de logging que ele mesmo implementa. Nenhuma dessas três lacunas depende de decidir algo sobre regra de produto — são inconsistências confirmadas contra o próprio padrão do repositório.

Separadamente, o card pede explicitamente para usar bibliotecas nativas do Python. A stack atual de logging é 100% baseada em `loguru`, uma dependência de terceiros. Essa é uma decisão de arquitetura maior (não uma correção pontual) e está registrada como decisão aberta em `design.md` para a aprovação da spec decidir o alcance da migração, em vez de ser resolvida aqui unilateralmente.

## What Changes

- Corrigir `ClienteService.criar_cliente`: a regra "nome contém número" passa a levantar `HTTPException(400)` em vez de `RuntimeError`, alinhando com as demais regras de negócio do mesmo arquivo e do `ApoliceService`.
- Adicionar um exception handler para `RequestValidationError` (422) em `app/main.py`, para que erros de validação de payload também sejam logados (console + Postgres) com `correlation_id`, `endpoint`, `method`, `status_code` e `module`, do mesmo modo que os erros 4xx/5xx já tratados.
- Substituir os `print()` de fallback dentro de `postgres_sink` (`app/core/logging_config.py`) por uma chamada ao logger que não reentra no próprio sink Postgres (evitando recursão), preservando a saída no console/stderr em caso de falha do sink.
- **[Decisão aberta — ver `design.md`]** Avaliar a migração do sistema de logging de `loguru` (terceiros) para o módulo nativo `logging` do Python, preservando as capacidades atuais (sink de console, sink de Postgres, correlation_id via contexto). O alcance exato (migração completa vs. parcial) fica para APROVAÇÃO 1 decidir.
- **[Decisão aberta — ver `design.md`]** Escrever os testes novos deste change usando `unittest` (biblioteca nativa) em vez de `pytest`, coerente com o pedido do card de priorizar bibliotecas nativas, já que o projeto não tem nenhum test runner declarado hoje.

## Capabilities

### New Capabilities
- `error-logging`: cobre a persistência e a formatação de logs de erro (4xx/5xx/422) da API, incluindo consistência do tipo de exceção levantada pelas regras de negócio e o comportamento do sink de logging em caso de falha. Não existe ainda um `openspec/specs/error-logging/spec.md` canônico — o diretório `openspec/changes/loguru-error-logging/` já implementado no código (commits `9493384`, `6751930`, `297f5a1`) nunca foi arquivado; este change assume esse comportamento como base e adiciona os requisitos novos/corrigidos sobre ele.

### Modified Capabilities
<!-- Nenhuma capability canônica existe em openspec/specs/ ainda; nada a modificar formalmente. -->

## Impact

- **Arquivos afetados:**
  - `app/services/cliente_service.py` — trocar `RuntimeError` por `HTTPException(400)`
  - `app/main.py` — adicionar handler de `RequestValidationError`
  - `app/core/logging_config.py` — remover `print()` de fallback do sink, decisão de migração de logging
  - `requirements.txt` — dependente da decisão de migração (remoção condicional de `loguru`)
  - Novos arquivos de teste (`tests/`) — dependente da decisão de framework de teste
- **APIs:** nenhuma rota nova; comportamento de resposta HTTP não muda (mesmos status codes), apenas o que é logado/persistido e o tipo interno de exceção.
- **Banco de dados:** nenhuma alteração de schema.
- **Dependências:** possível remoção de `loguru` de `requirements.txt`, dependente da decisão em `design.md`.
- **Compatibilidade:** sem breaking changes de contrato HTTP; comportamento de logging interno muda.
