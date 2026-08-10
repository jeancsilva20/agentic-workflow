from pydantic import BaseModel, EmailStr, validator
from datetime import datetime, date
from typing import List, Optional


class ClienteBase(BaseModel):
    nome: str
    email: EmailStr
    cpf: str

class ClienteCreate(ClienteBase):
    pass

class ClienteResponse(ClienteBase):
    id: int

    class Config:
        from_attributes = True


class ApoliceBase(BaseModel):
    numero: str
    valor: float
    data_inicio: datetime
    data_fim: datetime
    cliente_id: int

class ApoliceCreate(ApoliceBase):
    pass

class ApoliceResponse(ApoliceBase):
    id: int
    
    class Config:
        from_attributes = True


class LogErroResponse(BaseModel):
    id: int
    timestamp: datetime
    level: str
    message: str
    correlation_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    status_code: Optional[int] = None
    traceback: Optional[str] = None
    module: Optional[str] = None

    class Config:
        from_attributes = True