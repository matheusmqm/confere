"""Identidade da requisição: de qual empresa e usuário ela vem."""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Tenant:
    empresa_id: uuid.UUID
    usuario_id: uuid.UUID | None
    papel: str  # ap | operacional | gestor
