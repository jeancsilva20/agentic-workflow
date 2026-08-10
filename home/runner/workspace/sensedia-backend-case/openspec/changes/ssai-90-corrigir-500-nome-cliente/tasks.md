## 1. Corrigir o defeito

- [ ] 1.1 Em `app/services/cliente_service.py::criar_cliente`, trocar `raise RuntimeError(...)` por `raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=...)` no bloco que valida números no nome, seguindo o mesmo padrão das validações de CPF e e-mail duplicados na mesma função.
- [ ] 1.2 Manter o texto da mensagem de validação (adaptado para o campo `detail` de `HTTPException`).

## 2. Testes

- [ ] 2.1 Criar `tests/services/test_cliente_service.py` usando `unittest` (biblioteca padrão) com o repositório mockado via `unittest.mock.MagicMock`.
- [ ] 2.2 Teste: nome contendo dígito levanta `HTTPException` com `status_code == 400` (não `RuntimeError`, não 500) e o repositório não é chamado.
- [ ] 2.3 Teste (regressão): CPF duplicado ainda levanta `HTTPException` com `status_code == 400`.
- [ ] 2.4 Teste (regressão): e-mail duplicado ainda levanta `HTTPException` com `status_code == 400`.
- [ ] 2.5 Teste (regressão): criação com nome, CPF e e-mail válidos/inéditos chama `repository.criar` e retorna o cliente criado.
- [ ] 2.6 Executar `python -m unittest discover -s tests -p "test_*.py" -v` e confirmar que todos os testes passam.

## 3. Verificação

- [ ] 3.1 Rodar `openspec-verify` contra este change antes de solicitar code review, confirmando que a implementação cobre todos os requirements/scenarios do spec sem achados CRITICAL pendentes.
