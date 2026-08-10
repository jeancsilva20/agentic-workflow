from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.services.apolice_service import ApoliceService
from app.schemas.schemas import ApoliceCreate, ApoliceResponse

router = APIRouter(prefix="/apolices", tags=["Apólices"])

@router.post("", response_model=ApoliceResponse, status_code=201)
def criar_apolice(apolice: ApoliceCreate, db: Session = Depends(get_db)):
    service = ApoliceService(db)
    return service.criar_apolice(apolice)

@router.get("", response_model=List[ApoliceResponse])
def listar_apolices(db: Session = Depends(get_db)):
    service = ApoliceService(db)
    return service.listar_apolices()

@router.get("/{id}", response_model=ApoliceResponse)
def buscar_apolice(id: int, db: Session = Depends(get_db)):
    service = ApoliceService(db)
    return service.buscar_apolice(id)


@router.delete("/{id}", status_code=204)
def deletar_apolice(id: int, db: Session = Depends(get_db)):
    service = ApoliceService(db)
    service.deletar_apolice(id)
    # Retorna vazio (204 No Content) conforme padrão REST


@router.put("/{id}", response_model=ApoliceResponse)
def atualizar_apolice_completa(id: int, apolice: ApoliceCreate, db: Session = Depends(get_db)):
    service = ApoliceService(db)
    # No PUT, passamos todos os dados do objeto
    return service.atualizar_apolice(id, apolice.dict())


@router.patch("/{id}", response_model=ApoliceResponse)
def atualizar_apolice_parcial(id: int, apolice: dict, db: Session = Depends(get_db)):
    service = ApoliceService(db)
    return service.atualizar_apolice(id, apolice)