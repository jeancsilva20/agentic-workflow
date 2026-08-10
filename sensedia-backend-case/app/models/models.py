from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime


Base = declarative_base()


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    cpf = Column(String(14), unique=True, nullable=False)
    apolices = relationship("Apolice", back_populates="cliente", cascade="all, delete-orphan")


class Apolice(Base):
    __tablename__ = "apolices"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String(50), unique=True, nullable=False)
    valor = Column(Float, nullable=False)
    data_inicio = Column(DateTime, default=datetime.now)
    data_fim = Column(DateTime, nullable=False)

    # Chave Estrangeira (ForeignKey) - O link com o Cliente
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    
    # Relacionamento inverso (para acessar apolice.cliente)
    cliente = relationship("Cliente", back_populates="apolices")


class LogErro(Base):
    __tablename__ = "logs_erro"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    correlation_id = Column(String(36), nullable=True)
    endpoint = Column(String(255), nullable=True)
    method = Column(String(10), nullable=True)
    status_code = Column(Integer, nullable=True)
    traceback = Column(Text, nullable=True)
    module = Column(String(255), nullable=True)

