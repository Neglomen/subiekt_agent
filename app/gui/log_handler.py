import logging
import queue

class QueueLogHandler(logging.Handler):
    """
    Log handler that redirects log records to a queue.Queue.
    This is used to transfer log messages safely from background threads
    (FastAPI, SferaWorker, Cloudflare Tunnel) to the tkinter main thread.
    """
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            # Format the message before putting it into the queue
            msg = self.format(record)
            self.log_queue.put((record.levelname, msg))
        except Exception:
            self.handleError(record)
