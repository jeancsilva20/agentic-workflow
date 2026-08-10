from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.models import LogErro


class LogRepository:
    def __init__(self, db: Session):
        self.db = db

    def buscar_com_filtros(
        self,
        data_inicio: Optional[datetime] = None,
        data_fim: Optional[datetime] = None,
        level: Optional[str] = None,
        status_code: Optional[int] = None,
        limit: int = 5,
        offset: int = 0,
    ) -> List[LogErro]:
        query = self.db.query(LogErro)

        if data_inicio is not None:
            query = query.filter(LogErro.timestamp >= data_inicio)

        if data_fim is not None:
            query = query.filter(LogErro.timestamp <= data_fim)

        if level is not None:
            query = query.filter(LogErro.level == level)

        if status_code is not None:
            query = query.filter(LogErro.status_code == status_code)

        return query.order_by(LogErro.timestamp.desc()).offset(offset).limit(limit).all()

    def criar(self, log: LogErro) -> LogErro:
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def remover_todos(self) -> int:
        count = self.db.query(LogErro).count()
        self.db.query(LogErro).delete()
        self.db.commit()
        return count
