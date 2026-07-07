import asyncio
import threading
import logging
from typing import Callable, Any
from concurrent.futures import Future

from app.sfera.sfera_instance import SferaInstance
import app.config as app_config
from app.exceptions import SferaConnectionError

logger = logging.getLogger(__name__)

class SferaWorker:
    def __init__(self):
        self._loop = None
        self._thread = None
        self._sfera: SferaInstance | None = None
        self._queue = None
        self.is_ready = False

    def _run(self):
        asyncio.set_event_loop(self._loop)
        try:
            import pythoncom
            pythoncom.CoInitialize()
            
            self._sfera = SferaInstance(app_config.settings.sfera)
            self._sfera.connect()
            
            self.is_ready = True
            logger.info("SferaWorker jest gotowy do przyjmowania zadań.")
            
            self._loop.run_until_complete(self._process_tasks())
        except Exception as e:
            logger.critical(f"Krytyczny błąd w SferaWorker podczas inicjalizacji: {e}", exc_info=True)
            self.is_ready = False
        finally:
            self.is_ready = False
            if self._sfera and self._sfera.is_connected:
                self._sfera.disconnect()
            pythoncom.CoUninitialize()
            logger.info("Wątek SferaWorker został zakończony.")
            self._loop.close()

    async def _process_tasks(self):
        """Pętla przetwarzająca zadania z kolejki."""
        while True:
            task = await self._queue.get()
            if task is None:
                logger.info("Otrzymano sygnał zatrzymania SferaWorker.")
                self._queue.task_done()
                break
            
            future, func, args, kwargs = task
            try:
                if not self.is_ready:
                    raise RuntimeError("SferaWorker nie jest gotowy do przetwarzania zadań.")
                
                result = func(*args, **kwargs)
                future.set_result(result)
            except SferaConnectionError as e:
                # Sfera utraciła sesję - próbujemy się ponownie połączyć
                logger.error(f"SferaConnectionError w workerze: {e}. Próbujem reconnect...")
                try:
                    self._sfera.reconnect()
                    self.is_ready = True
                    logger.info("Reconnect ze Sferą udał się. Ponawiam zadanie...")
                    result = func(*args, **kwargs)
                    future.set_result(result)
                except Exception as reconnect_err:
                    logger.error(f"Reconnect nieudany: {reconnect_err}", exc_info=True)
                    self.is_ready = False
                    future.set_exception(reconnect_err)
            except Exception as e:
                logger.error(f"Błąd podczas wykonywania zadania w SferaWorker: {e}", exc_info=True)
                future.set_exception(e)
            finally:
                self._queue.task_done()

    def start(self):
        """Uruchamia wątek workera w tle (nie blokuje)."""
        if self._thread and self._thread.is_alive(): 
            return
        logger.info("Uruchamianie SferaWorker w tle...")
        self._loop = asyncio.new_event_loop()
        # Tworzymy kolejkę w kontekście nowej pętli
        self._queue = asyncio.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Zatrzymuje wątek SferaWorker."""
        if not self._thread or not self._thread.is_alive():
            return
        logger.info("Zatrzymywanie SferaWorker...")
        # Wrzucamy None jako sentinel, aby wyjść z pętli _process_tasks
        self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
        self._thread.join(timeout=5)
        self._thread = None
        self._loop = None

    async def submit_task(self, func: Callable, *args, **kwargs) -> Any:
        """Wysyła zadanie do wykonania w wątku workera i czeka na wynik."""
        if not self.is_ready or self._loop is None:
            raise RuntimeError("SferaWorker nie działa lub nie jest zainicjalizowany.")
        future = Future()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (future, func, args, kwargs))
        return await asyncio.wrap_future(future)

sfera_worker = SferaWorker()