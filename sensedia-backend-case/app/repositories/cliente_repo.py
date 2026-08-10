from sqlalchemy.orm import Session
from app.models.models import Cliente
from app.schemas.schemas import ClienteCreate


class ClienteRepository:
    def __init__(self, db: Session):
        self.db = db

    def criar(self, cliente: ClienteCreate):
        db_cliente = Cliente(
            nome=cliente.nome,
            email=cliente.email,
            cpf=cliente.cpf
        )
        # 2. Adiciona na sessão
        self.db.add(db_cliente)
        # 3. Confirma a transação (Commit)
        self.db.commit()
        # 4. Atualiza o objeto com o ID gerado pelo banco
        self.db.refresh(db_cliente)
        return db_cliente
    
    def deletar(self, cliente: Cliente):
        self.db.delete(cliente)
        self.db.commit()

    def atualizar(self, db_cliente: Cliente):
        self.db.commit()
        self.db.refresh(db_cliente)
        return db_cliente

    def listar_todos(self):
        return self.db.query(Cliente).all()

    def buscar_por_id(self, id: int):
        return self.db.query(Cliente).filter(Cliente.id == id).first()
    
    def buscar_por_cpf(self, cpf: str):
        return self.db.query(Cliente).filter(Cliente.cpf == cpf).first()

    def buscar_por_email(self, email: str):
        return self.db.query(Cliente).filter(Cliente.email == email).first()