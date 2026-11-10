"""`python -m confere_api.worker --concorrencia 4`: sobe o worker."""

import argparse
import signal
import threading
from types import FrameType

import structlog
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from confere_api.db.session import PORTA_POOLER_TRANSACTION
from confere_api.settings import get_settings
from confere_api.worker import fila, handlers, runner

log = structlog.get_logger()
_ = handlers  # importar registra os handlers dos tipos de job


def criar_engine(concorrencia: int) -> Engine:
    url = get_settings().database_url_worker.get_secret_value()
    if make_url(url).port == PORTA_POOLER_TRANSACTION:
        raise SystemExit(
            "DATABASE_URL_WORKER aponta para o pooler em modo transaction (porta 6543). "
            "O worker precisa de conexão direta ou do pooler em modo session (porta 5432)."
        )
    return create_engine(url, pool_pre_ping=True, pool_size=concorrencia, max_overflow=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker do Confere")
    parser.add_argument("--concorrencia", type=int, default=4, help="threads em paralelo")
    argumentos = parser.parse_args()

    engine = criar_engine(argumentos.concorrencia)
    fabrica = sessionmaker(bind=engine, expire_on_commit=False)
    parar = threading.Event()

    def _sinal(_numero: int, _quadro: FrameType | None) -> None:
        log.info("worker_encerrando")
        parar.set()

    signal.signal(signal.SIGTERM, _sinal)
    signal.signal(signal.SIGINT, _sinal)

    with fabrica() as session:
        liberados = fila.liberar_jobs_presos(session, runner.config()["job_preso_apos_min"])
    if liberados:
        log.warning("jobs_presos_liberados", quantidade=liberados)

    threads = [
        threading.Thread(target=runner.laco, args=(fabrica, parar), name=f"worker-{i}")
        for i in range(argumentos.concorrencia)
    ]
    log.info("worker_iniciado", concorrencia=argumentos.concorrencia)
    for thread in threads:
        thread.start()
    while any(t.is_alive() for t in threads):
        for thread in threads:
            thread.join(timeout=0.5)  # volta curta: o SIGTERM/Ctrl+C é tratado entre as voltas
    log.info("worker_encerrado")


if __name__ == "__main__":
    main()
