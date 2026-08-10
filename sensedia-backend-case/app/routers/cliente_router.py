from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.services.cliente_service import ClienteService
from app.schemas.schemas import ClienteCreate, ClienteResponse


router = APIRouter(prefix="/clientes", tags=["Clientes"])

@router.post("", response_model=ClienteResponse, status_code=status.HTTP_201_CREATED)
def criar_cliente(cliente: ClienteCreate, db: Session = Depends(get_db)):
    service = ClienteService(db)
    return service.criar_cliente(cliente)

@router.get("", response_model=List[ClienteResponse])
def listar_clientes(db: Session = Depends(get_db)):
    service = ClienteService(db)
    return service.listar_clientes()

@router.get("/{id}", response_model=ClienteResponse)
def buscar_cliente(id: int, db: Session = Depends(get_db)):
    service = ClienteService(db)
    return service.buscar_cliente(id)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_cliente(id: int, db: Session = Depends(get_db)):
    service = ClienteService(db)
    service.deletar_cliente(id)

@router.put("/{id}", response_model=ClienteResponse)
def atualizar_cliente_completo(id: int, cliente: ClienteCreate, db: Session = Depends(get_db)):
    service = ClienteService(db)
    # Transforma o schema em dict para passar pro service
    return service.atualizar_cliente(id, cliente.dict())

@router.patch("/{id}", response_model=ClienteResponse)
def atualizar_cliente_parcial(id: int, cliente: dict, db: Session = Depends(get_db)):
    service = ClienteService(db)
    return service.atualizar_cliente(id, cliente)