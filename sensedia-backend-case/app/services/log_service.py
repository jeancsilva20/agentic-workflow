from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.repositories.log_repo import LogRepository
from app.models.models import LogErro


class LogService:
    def __init__(self, db: Session):
        self.repository = LogRepository(db)

    def buscar_logs(
        self,
        data_inicio: Optional[datetime] = None,
        data_fim: Optional[datetime] = None,
        level: Optional[str] = None,
        status_code: Optional[int] = None,
        limit: int = 5,
        offset: int = 0,
    ) -> List[LogErro]:
        return self.repository.buscar_com_filtros(
            data_inicio=data_inicio,
            data_fim=data_fim,
            level=level,
            status_code=status_code,
            limit=limit,
            offset=offset,
        )

    def limpar_logs(self) -> int:
        return self.repository.remover_todos()
