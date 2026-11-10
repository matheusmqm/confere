"""Loop do worker: pega job, despacha para o handler do tipo, trata retry, backoff e timeout."""

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoTimeout
from functools import lru_cache
from typing import Any

import structlog
import yaml
from sqlalchemy.orm import Session, sessionmaker

from confere_api.controllers.evento import EventoController
from confere_api.models.job import Job
from confere_api.settings import RAIZ
from confere_api.tenant import Tenant
from confere_api.worker import fila

log = structlog.get_logger()
CAMINHO_CONFIG = RAIZ / "config" / "worker.yaml"

Handler = Callable[[Session, Job], None]
HANDLERS: dict[str, Handler] = {}


class TimeoutEtapaError(Exception):
    """A etapa passou do tempo limite; conta como falha da tentativa."""


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    with open(CAMINHO_CONFIG, encoding="utf-8") as arquivo:
        dados: dict[str, Any] = yaml.safe_load(arquivo)
    return dados


def timeout_da_etapa(etapa: str) -> float:
    timeouts: dict[str, float] = config()["timeouts_s"]
    return float(timeouts.get(etapa, timeouts["padrao"]))


def handler(tipo: str) -> Callable[[Handler], Handler]:
    """Registra a função que processa jobs do `tipo`."""

    def registrar(funcao: Handler) -> Handler:
        HANDLERS[tipo] = funcao
        return funcao

    return registrar


def executar_com_timeout[T](funcao: Callable[[], T], segundos: float) -> T:
    """Roda `funcao` numa thread e espera no máximo `segundos`.

    Python não mata threads: ao estourar o tempo a thread segue até o fim em segundo plano, mas o
    worker já tratou a tentativa como falha.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    futuro = executor.submit(funcao)
    try:
        return futuro.result(timeout=segundos)
    except FuturoTimeout as erro:
        raise TimeoutEtapaError(f"tempo limite de {segundos:g} s excedido") from erro
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _documento_do_job(job: Job) -> uuid.UUID | None:
    bruto = (job.payload_json or {}).get("documento_id")
    try:
        return uuid.UUID(str(bruto)) if bruto else None
    except ValueError:
        return None


def executar_job(session: Session, job: Job) -> None:
    """Executa um job já reservado e registra o resultado (feito, nova tentativa ou falha)."""
    tipo, job_id = job.tipo, job.id
    funcao = HANDLERS.get(tipo)
    try:
        if funcao is None:
            raise LookupError(f"sem handler para o tipo de job {tipo!r}")
        funcao(session, job)
        fila.concluir(session, job_id)
        log.info("job_feito", job_id=str(job_id), tipo=tipo)
    except Exception as erro:
        session.rollback()
        mensagem = f"{type(erro).__name__}: {erro}"[:500]
        log.error(
            "job_falhou",
            job_id=str(job_id),
            tipo=tipo,
            tentativa=job.tentativas,
            erro=mensagem,
            exc_info=erro,
        )
        cfg = config()
        definitiva = fila.falhar(
            session, job, mensagem, base_s=cfg["backoff_base_s"], jitter_s=cfg["backoff_jitter_s"]
        )
        if definitiva:
            tenant = Tenant(job.empresa_id, None, "gestor")
            EventoController(session, tenant).registrar(
                "erro",
                "erro",
                "Não foi possível processar o documento após várias tentativas.",
                documento_id=_documento_do_job(job),
                job_id=job_id,
                dados={"erro": mensagem},
            )
            session.commit()


def laco(fabrica: sessionmaker[Session], parar: threading.Event) -> None:
    """Uma thread do worker: sessão própria, termina o job atual e sai quando `parar` é acionado."""
    intervalo = float(config()["intervalo_sem_job_s"])
    while not parar.is_set():
        with fabrica() as session:
            job = fila.pegar_job(session)
            if job is None:
                parar.wait(intervalo)
                continue
            executar_job(session, job)
