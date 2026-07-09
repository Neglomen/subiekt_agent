"""
app/gui_api.py — Trasy FastAPI dla panelu webowego (GUI).
Zarejestrowane pod prefiksem /gui/* i /ws/logs.
"""
import asyncio
import json
import logging
import time
import threading
from collections import deque
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import app.config as app_config
from app.config import SferaSettings, MappingSettings, save_sfera_settings, BASE_DIR
from app.services.config_service import ConfigService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# STATISTICS STORE
# ---------------------------------------------------------------------------

class AgentStats:
    """Thread-safe in-memory store for real-time agent statistics."""
    def __init__(self):
        self._lock = threading.Lock()
        # Rolling window of (timestamp, latency_ms) tuples
        self._requests: deque = deque(maxlen=5000)
        # Rolling window of last 20 request counts per "tick"
        self._history: deque = deque(maxlen=20)
        self._history_last_tick = time.time()

        # Document counters (reset at midnight)
        self._day = date.today()
        self._invoices_today = 0
        self._products_today: Set[str] = set()
        self._bulk_stock_queries = 0

        # Status of last operations
        self.last_invoice_number: str = ""
        self.last_invoice_status: str = "Brak"
        self.last_invoice_time: str = ""
        self.last_stock_status: str = "Brak"
        self.last_stock_time: str = ""

    def _check_day_rollover(self):
        today = date.today()
        if today != self._day:
            self._day = today
            self._invoices_today = 0
            self._products_today = set()
            self._bulk_stock_queries = 0

    def record_request(self, latency_ms: float):
        with self._lock:
            self._check_day_rollover()
            self._requests.append((time.time(), latency_ms))

    def record_invoice(self, doc_number: str, success: bool):
        with self._lock:
            self._check_day_rollover()
            self._invoices_today += 1
            self.last_invoice_number = doc_number
            self.last_invoice_status = "OK" if success else "ERROR"
            self.last_invoice_time = datetime.now().strftime("%H:%M:%S")

    def record_bulk_stock(self, symbols: List[str], success: bool):
        with self._lock:
            self._check_day_rollover()
            self._bulk_stock_queries += 1
            for s in symbols:
                self._products_today.add(s)
            self.last_stock_status = "OK" if success else "ERROR"
            self.last_stock_time = datetime.now().strftime("%H:%M:%S")

    def get_snapshot(self) -> dict:
        with self._lock:
            self._check_day_rollover()
            now = time.time()
            cutoff = now - 60
            recent = [r for r in self._requests if r[0] >= cutoff]

            # Update history ticker every 3s
            if now - self._history_last_tick >= 3:
                self._history.append(len(recent))
                self._history_last_tick = now

            avg_latency = round(sum(r[1] for r in recent) / len(recent), 1) if recent else 0

            return {
                "requests_last_60s": len(recent),
                "request_history": list(self._history),
                "avg_latency_ms": avg_latency,
                "products_checked_today": len(self._products_today),
                "bulk_stock_queries": self._bulk_stock_queries,
                "invoices_created_today": self._invoices_today,
                "last_invoice_number": self.last_invoice_number,
                "last_invoice_status": self.last_invoice_status,
                "last_invoice_time": self.last_invoice_time,
                "last_stock_status": self.last_stock_status,
                "last_stock_time": self.last_stock_time,
                "ksef_enabled": app_config.settings.mappings.ksef_enabled,
                "fiscalization_enabled": app_config.settings.mappings.fiscalization_enabled,
            }


# Global stats instance - imported and used by main.py middleware
agent_stats = AgentStats()


# ---------------------------------------------------------------------------
# LOG BUFFER (ring buffer for WS broadcast)
# ---------------------------------------------------------------------------

class LogBroadcaster:
    """Collects log messages and broadcasts to connected WebSocket clients."""

    def __init__(self, maxlen: int = 200):
        self._buffer: deque = deque(maxlen=maxlen)
        self._clients: List[WebSocket] = []
        self._lock = threading.Lock()

    def add(self, message: str):
        with self._lock:
            self._buffer.append(message)
        # Async broadcast in a fire-and-forget fashion
        asyncio.create_task(self._broadcast_one(message))

    def get_backlog(self) -> List[str]:
        with self._lock:
            return list(self._buffer)

    async def connect(self, ws: WebSocket):
        await ws.accept()
        with self._lock:
            self._clients.append(ws)
        # Send backlog immediately so the terminal isn't empty
        backlog = self.get_backlog()
        if backlog:
            try:
                await ws.send_text(json.dumps(backlog))
            except Exception:
                pass

    async def disconnect(self, ws: WebSocket):
        with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)

    async def _broadcast_one(self, message: str):
        disconnected = []
        clients_copy = []
        with self._lock:
            clients_copy = list(self._clients)
        for ws in clients_copy:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            await self.disconnect(ws)


# Global broadcaster — main.py installs a QueueLogHandler that feeds into this
log_broadcaster = LogBroadcaster(maxlen=200)


class BroadcastLogHandler(logging.Handler):
    """Logging handler that feeds records to the WebSocket broadcaster."""

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            # We can't await from a sync context, so we schedule via asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(log_broadcaster._buffer.append, msg)
                # Broadcast asynchronously — create task if loop is running
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(log_broadcaster._broadcast_one(msg))
                )
            except RuntimeError:
                # No running loop (e.g. startup) — just buffer
                log_broadcaster._buffer.append(msg)
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS FOR GUI
# ---------------------------------------------------------------------------

class GUIConfigPayload(BaseModel):
    db_server_name: str
    db_name: str
    sfera_operator: str
    sfera_operator_password: str
    agent_api_key: str
    agent_port: int = 8000
    cloudflare_enabled: bool = False
    cloudflare_token: str = ""
    cloudflare_custom_url: str = ""
    autostart_enabled: bool = False
    # Ngrok tunnel (alternatywa dla Cloudflare)
    ngrok_enabled: bool = False
    ngrok_authtoken: str = ""
    ngrok_domain: str = ""
    # Mapping settings
    ksef_enabled: bool = False
    fiscalization_enabled: bool = False
    fiscal_printer_id: int = 0
    distributed_costs_keywords: List[str] = []


# ---------------------------------------------------------------------------
# ROUTER
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/gui", tags=["GUI"])
ws_router = APIRouter(tags=["GUI WebSocket"])


@router.get("/status")
async def gui_status():
    """Returns current agent, Sfera, and Cloudflare tunnel status."""
    from app.sfera.sfera_worker import sfera_worker

    sfera_connected = bool(
        sfera_worker.is_ready
        and sfera_worker._sfera
        and sfera_worker._sfera.is_connected
    )

    # Try to find the cloudflare manager if tray is active
    cf_connected = False
    cf_url = ""
    ngrok_connected = False
    ngrok_url = ""
    try:
        from app.gui.tray import _tray_instance
        if _tray_instance and _tray_instance.agent_manager.cloudflare_manager:
            cf_mgr = _tray_instance.agent_manager.cloudflare_manager
            cf_connected = cf_mgr.is_running and bool(cf_mgr.public_url)
            cf_url = cf_mgr.public_url or ""
        if _tray_instance and _tray_instance.agent_manager.ngrok_manager:
            ng_mgr = _tray_instance.agent_manager.ngrok_manager
            ngrok_connected = ng_mgr.is_running and bool(ng_mgr.public_url)
            ngrok_url = ng_mgr.public_url or ""
    except Exception:
        pass

    return {
        "sfera_connected": sfera_connected,
        "cf_connected": cf_connected,
        "cf_url": cf_url,
        "ngrok_connected": ngrok_connected,
        "ngrok_url": ngrok_url,
        "version": "0.5.1-web",
    }


@router.post("/test-sfera")
async def gui_test_sfera():
    """Forces an immediate Sfera ping and returns latency and connection result."""
    from app.sfera.sfera_worker import sfera_worker
    import time

    start = time.perf_counter()
    sfera_connected = False
    try:
        if sfera_worker.is_ready and sfera_worker._sfera:
            # Lightweight probe — read Kontrahenci object
            def probe():
                sfera_worker._sfera.o_subiekt.Kontrahenci  # Access COM attr — throws if dead
                return True
            await sfera_worker.submit_task(probe)
            sfera_connected = True
    except Exception:
        sfera_connected = False

    latency = round((time.perf_counter() - start) * 1000, 1)
    return {"sfera_connected": sfera_connected, "latency_ms": latency}


@router.get("/stats")
async def gui_stats():
    """Returns live agent statistics snapshot."""
    return agent_stats.get_snapshot()


@router.get("/config")
async def gui_get_config():
    """Returns current agent configuration merged from .env and config.json."""
    sfera = app_config.settings.sfera
    mapping = app_config.settings.mappings
    return GUIConfigPayload(
        db_server_name=sfera.db_server_name,
        db_name=sfera.db_name,
        sfera_operator=sfera.sfera_operator,
        sfera_operator_password=sfera.sfera_operator_password,
        agent_api_key=sfera.agent_api_key,
        agent_port=sfera.agent_port,
        cloudflare_enabled=sfera.cloudflare_enabled,
        cloudflare_token=sfera.cloudflare_token,
        cloudflare_custom_url=sfera.cloudflare_custom_url,
        autostart_enabled=sfera.autostart_enabled,
        ngrok_enabled=sfera.ngrok_enabled,
        ngrok_authtoken=sfera.ngrok_authtoken,
        ngrok_domain=sfera.ngrok_domain,
        ksef_enabled=mapping.ksef_enabled,
        fiscalization_enabled=mapping.fiscalization_enabled,
        fiscal_printer_id=mapping.fiscal_printer_id or 0,
        distributed_costs_keywords=mapping.distributed_costs_keywords,
    )


@router.post("/config")
async def gui_save_config(payload: GUIConfigPayload):
    """Saves new configuration to .env and config.json, then reloads in-memory settings."""
    try:
        # 1. Save .env part
        new_sfera = SferaSettings(
            db_server_name=payload.db_server_name,
            db_name=payload.db_name,
            sfera_operator=payload.sfera_operator,
            sfera_operator_password=payload.sfera_operator_password,
            agent_api_key=payload.agent_api_key,
            agent_port=payload.agent_port,
            cloudflare_enabled=payload.cloudflare_enabled,
            cloudflare_token=payload.cloudflare_token,
            cloudflare_custom_url=payload.cloudflare_custom_url,
            autostart_enabled=payload.autostart_enabled,
            ngrok_enabled=payload.ngrok_enabled,
            ngrok_authtoken=payload.ngrok_authtoken,
            ngrok_domain=payload.ngrok_domain,
        )
        save_sfera_settings(new_sfera)

        # 2. Save config.json part via ConfigService
        config_svc = ConfigService()
        mapping = config_svc.get_config()
        mapping.ksef_enabled = payload.ksef_enabled
        mapping.fiscalization_enabled = payload.fiscalization_enabled
        mapping.fiscal_printer_id = payload.fiscal_printer_id
        mapping.distributed_costs_keywords = payload.distributed_costs_keywords
        config_svc.save_config(mapping)

        return {"status": "ok", "message": "Konfiguracja zapisana i zaktualizowana w pamięci."}
    except Exception as e:
        logger.error(f"Błąd zapisu konfiguracji GUI: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/config/reset")
async def gui_reset_config():
    """Resets agent settings to built-in defaults."""
    try:
        defaults = SferaSettings(
            db_server_name="SERVER\\SQL",
            db_name="DATABASE",
            sfera_operator="Szef",
            sfera_operator_password="",
            agent_api_key="SECRET_API_KEY_PLACEHOLDER",
            agent_port=8000,
            cloudflare_enabled=False,
            cloudflare_token="",
            cloudflare_custom_url="",
            autostart_enabled=False,
        )
        save_sfera_settings(defaults)
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/restart")
async def gui_restart():
    """Schedules an agent restart (server + Sfera worker)."""
    import asyncio
    from app.sfera.sfera_worker import sfera_worker

    async def _do_restart():
        await asyncio.sleep(0.5)
        sfera_worker.stop()
        await asyncio.sleep(0.5)
        sfera_worker.start()

    asyncio.create_task(_do_restart())
    return {"status": "ok", "message": "Restart zaplanowany."}


@router.post("/logs/clear")
async def gui_clear_logs():
    """Clears the in-memory log backlog buffer."""
    log_broadcaster._buffer.clear()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WEBSOCKET LOG STREAMING
# ---------------------------------------------------------------------------

@ws_router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    """WebSocket endpoint — streams live logs to the browser dashboard."""
    await log_broadcaster.connect(websocket)
    try:
        while True:
            # Keep connection alive; actual data is pushed by BroadcastLogHandler
            await asyncio.sleep(30)
            try:
                await websocket.send_text(json.dumps({"ping": True}))
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await log_broadcaster.disconnect(websocket)
