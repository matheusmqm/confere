"""CONTROLLER: eventos do pipeline (trilha de auditoria e fonte do SSE)."""

import uuid
from collections.abc import Sequence
from typing import Any

from confere_api.controllers.base import RepositorioBase
from confere_api.models.evento import Evento


class EventoController(RepositorioBase):
    def registrar(
        self,
        etapa: str,
        status: str,
        mensagem: str,
        *,
        documento_id: uuid.UUID | None = None,
        job_id: uuid.UUID | None = None,
        dados: dict[str, Any] | None = None,
    ) -> Evento:
        evento = Evento(
            etapa=etapa,
            status=status,
            mensagem=mensagem,
            documento_id=documento_id,
            job_id=job_id,
            dados_json=dados,
        )
        self.adicionar(evento)
        self.db.flush()
        return evento

    def ultimo_id(self) -> int:
        """Maior id de evento da empresa (0 se não há nenhum)."""
        ultimo = self.db.scalars(self._q(Evento).order_by(Evento.id.desc()).limit(1)).first()
        return ultimo.id if ultimo else 0

    def depois_de(self, ultimo_id: int, limite: int = 200) -> Sequence[Evento]:
        """Eventos da empresa com id maior que `ultimo_id` (para o SSE)."""
        consulta = self._q(Evento).where(Evento.id > ultimo_id).order_by(Evento.id).limit(limite)
        return self.db.scalars(consulta).all()
