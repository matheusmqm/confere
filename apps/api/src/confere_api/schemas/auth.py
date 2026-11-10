"""SCHEMAS: login de demo."""

import uuid

from pydantic import BaseModel, ConfigDict


class UsuarioSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    email: str
    papel: str


class EmpresaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str


class EuSaida(BaseModel):
    usuario: UsuarioSaida
    empresa: EmpresaSaida
