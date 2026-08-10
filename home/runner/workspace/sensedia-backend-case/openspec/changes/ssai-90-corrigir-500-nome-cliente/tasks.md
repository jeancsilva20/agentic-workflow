# Tasks — Corrigir 500 em POST /clientes ao cadastrar nome com número

## 1. Correção do defeito

- [ ] 1.1 Em `app/services/cliente_service.py::criar_cliente`, trocar o `raise RuntimeError(...)` da validação de nome com número por `raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=...)`, reaproveitando o texto da mensagem de erro atual.
- [ ] 1.2 Confirmar manualmente (leitura de código) que `HTTPException` já está importada em `cliente_service.py` (está, usada pelas validações de CPF/e-mail) — nenhum novo import necessário.

## 2. Testes (baseline nova para o service)

- [ ] 2.1 Adicionar `pytest` e `httpx` como dependências de desenvolvimento (`requirements.txt` ou `requirements-dev.txt`, conforme convenção a definir na implementação).
- [ ] 2.2 Criar `tests/test_cliente_service.py` com um repositório de cliente mockado (`unittest.mock` ou fixture equivalente) cobrindo:
  - [ ] 2.2.1 Nome com número → `HTTPException` com `status_code == 400` (não mais `RuntimeError`).
  - [ ] 2.2.2 CPF duplicado → `HTTPException` com `status_code == 400` (comportamento inalterado, teste de regressão).
  - [ ] 2.2.3 E-mail duplicado → `HTTPException` com `status_code == 400` (comportamento inalterado, teste de regressão).
  - [ ] 2.2.4 Nome sem número, CPF e e-mail inéditos → criação bem-sucedida, sem exceção.

## 3. Verificação

- [ ] 3.1 Rodar `pytest tests/test_cliente_service.py` e confirmar que todos os casos passam.
- [ ] 3.2 Revisar o diff final contra `specs/cadastro-clientes/spec.md` — cada scenario do spec corresponde a um teste ou a uma verificação manual explícita.
