"""Fila de jobs no Postgres (SKIP LOCKED). Acesso de sistema: não filtra por empresa.

Cada job carrega a sua `empresa_id`; os handlers montam o `Tenant` a partir dela.
"""

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from confere_api.models.job import Job


def pegar_job(session: Session) -> Job | None:
    """Reserva o próximo job pendente: vários workers nunca pegam o mesmo."""
    job = session.scalars(
        select(Job)
        .where(Job.status == "pendente", Job.executar_apos <= func.now())
        .order_by(Job.criado_em)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        session.rollback()
        return None
    job.status = "executando"
    job.iniciado_em = datetime.now(UTC)
    job.tentativas += 1
    session.commit()
    return job


def concluir(session: Session, job_id: uuid.UUID) -> None:
    session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="feito", terminado_em=func.now(), erro=None)
    )
    session.commit()


def falhar(session: Session, job: Job, erro: str, *, base_s: float, jitter_s: float) -> bool:
    """Devolve o job à fila com backoff ou o dá como falho. True se for falha definitiva."""
    definitiva = job.tentativas >= job.max_tentativas
    valores: dict[str, Any]
    if definitiva:
        valores = {"status": "falhou", "erro": erro, "terminado_em": func.now()}
    else:
        espera = (2**job.tentativas) * base_s + random.uniform(0, jitter_s)
        valores = {
            "status": "pendente",
            "erro": erro,
            "executar_apos": datetime.now(UTC) + timedelta(seconds=espera),
        }
    session.execute(update(Job).where(Job.id == job.id).values(**valores))
    session.commit()
    return definitiva


def liberar_jobs_presos(session: Session, minutos: int) -> int:
    """Jobs `executando` há mais de `minutos` (crash anterior) voltam para `pendente`."""
    limite = datetime.now(UTC) - timedelta(minutes=minutos)
    resultado = session.execute(
        update(Job)
        .where(Job.status == "executando", Job.iniciado_em < limite)
        .values(status="pendente")
    )
    session.commit()
    return int(getattr(resultado, "rowcount", 0) or 0)
