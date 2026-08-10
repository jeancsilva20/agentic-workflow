from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.log_service import LogService
from app.schemas.schemas import LogErroResponse


router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("", response_model=List[LogErroResponse])
def buscar_logs(
    response: Response,
    data_inicio: Optional[datetime] = Query(None, description="Filtra logs a partir desta data (inclusive). Ex: 2025-01-01T00:00:00"),
    data_fim: Optional[datetime] = Query(None, description="Filtra logs até esta data (inclusive). Ex: 2025-01-31T23:59:59"),
    level: Optional[str] = Query(None, description="Filtra por level (ex: ERROR, WARNING)"),
    status_code: Optional[int] = Query(None, description="Filtra por status code HTTP (ex: 500, 404)"),
    limit: int = Query(5, ge=1, le=100, description="Número máximo de resultados (default: 5, max: 100)"),
    offset: int = Query(0, ge=0, description="Número de registros a pular para paginação (default: 0)"),
    db: Session = Depends(get_db),
):
    response.headers["Content-Encoding"] = "identity"
    response.headers["Cache-Control"] = "no-transform"
    service = LogService(db)
    return service.buscar_logs(
        data_inicio=data_inicio,
        data_fim=data_fim,
        level=level,
        status_code=status_code,
        limit=limit,
        offset=offset,
    )


@router.delete("", status_code=200)
def limpar_logs(
    db: Session = Depends(get_db),
):
    service = LogService(db)
    removed = service.limpar_logs()
    return {"status": "cleared", "records_removed": removed}
