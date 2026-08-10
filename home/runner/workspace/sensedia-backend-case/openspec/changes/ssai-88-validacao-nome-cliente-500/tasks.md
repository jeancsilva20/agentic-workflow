## 1. Correção do defeito

- [ ] 1.1 Em `app/services/cliente_service.py::criar_cliente`, substituir o `raise RuntimeError(...)` da verificação "nome contém número" por `raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=...)`, preservando o texto da mensagem.
- [ ] 1.2 Confirmar, por leitura do código, que nenhum outro ponto do serviço (`atualizar_cliente`, `ApoliceService`) precisa do mesmo ajuste — a validação de nome hoje só existe em `criar_cliente`.

## 2. Testes

- [ ] 2.1 Criar `tests/services/test_cliente_service.py` (ou local equivalente ao layout do projeto) usando `unittest`, com um `ClienteRepository` fake/mock injetado no `ClienteService`.
- [ ] 2.2 Teste: nome com número levanta `HTTPException` com `status_code == 400` (não `RuntimeError`, não 500).
- [ ] 2.3 Teste: CPF duplicado levanta `HTTPException` com `status_code == 400`.
- [ ] 2.4 Teste: email duplicado levanta `HTTPException` com `status_code == 400`.
- [ ] 2.5 Teste: cadastro válido (nome sem número, CPF e email inéditos) chama `repository.criar` e retorna o cliente criado.

## 3. Verificação

- [ ] 3.1 Rodar `python -m unittest` (ou o caminho específico do novo módulo de teste) e confirmar que os 4 cenários passam.
- [ ] 3.2 Revisar o diff final contra `specs/cadastro-clientes/spec.md` — cada scenario do spec corresponde a um teste ou a uma verificação manual documentada.
