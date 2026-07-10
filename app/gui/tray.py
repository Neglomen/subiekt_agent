import os
import sys
import threading
import logging
import time

import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

import app.config as app_config
from app.tunnel.cloudflare_manager import CloudflareManager
from app.tunnel.ngrok_manager import NgrokManager
from app.gui.log_handler import QueueLogHandler
from app.sfera.sfera_worker import sfera_worker
from app.gui import webview_window

logger = logging.getLogger(__name__)

# Moduł-poziomowa referencja do aktywnej instancji TrayApp.
_tray_instance = None


class UvicornServerThread(threading.Thread):
    def __init__(self, app, host="127.0.0.1", port=8000):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.app = app
        import uvicorn
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            loop="asyncio"
        )
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


class AgentManager:
    def __init__(self):
        self.server_thread = None
        self.cloudflare_manager = None
        self.ngrok_manager = None
        self.start_time = None
        self.is_active = False
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.is_active:
                return

            logger.info("Uruchamianie serwera FastAPI i tunelu Cloudflare...")
            sfera = app_config.settings.sfera
            port = sfera.agent_port

            # 1. Uruchom SferaWorker
            sfera_worker.start()

            # 2. Uruchom FastAPI / Uvicorn
            from app.main import app as fastapi_app
            self.server_thread = UvicornServerThread(fastapi_app, host="127.0.0.1", port=port)
            self.server_thread.start()

            # 3. Uruchom Cloudflare Tunnel jeśli włączony
            if sfera.cloudflare_enabled:
                self.cloudflare_manager = CloudflareManager(
                    port=port,
                    token=sfera.cloudflare_token or None,
                    custom_url=sfera.cloudflare_custom_url or None
                )
                self.cloudflare_manager.start()
            else:
                self.cloudflare_manager = None

            # 4. Uruchom ngrok jeśli włączony
            if sfera.ngrok_enabled:
                self.ngrok_manager = NgrokManager(
                    port=port,
                    authtoken=sfera.ngrok_authtoken or "",
                    domain=sfera.ngrok_domain or "",
                )
                self.ngrok_manager.start()
            else:
                self.ngrok_manager = None

            self.start_time = time.time()
            self.is_active = True
            logger.info(f"Agent uruchomiony na http://127.0.0.1:{port}")

    def stop(self):
        with self.lock:
            if not self.is_active:
                return

            logger.info("Zatrzymywanie usług agenta...")

            if self.cloudflare_manager:
                try:
                    self.cloudflare_manager.stop()
                except Exception as e:
                    logger.error(f"Błąd zatrzymywania CF: {e}")
                self.cloudflare_manager = None

            if self.ngrok_manager:
                try:
                    self.ngrok_manager.stop()
                except Exception as e:
                    logger.error(f"Błąd zatrzymywania ngrok: {e}")
                self.ngrok_manager = None

            if self.server_thread:
                try:
                    self.server_thread.stop()
                    self.server_thread.join(timeout=3)
                except Exception as e:
                    logger.error(f"Błąd zatrzymywania uvicorn: {e}")
                self.server_thread = None

            try:
                sfera_worker.stop()
            except Exception as e:
                logger.error(f"Błąd zatrzymywania SferaWorker: {e}")

            self.start_time = None
            self.is_active = False
            logger.info("Agent zatrzymany.")

    def restart(self):
        self.stop()
        time.sleep(1)
        self.start()

    def update_tunnels(self):
        """Aktualizuje tunele (CF i ngrok) w locie, po zapisaniu konfiguracji."""
        with self.lock:
            if not self.is_active:
                return

            logger.info("Aktualizacja tuneli w tle na podstawie nowej konfiguracji...")
            sfera = app_config.settings.sfera
            port = sfera.agent_port

            # 1. Cloudflare Tunnel
            if sfera.cloudflare_enabled:
                if self.cloudflare_manager:
                    logger.info("Restartowanie istniejącego tunelu Cloudflare...")
                    try:
                        self.cloudflare_manager.stop()
                    except Exception as e:
                        logger.error(f"Błąd zatrzymywania CF: {e}")
                self.cloudflare_manager = CloudflareManager(
                    port=port,
                    token=sfera.cloudflare_token or None,
                    custom_url=sfera.cloudflare_custom_url or None
                )
                self.cloudflare_manager.start()
            else:
                if self.cloudflare_manager:
                    logger.info("Wyłączanie tunelu Cloudflare...")
                    try:
                        self.cloudflare_manager.stop()
                    except Exception as e:
                        logger.error(f"Błąd zatrzymywania CF: {e}")
                    self.cloudflare_manager = None

            # 2. ngrok Tunnel
            if sfera.ngrok_enabled:
                if self.ngrok_manager:
                    logger.info("Restartowanie istniejącego tunelu ngrok...")
                    try:
                        self.ngrok_manager.stop()
                    except Exception as e:
                        logger.error(f"Błąd zatrzymywania ngrok: {e}")
                self.ngrok_manager = NgrokManager(
                    port=port,
                    authtoken=sfera.ngrok_authtoken or "",
                    domain=sfera.ngrok_domain or "",
                )
                self.ngrok_manager.start()
            else:
                if self.ngrok_manager:
                    logger.info("Wyłączanie tunelu ngrok...")
                    try:
                        self.ngrok_manager.stop()
                    except Exception as e:
                        logger.error(f"Błąd zatrzymywania ngrok: {e}")
                    self.ngrok_manager = None


class TrayApp:
    def __init__(self):
        global _tray_instance
        _tray_instance = self

        self.agent_manager = AgentManager()
        self.icon_image = self._build_icon()
        self.icon = None

    def _build_icon(self) -> Image.Image:
        """Rysuje ikonę agenta (gradient fiolet→magenta, litera S)."""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        dc = ImageDraw.Draw(img)

        for i in range(size // 2, 0, -1):
            ratio = i / (size // 2)
            r = int(168 * ratio + 107 * (1 - ratio))
            g = int(36 * ratio + 0 * (1 - ratio))
            b = int(255 * ratio + 195 * (1 - ratio))
            dc.ellipse(
                [size // 2 - i, size // 2 - i, size // 2 + i, size // 2 + i],
                fill=(r, g, b, 220)
            )

        dc.line([(22, 18), (42, 18)], fill="white", width=5)
        dc.line([(22, 18), (22, 32)], fill="white", width=5)
        dc.line([(22, 32), (42, 32)], fill="white", width=5)
        dc.line([(42, 32), (42, 46)], fill="white", width=5)
        dc.line([(22, 46), (42, 46)], fill="white", width=5)

        return img

    def _open_dashboard(self):
        """Pokazuje natywne okno pywebview z dashboardem."""
        logger.info("Otwieranie panelu webview...")
        webview_window.show()

    def _on_exit(self):
        logger.info("Zamykanie aplikacji...")
        self.agent_manager.stop()
        if self.icon:
            self.icon.stop()
        # Zniszcz okno pywebview — zakończy jego pętlę na głównym wątku
        webview_window.destroy()

    def _run_tray_detached(self):
        """Uruchamia pystray w tle (run_detached — własny wątek)."""
        menu = pystray.Menu(
            item("Otwórz Panel", self._open_dashboard, default=True),
            pystray.Menu.SEPARATOR,
            item("Uruchom agenta", lambda: self.agent_manager.start(),
                 enabled=lambda i: not self.agent_manager.is_active),
            item("Zatrzymaj agenta", lambda: self.agent_manager.stop(),
                 enabled=lambda i: self.agent_manager.is_active),
            item("Restartuj agenta", lambda: self.agent_manager.restart()),
            pystray.Menu.SEPARATOR,
            item("Wyjdź", self._on_exit),
        )

        self.icon = pystray.Icon(
            "SuppSalesAgent",
            self.icon_image,
            "SuppSales Subiekt GT Agent",
            menu=menu,
        )
        # run_detached() uruchamia ikonę w osobnym wątku systemowym
        self.icon.run_detached()
        logger.info("Ikona w zasobniku systemowym uruchomiona.")

    def run(self):
        """
        Punkt wejścia aplikacji.
        1. Start agenta (FastAPI + tunele) w tle
        2. pystray uruchamia się jako detached (własny wątek)
        3. pywebview startuje na GŁÓWNYM wątku (wymóg Windows)
        """
        # 1. Start usług agenta
        self.agent_manager.start()

        # 2. pystray w tle
        self._run_tray_detached()

        # 3. Poczekaj chwilę na start serwera, potem otwórz okno
        port = app_config.settings.sfera.agent_port
        url = f"http://127.0.0.1:{port}"

        def _show_window_when_ready():
            """Czeka aż serwer odpowie, potem pokazuje okno."""
            import urllib.request
            for _ in range(30):  # max 15 sekund
                try:
                    urllib.request.urlopen(url, timeout=1)
                    break
                except Exception:
                    time.sleep(0.5)
            logger.info(f"Serwer gotowy, pokazuję okno pywebview: {url}")
            webview_window.show()

        threading.Thread(target=_show_window_when_ready, daemon=True).start()

        # 4. Główna pętla pywebview (blokuje wątek główny)
        logger.info(f"Uruchamianie pywebview na wątku głównym -> {url}")
        webview_window.start(url)

        # Po zamknięciu okna pywebview — sprzątamy
        logger.info("pywebview zakończył działanie. Zamykanie...")
        if self.agent_manager.is_active:
            self.agent_manager.stop()
        if self.icon:
            self.icon.stop()
