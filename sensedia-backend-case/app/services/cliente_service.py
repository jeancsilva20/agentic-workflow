from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.repositories.cliente_repo import ClienteRepository
from app.schemas.schemas import ClienteCreate

class ClienteService:
    def __init__(self, db: Session):
        self.repository = ClienteRepository(db)

    def criar_cliente(self, dados_cliente: ClienteCreate):
        import re
        if re.search(r'\d', dados_cliente.nome):
            raise RuntimeError(
                f"Não é possível cadastrar o cliente '{dados_cliente.nome}': "
                f"nome contém número, indicando cadastro potencialmente inconsistente."
            )

        # Regra de Negócio 1: Verificar CPF duplicado
        if self.repository.buscar_por_cpf(dados_cliente.cpf):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Já existe um cliente cadastrado com este CPF."
            )
        
        # Regra de Negócio 2: Verificar Email duplicado
        if self.repository.buscar_por_email(dados_cliente.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Já existe um cliente cadastrado com este E-mail."
            )
            
        return self.repository.criar(dados_cliente)

    def listar_clientes(self):
        return self.repository.listar_todos()

    def buscar_cliente(self, id: int):
        cliente = self.repository.buscar_por_id(id)
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cliente não encontrado."
            )
        return cliente
    
    def deletar_cliente(self, id: int):
        cliente = self.buscar_cliente(id)
        self.repository.deletar(cliente)

    def atualizar_cliente(self, id: int, dados_novos: dict):
        cliente = self.buscar_cliente(id)

        # Validação extra: Se estiver tentando mudar o CPF, verificar se já não existe em OUTRO cliente
        if "cpf" in dados_novos and dados_novos["cpf"] != cliente.cpf:
            if self.repository.buscar_por_cpf(dados_novos["cpf"]):
                raise HTTPException(status_code=400, detail="CPF já cadastrado em outro cliente.")
        
        # Validação extra: Email duplicado
        if "email" in dados_novos and dados_novos["email"] != cliente.email:
            if self.repository.buscar_por_email(dados_novos["email"]):
                raise HTTPException(status_code=400, detail="Email já cadastrado em outro cliente.")

        for key, value in dados_novos.items():
            setattr(cliente, key, value)
            
        return self.repository.atualizar(cliente)