import os
import sys
import threading
import queue
import logging
import time
import webbrowser
import tkinter as tk
from pathlib import Path

import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

import app.config as app_config
from app.tunnel.cloudflare_manager import CloudflareManager
from app.tunnel.ngrok_manager import NgrokManager
from app.gui.log_handler import QueueLogHandler
from app.sfera.sfera_worker import sfera_worker

logger = logging.getLogger(__name__)

# Moduł-poziomowa referencja do aktywnej instancji TrayApp.
# Używana przez /gui/status do odczytu statusu tunelu Cloudflare.
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

            # 4. Uruchom ngrok jeśli włączony (można łączyć z CF lub osobno)
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


class TrayApp:
    def __init__(self):
        global _tray_instance
        _tray_instance = self

        # Niewidoczne okno root Tkinter potrzebne do obsługi pętli systemowej
        # (pystray na Windows czasem tego wymaga dla poprawnej pracy menu)
        self.root = tk.Tk()
        self.root.withdraw()

        # Manager usług
        self.agent_manager = AgentManager()

        # Ikona
        self.icon_image = self._build_icon()
        self.icon = None

    def _build_icon(self) -> Image.Image:
        """Rysuje ikonę agenta (gradient fiolet→magenta, litera S)."""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        dc = ImageDraw.Draw(img)

        # Tło: okrąg gradient (uproszczony przez kilka warstw)
        for i in range(size // 2, 0, -1):
            ratio = i / (size // 2)
            r = int(168 * ratio + 107 * (1 - ratio))
            g = int(36 * ratio + 0 * (1 - ratio))
            b = int(255 * ratio + 195 * (1 - ratio))
            dc.ellipse(
                [size // 2 - i, size // 2 - i, size // 2 + i, size // 2 + i],
                fill=(r, g, b, 220)
            )

        # Biała litera S
        dc.line([(22, 18), (42, 18)], fill="white", width=5)
        dc.line([(22, 18), (22, 32)], fill="white", width=5)
        dc.line([(22, 32), (42, 32)], fill="white", width=5)
        dc.line([(42, 32), (42, 46)], fill="white", width=5)
        dc.line([(22, 46), (42, 46)], fill="white", width=5)

        return img

    def _open_dashboard(self):
        port = app_config.settings.sfera.agent_port
        url = f"http://127.0.0.1:{port}"
        logger.info(f"Otwieranie panelu w przeglądarce: {url}")
        webbrowser.open(url)

    def _on_exit(self):
        logger.info("Zamykanie aplikacji...")
        self.agent_manager.stop()
        if self.icon:
            self.icon.stop()
        self.root.after(0, self.root.destroy)

    def _run_tray_loop(self):
        menu = pystray.Menu(
            item("Otwórz Panel (przeglądarka)", self._open_dashboard, default=True),
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
        self.icon.run()

    def run(self):
        # 1. Start agenta automatycznie przy uruchomieniu
        self.agent_manager.start()

        # Poczekaj chwilę, aż serwer wstanie, potem otwórz przeglądarkę
        def _delayed_open():
            time.sleep(2.5)
            self._open_dashboard()
        threading.Thread(target=_delayed_open, daemon=True).start()

        # 2. Uruchom pystray w osobnym wątku (ma własną pętlę zdarzeń)
        tray_thread = threading.Thread(target=self._run_tray_loop, daemon=True)
        tray_thread.start()

        # 3. Główna pętla Tkinter (musi być w wątku głównym)
        self.root.mainloop()
