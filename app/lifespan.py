import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.sfera.sfera_worker import sfera_worker

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządza cyklem życia SferaWorkera."""
    logger.info("Inicjalizacja agenta i zlecanie uruchomienia SferaWorker...")
    sfera_worker.start()
    app.state.sfera_worker = sfera_worker
    yield
    logger.info("Zamykanie agenta...")
    sfera_worker.stop()