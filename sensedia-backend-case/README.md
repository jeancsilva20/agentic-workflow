# Case Backend Python - Sensedia API Gateway

Este repositório contém a solução para o case técnico de Backend em Python com integração ao Sensedia API Gateway. O projeto consiste em uma API RESTful para a gestão de Clientes e Apólices, com persistência em banco de dados relacional e protegida por interceptors de segurança.

## 🔗 Links do Projeto

* **API no Render (Backend):** https://sensedia-api-backend.onrender.com/docs
* **API Gateway (Sensedia):** https://api-consulting.sensedia.com/cli-2/api/v1
* **Apresentação de Slides:** https://docs.google.com/presentation/d/1wRWUZdBTKiuwx_Q2aFsua5uJ8npFPrT5LpypHLGEJdc/edit?usp=sharing

---

## 🛠️ Tecnologias e Arquitetura

O projeto foi construído focando em performance, tipagem forte e boas práticas de engenharia de software:

* **Linguagem:** Python 3.x
* **Framework:** FastAPI (Escolhido por gerar documentação OpenAPI 3.0 nativamente e possuir excelente performance)
* **Banco de Dados:** PostgreSQL
* **ORM & Migrations:** SQLAlchemy + Alembic
* **API Gateway:** Sensedia API Manager
* **Deploy:** Render

A arquitetura segue o padrão de camadas (Routers, Services, Repositories, Schemas) garantindo a separação de responsabilidades e facilitando a manutenção.

---

## 🔒 Sensedia API Gateway (Segurança e Tráfego)

Para cumprir os requisitos de governança e segurança, a API não deve ser acessada diretamente. Ela está publicada atrás do Sensedia API Gateway com os seguintes Interceptors configurados:

1. **Client ID Validation:** Autenticação obrigatória via header para todas as requisições.
2. **Rate Limit:** Controle de tráfego configurado (bloqueio temporal com erro 429 em caso de abuso).
3. **Log Tracing:** Registro de payload e headers para auditoria.

---

## 🧪 Como Testar a API (Collection Postman)

Para facilitar a avaliação, disponibilizei uma Collection completa do Postman com todas as rotas (CRUD de Clientes e Apólices) já configuradas.

1. Baixe o arquivo `sensedia_case_collection.json` que está na raiz deste repositório.
2. Abra o Postman e clique em **Import** (canto superior esquerdo).
3. Arraste o arquivo `.json` para dentro do Postman.
4. **Importante - Credencial de Acesso:** Para que as requisições passem pelo Gateway, é necessário informar o `client_id` nas variáveis da Collection. 
   * Vá na aba **Variables** da Collection importada.
   * Na variável `client_id`, insira o token: `332d2adb-210a-46f4-ab72-fcb120e3ca68`
   * Salve e comece a testar!

---

## 💻 Como rodar o projeto localmente

Se desejar rodar a aplicação em sua própria máquina em vez de usar a versão em nuvem:

1. Clone o repositório:
   ```bash
   git clone https://github.com/guilhermeallen/sensedia-backend-case.git


2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv venv 
   source venv/bin/activate  # No Windows use: venv\Scripts\activate

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt

4. Configure as variáveis de ambiente (crie um arquivo .env baseado no .env.example). 

5. Execute as migrations do banco de dados:
   ```bash
   alembic upgrade head

6. Inicie o servidor:
   ```bash
   uvicorn app.main:app --reload
