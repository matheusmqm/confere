"""CONTROLLER: fila de jobs (lado de quem enfileira; quem consome é `worker/fila.py`)."""

import uuid
from typing import Any

from confere_api.controllers.base import RepositorioBase
from confere_api.models.job import Job


class JobController(RepositorioBase):
    def enfileirar(self, tipo: str, payload: dict[str, Any]) -> Job:
        job = Job(tipo=tipo, payload_json=payload)
        self.adicionar(job)
        self.db.flush()
        return job

    def reprocessar_documento(self, documento_id: uuid.UUID, a_partir_de: str = "casado") -> Job:
        """Reprocessa o documento reaproveitando a extração (sem chamar o LLM de extração)."""
        return self.enfileirar(
            "reprocessar", {"documento_id": str(documento_id), "a_partir_de": a_partir_de}
        )
