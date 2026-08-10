from sqlalchemy.orm import Session
from app.models.models import Apolice
from app.schemas.schemas import ApoliceCreate

class ApoliceRepository:
    def __init__(self, db: Session):
        self.db = db

    def criar(self, apolice: ApoliceCreate):
        db_apolice = Apolice(
            numero=apolice.numero,
            valor=apolice.valor,
            data_inicio=apolice.data_inicio,
            data_fim=apolice.data_fim,
            cliente_id=apolice.cliente_id
        )
        self.db.add(db_apolice)
        self.db.commit()
        self.db.refresh(db_apolice)
        return db_apolice

    def listar_todos(self):
        return self.db.query(Apolice).all()

    def buscar_por_id(self, id: int):
        return self.db.query(Apolice).filter(Apolice.id == id).first()

    def deletar(self, apolice: Apolice):
        self.db.delete(apolice)
        self.db.commit()

    def atualizar(self, db_apolice: Apolice):
        self.db.commit()
        self.db.refresh(db_apolice)
        return db_apolice