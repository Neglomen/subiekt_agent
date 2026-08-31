# Plik: subiekt_agent/app/services/updater.py

import logging
import re
import os
import subprocess
import tempfile
import time
import urllib.request
import json
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

APP_VERSION = "0.9.0"
GITHUB_REPO = "Neglomen/subiekt_agent"

# Aktualizacje mogą być pobierane wyłącznie z tych hostów (GitHub Releases).
# Chroni przed nadużyciem mechanizmu auto-update do pobrania i uruchomienia
# dowolnego pliku (patrz subiekt_agent/CLAUDE.md — sekcja "Bezpieczeństwo").
ALLOWED_DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com")

class UpdateManager:
    def __init__(self):
        self.download_progress = 0
        self.download_status = "idle"  # idle, downloading, finished, error
        self.error_message = ""
        self.downloaded_file_path: Optional[Path] = None

    @staticmethod
    def is_safe_download_url(url: str) -> bool:
        """Sprawdza, czy URL wskazuje na zaufany host (GitHub Releases) po HTTPS."""
        try:
            parsed = urlparse(url)
            return parsed.scheme == "https" and parsed.hostname in ALLOWED_DOWNLOAD_HOSTS
        except Exception:
            return False

    @staticmethod
    def parse_version(version_str: str) -> tuple:
        """Konwertuje wersję tekstową (np. 'v0.5.1-web') do krotki liczb (0, 5, 1) do porównania."""
        cleaned = re.sub(r'[^0-9.]', '', version_str)
        try:
            return tuple(int(x) for x in cleaned.split('.') if x)
        except ValueError:
            return (0, 0, 0)

    def check_for_updates(self) -> Dict[str, Any]:
        """
        Pobiera informacje o najnowszej wersji z publicznego repozytorium GitHub.
        Zwraca słownik z informacjami o dostępności aktualizacji.
        """
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'subiekt-agent-updater'}
        )
        
        from app.config import settings
        from app.utils import urlopen_with_fallback
        ignore_ssl = getattr(settings.mappings, 'ignore_ssl_errors', False)
        
        try:
            with urlopen_with_fallback(req, ignore_ssl=ignore_ssl, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                
            latest_version_str = data.get("tag_name", "v0.0.0")
            changelog = data.get("body", "")
            
            # Szukamy assetu o rozszerzeniu .exe
            download_url = None
            for asset in data.get("assets", []):
                asset_name = asset.get("name", "")
                if asset_name.endswith(".exe"):
                    download_url = asset.get("browser_download_url")
                    break
            
            current_ver = self.parse_version(APP_VERSION)
            latest_ver = self.parse_version(latest_version_str)
            
            is_newer = latest_ver > current_ver
            
            return {
                "current_version": APP_VERSION,
                "latest_version": latest_version_str,
                "is_newer": is_newer,
                "changelog": changelog,
                "download_url": download_url
            }
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania aktualizacji na GitHubie: {e}")
            return {
                "current_version": APP_VERSION,
                "latest_version": "v0.0.0",
                "is_newer": False,
                "changelog": "",
                "download_url": None,
                "error": str(e)
            }

    def start_download_and_install(self, download_url: str):
        """Uruchamia proces pobierania instalatora w osobnym wątku."""
        import threading
        if self.download_status == "downloading":
            logger.warning("Pobieranie aktualizacji jest już w toku.")
            return

        self.download_progress = 0
        self.download_status = "downloading"
        self.error_message = ""
        
        thread = threading.Thread(
            target=self._download_and_install_worker,
            args=(download_url,),
            daemon=True
        )
        thread.start()

    def _download_and_install_worker(self, download_url: str):
        """Pracownik pobierający plik w pętli z uaktualnianiem postępu."""
        if not self.is_safe_download_url(download_url):
            logger.error(f"Odrzucono pobieranie z niezaufanego URL: {download_url}")
            self.download_status = "error"
            self.error_message = "Adres pobierania nie przeszedł weryfikacji bezpieczeństwa."
            return
        try:
            logger.info(f"Rozpoczynam pobieranie aktualizacji z URL: {download_url}")
            temp_dir = Path(tempfile.gettempdir())
            dest_file = temp_dir / "SuppSalesAgent_Setup.exe"
            
            req = urllib.request.Request(
                download_url, 
                headers={'User-Agent': 'subiekt-agent-updater'}
            )
            
            from app.config import settings
            from app.utils import urlopen_with_fallback
            ignore_ssl = getattr(settings.mappings, 'ignore_ssl_errors', False)
            
            with urlopen_with_fallback(req, ignore_ssl=ignore_ssl) as response:
                total_size = int(response.info().get('Content-Length', 0))
                bytes_downloaded = 0
                block_size = 1024 * 64 # 64 KB
                
                with open(dest_file, "wb") as f:
                    while True:
                        block = response.read(block_size)
                        if not block:
                            break
                        f.write(block)
                        bytes_downloaded += len(block)
                        if total_size > 0:
                            self.download_progress = int((bytes_downloaded / total_size) * 100)
                        else:
                            self.download_progress = 50 # Fallback
                            
            logger.info(f"Pobieranie zakończone pomyślnie. Zapisano w: {dest_file}")
            self.downloaded_file_path = dest_file
            self.download_status = "finished"
            
            # Automatyczne uruchomienie instalatora po pobraniu
            self.apply_update()
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania aktualizacji: {e}")
            self.download_status = "error"
            self.error_message = str(e)

    def _release_file_locks(self) -> None:
        """
        Zatrzymuje tunel, serwer HTTP i SferaWorkera, zanim ruszy instalator.

        `cloudflared.exe` i `ngrok.exe` agent pobiera do `%APPDATA%\\SuppSalesAgent\\bin`,
        czyli **do wnętrza katalogu instalacji**. Są to procesy potomne — samo zamknięcie
        agenta ich nie kończy, a dopóki żyją, Inno Setup nie nadpisze plików w `{app}`
        i instalacja pada na błędach dostępu.
        """
        try:
            from app.gui import tray

            manager = getattr(tray._tray_instance, "agent_manager", None)
            if manager is None:
                logger.warning("Brak instancji AgentManagera — pomijam zamykanie usług.")
                return
            manager.stop()
            logger.info("Usługi agenta zatrzymane, pliki zwolnione.")
        except Exception as e:
            # Instalator i tak ma ruszyć: gorsza jest aktualizacja, która nie startuje,
            # niż taka, która trafi na zablokowany plik i o tym powie.
            logger.error(f"Nie udało się zatrzymać usług agenta przed aktualizacją: {e}")

    def apply_update(self):
        """Uruchamia pobrany instalator i zamyka bieżącą aplikację."""
        if not self.downloaded_file_path or not self.downloaded_file_path.exists():
            logger.error("Nie znaleziono pobranego instalatora do uruchomienia.")
            return

        logger.info("Zatrzymywanie usług agenta przed aktualizacją...")
        self._release_file_locks()
        # Chwila na zamkniecie uchwytow przez system po zabiciu procesow potomnych.
        time.sleep(1.5)

        logger.info("Uruchamianie instalatora i wyłączanie agenta...")
        try:
            # Uruchamiamy instalator w tle. 
            # Domyślnie nie używamy flag /SILENT, aby użytkownik widział instalator.
            subprocess.Popen([str(self.downloaded_file_path)])
        except Exception as e:
            logger.error(f"Nie udało się uruchomić instalatora: {e}")
            self.download_status = "error"
            self.error_message = f"Uruchomienie instalatora nie powiodło się: {e}"
            return

        # `os._exit`, nie `sys.exit`: ta metoda biegnie w wątku pobierania
        # (`start_download_and_install` -> threading.Thread), a `sys.exit()` poza wątkiem
        # głównym kończy wyłącznie ten wątek. Proces agenta zostawał więc przy życiu i
        # trzymał własne pliki, przez co instalator wywalał się na błędach dostępu.
        logging.shutdown()
        os._exit(0)

# Globalna instancja UpdateManagera
update_manager = UpdateManager()
