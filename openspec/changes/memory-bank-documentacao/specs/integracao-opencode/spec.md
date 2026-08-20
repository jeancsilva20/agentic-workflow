## ADDED Requirements

### Requirement: opencode.json com instructions
O repositório SHALL conter um arquivo `opencode.json` na raiz com o campo `instructions` listando os arquivos do memory bank, para que o OpenCode os carregue automaticamente no contexto.

#### Scenario: opencode.json criado
- **WHEN** a mudança é aplicada
- **THEN** existe um `opencode.json` válido na raiz com o campo `instructions` apontando para os arquivos do memory bank

#### Scenario: Instructions listam os arquivos
- **WHEN** um leitor abre `opencode.json`
- **THEN** encontra no campo `instructions` as referências aos arquivos de contexto global e aos documentos de agentes/camadas do memory bank

### Requirement: AGENTS.md com índice do memory bank
O arquivo `AGENTS.md` SHALL ser atualizado com uma seção/índice apontando para o memory bank, para que humanos e agentes descubram a documentação.

#### Scenario: Índice adicionado ao AGENTS.md
- **WHEN** a mudança é aplicada
- **THEN** `AGENTS.md` contém uma seção apontando para `memory-bank/` e descrevendo sua finalidade

### Requirement: Validade do opencode.json
O `opencode.json` SHALL ser válido segundo o schema do OpenCode, sem quebrar a configuração existente do projeto.

#### Scenario: JSON válido
- **WHEN** o `opencode.json` é validado
- **THEN** é um JSON bem-formado e compatível com o schema do OpenCode
