from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.repositories.apolice_repo import ApoliceRepository
from app.repositories.cliente_repo import ClienteRepository
from app.schemas.schemas import ApoliceCreate

class ApoliceService:
    def __init__(self, db: Session):
        self.repository = ApoliceRepository(db)
        self.cliente_repo = ClienteRepository(db)

    def criar_apolice(self, dados: ApoliceCreate):
        # Regra: Verificar se cliente existe
        cliente = self.cliente_repo.buscar_por_id(dados.cliente_id)
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado para vincular a apólice.")
        
        return self.repository.criar(dados)

    def listar_apolices(self):
        return self.repository.listar_todos()

    def buscar_apolice(self, id: int):
        apolice = self.repository.buscar_por_id(id)
        if not apolice:
            raise HTTPException(status_code=404, detail="Apólice não encontrada.")
        return apolice

    def deletar_apolice(self, id: int):
        apolice = self.buscar_apolice(id) # Reutiliza o método que já checa 404
        self.repository.deletar(apolice)

        return {"message": "Apólice deletada com sucesso"}

    def atualizar_apolice(self, id: int, dados_novos: dict):
        apolice = self.buscar_apolice(id)
        
        # Atualiza apenas os campos enviados (Lógica para PATCH e PUT)
        for key, value in dados_novos.items():
            setattr(apolice, key, value)
            
        return self.repository.atualizar(apolice)