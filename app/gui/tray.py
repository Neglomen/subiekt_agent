import os
import sys
import threading
import queue
import logging
import time
import tkinter as tk
from pathlib import Path
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import uvicorn

import app.config as app_config
from app.tunnel.cloudflare_manager import CloudflareManager
from app.gui.window import AgentWindow
from app.gui.log_handler import QueueLogHandler
from app.sfera.sfera_worker import sfera_worker

logger = logging.getLogger(__name__)

class UvicornServerThread(threading.Thread):
    def __init__(self, app, host="127.0.0.1", port=8000):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.app = app
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
        self.start_time = None
        self.is_active = False
        self.status_message = "Zatrzymany"
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.is_active:
                return
                
            logger.info("Uruchamianie serwerów i tuneli agenta...")
            
            # Pobieramy najświeższą konfigurację
            sfera = app_config.settings.sfera
            port = sfera.agent_port
            
            # 1. Uruchomienie FastAPI / Uvicorn w osobnym wątku
            from app.main import app as fastapi_app
            self.server_thread = UvicornServerThread(fastapi_app, host="127.0.0.1", port=port)
            self.server_thread.start()
            
            # 2. Uruchomienie Cloudflare Tunnel jeśli włączony
            if sfera.cloudflare_enabled:
                self.cloudflare_manager = CloudflareManager(
                    port=port, 
                    token=sfera.cloudflare_token or None, 
                    custom_url=sfera.cloudflare_custom_url or None
                )
                self.cloudflare_manager.start()
            else:
                self.cloudflare_manager = None
                
            self.start_time = time.time()
            self.is_active = True
            self.status_message = "Uruchomiony"
            logger.info("Agent i powiązane usługi zostały pomyślnie uruchomione.")

    def stop(self):
        with self.lock:
            if not self.is_active:
                return
                
            logger.info("Zatrzymywanie usług agenta...")
            
            # 1. Zatrzymanie tunelu Cloudflare
            if self.cloudflare_manager:
                try:
                    self.cloudflare_manager.stop()
                except Exception as e:
                    logger.error(f"Błąd podczas zatrzymywania tunelu: {e}")
                self.cloudflare_manager = None
                
            # 2. Zatrzymanie FastAPI / Uvicorn
            if self.server_thread:
                try:
                    self.server_thread.stop()
                    self.server_thread.join(timeout=3)
                except Exception as e:
                    logger.error(f"Błąd podczas zatrzymywania uvicorn: {e}")
                self.server_thread = None
                
            # 3. Zatrzymanie SferaWorker
            try:
                sfera_worker.stop()
            except Exception as e:
                logger.error(f"Błąd podczas zatrzymywania SferaWorker: {e}")
                
            self.start_time = None
            self.is_active = False
            self.status_message = "Zatrzymany"
            logger.info("Agent został pomyślnie zatrzymany.")

    def restart(self):
        self.stop()
        time.sleep(1)
        self.start()


class TrayApp:
    def __init__(self):
        # Inicjalizacja niewidocznego głównego okna Tkinter
        self.root = tk.Tk()
        self.root.withdraw()
        
        # Kolejka logów
        self.log_queue = queue.Queue()
        self._setup_logging()
        
        # Manager usług agenta
        self.agent_manager = AgentManager()
        
        # Okno GUI
        self.window = AgentWindow(self.root, self.agent_manager, self.log_queue)
        self.window.withdraw() # Schowane przy starcie
        
        # Ikona w tray
        self.icon = None
        self._create_assets_dir_and_icon()
        
    def _setup_logging(self):
        root_logger = logging.getLogger()
        # Dodajemy nasz customowy handler do kolejkowania logów do GUI
        self.gui_handler = QueueLogHandler(self.log_queue)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s')
        self.gui_handler.setFormatter(formatter)
        self.gui_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(self.gui_handler)

    def _generate_default_icon(self) -> Image.Image:
        """Generuje ładną ikonę koła z symbolem 'S' za pomocą Pillow."""
        image = Image.new('RGB', (64, 64), color='#2c3e50')
        dc = ImageDraw.Draw(image)
        # Zielone koło (SuppSales green)
        dc.ellipse([8, 8, 56, 56], fill='#27ae60')
        # Biała litera 'S' w środku
        # Używamy linii do narysowania 'S' jeśli brak czcionki
        dc.line([(24, 20), (40, 20)], fill='white', width=6)
        dc.line([(24, 20), (24, 32)], fill='white', width=6)
        dc.line([(24, 32), (40, 32)], fill='white', width=6)
        dc.line([(40, 32), (40, 44)], fill='white', width=6)
        dc.line([(24, 44), (40, 44)], fill='white', width=6)
        return image

    def _create_assets_dir_and_icon(self):
        """Tworzy katalog zasobów i zapisuje domyślną ikonę, jeśli nie istnieje."""
        assets_dir = Path(app_config.BASE_DIR) / "app" / "gui" / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        
        icon_path = assets_dir / "icon.png"
        if not icon_path.exists():
            try:
                img = self._generate_default_icon()
                img.save(icon_path)
                logger.info(f"Wygenerowano i zapisano domyślną ikonę w {icon_path}")
            except Exception as e:
                logger.error(f"Nie udało się zapisać wygenerowanej ikony: {e}")

        # Wczytujemy ikonę
        try:
            self.icon_image = Image.open(icon_path)
        except Exception:
            self.icon_image = self._generate_default_icon()

    def _show_panel(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _on_exit(self):
        logger.info("Zamykanie aplikacji z poziomu ikony w tray...")
        self.agent_manager.stop()
        if self.icon:
            self.icon.stop()
        self.root.after(0, self.root.destroy)

    def _run_tray_loop(self):
        menu = pystray.Menu(
            item('Otwórz panel', self._show_panel, default=True),
            item('Uruchom agenta', lambda: self.agent_manager.start(), enabled=lambda item: not self.agent_manager.is_active),
            item('Zatrzymaj agenta', lambda: self.agent_manager.stop(), enabled=lambda item: self.agent_manager.is_active),
            pystray.Menu.SEPARATOR,
            item('Wyjdź', self._on_exit)
        )
        
        self.icon = pystray.Icon(
            "SuppSalesAgent", 
            self.icon_image, 
            "SuppSales Subiekt GT Agent", 
            menu=menu
        )
        
        # Pętla ikony w tray
        self.icon.run()

    def run(self):
        # 1. Uruchamiamy agenta automatycznie przy starcie
        self.agent_manager.start()
        
        # 2. Uruchamiamy pystray w osobnym wątku
        tray_thread = threading.Thread(target=self._run_tray_loop, daemon=True)
        tray_thread.start()
        
        # 3. Uruchamiamy główną pętlę Tkinter (musi być w głównym wątku)
        self.root.mainloop()
