"""
app/tunnel/ngrok_manager.py — Zarządza procesem ngrok.exe jako tunelem HTTP.

Obsługuje dwa tryby:
  1. Bez authtoken   → ngrok http <port>   (bezpłatny, losowy URL, wymagane zalogowanie)
  2. Z authtokenem   → ngrok http <port>   + authtoken, z opcjonalną stałą domeną (ngrok Pro/Free)

ngrok.exe jest pobierane automatycznie, jeśli go nie ma w standardowej lokalizacji.
"""
import os
import sys
import json
import subprocess
import threading
import logging
import urllib.request
import zipfile
import io
from pathlib import Path

logger = logging.getLogger(__name__)


class NgrokManager:
    """
    Zarządza procesem ngrok.exe do tworzenia tunelu HTTP.
    Interfejs analogiczny do CloudflareManager.
    """

    def __init__(self, port: int = 8000, authtoken: str = "", domain: str = ""):
        self.port = port
        self.authtoken = authtoken.strip()
        self.domain = domain.strip()          # Stała domena ngrok (wymaga planu Pro lub Free z rezerwacją)
        self.process = None
        self.public_url: str = ""
        self._thread = None
        self._stop_event = threading.Event()
        self.is_running = False

        # Katalog binarek (wspólny z cloudflared)
        self.bin_dir = Path(os.getenv("APPDATA", str(Path.home()))) / "SuppSalesAgent" / "bin"
        self.bin_path = self.bin_dir / "ngrok.exe"

        # Jeśli jesteśmy w paczce PyInstaller, sprawdź _MEIPASS
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            bundle_bin = Path(sys._MEIPASS) / "ngrok.exe"
            if bundle_bin.exists():
                self.bin_path = bundle_bin

    # ------------------------------------------------------------------
    # Pobranie ngrok.exe
    # ------------------------------------------------------------------

    def _ensure_binary(self) -> bool:
        """Upewnia się, że ngrok.exe istnieje. Jeśli nie, pobiera je."""
        if self.bin_path.exists():
            return True

        logger.info(f"Brak ngrok.exe w: {self.bin_path}. Rozpoczynam automatyczne pobieranie...")
        try:
            self.bin_dir.mkdir(parents=True, exist_ok=True)

            # Oficjalny ZIP dla Windows 64-bit ze strony ngrok.com
            url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            logger.info("Pobieranie ngrok.exe z ngrok.com...")
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()

            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                # Wewnątrz ZIP jest plik ngrok.exe
                zf.extract("ngrok.exe", path=self.bin_dir)

            logger.info(f"Pomyślnie pobrano ngrok.exe i zapisano w {self.bin_path}")
            return True
        except Exception as e:
            logger.error(f"Nie udało się pobrać ngrok.exe: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self):
        """Uruchamia tunel ngrok w tle."""
        if self.is_running:
            return
        self._stop_event.clear()
        self.is_running = True
        self._thread = threading.Thread(target=self._run_tunnel_loop, daemon=True)
        self._thread.start()
        logger.info("Inicjalizacja wątku managera ngrok Tunnel...")

    def stop(self):
        """Zatrzymuje tunel ngrok."""
        if not self.is_running:
            return
        logger.info("Zamykanie tunelu ngrok...")
        self.is_running = False
        self._stop_event.set()
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    self.process.kill()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Błąd podczas zatrzymywania ngrok: {e}")
            self.process = None
        self.public_url = ""
        logger.info("Tunel ngrok został zatrzymany.")

    # ------------------------------------------------------------------
    # Wewnętrzna pętla
    # ------------------------------------------------------------------

    def _run_tunnel_loop(self):
        while not self._stop_event.is_set():
            if not self._ensure_binary():
                logger.error("Brak ngrok.exe, ponowna próba za 30 sekund...")
                self._stop_event.wait(30)
                continue

            # Ustaw authtoken jeśli podany (zapis do lokalnej konfiguracji ngrok)
            if self.authtoken:
                self._configure_authtoken()

            # Zbuduj komendę
            cmd = [str(self.bin_path), "http"]
            if self.domain:
                cmd += ["--domain", self.domain]
            cmd += [f"127.0.0.1:{self.port}"]
            # Wymuszamy format JSON w logach, żeby łatwo wyciągnąć URL
            cmd += ["--log", "stdout", "--log-format", "json", "--log-level", "info"]

            logger.info(f"Uruchamianie ngrok http {self.port}" + (f" --domain {self.domain}" if self.domain else "") + "...")

            try:
                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE

                self.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    startupinfo=startupinfo,
                )

                # Parsuj stdout (JSON) w osobnym wątku
                stdout_thread = threading.Thread(
                    target=self._parse_output, args=(self.process.stdout,), daemon=True
                )
                stdout_thread.start()

                # Stderr dla błędów
                stderr_thread = threading.Thread(
                    target=self._log_stderr, args=(self.process.stderr,), daemon=True
                )
                stderr_thread.start()

                exit_code = self.process.wait()
                if not self._stop_event.is_set():
                    logger.warning(
                        f"Proces ngrok zakończył się z kodem {exit_code}. Restart za 5 sekund..."
                    )
                    self.public_url = ""
                    self._stop_event.wait(5)
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Wyjątek podczas działania ngrok: {e}. Restart za 5 sekund...")
                    self.public_url = ""
                    self._stop_event.wait(5)

    def _configure_authtoken(self):
        """Zapisuje authtoken do konfiguracji ngrok."""
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            result = subprocess.run(
                [str(self.bin_path), "config", "add-authtoken", self.authtoken],
                capture_output=True, text=True, timeout=15,
                startupinfo=startupinfo,
            )
            if result.returncode == 0:
                logger.info("Authtoken ngrok skonfigurowany pomyślnie.")
            else:
                logger.warning(f"Błąd konfiguracji authtoken ngrok: {result.stderr.strip()}")
        except Exception as e:
            logger.error(f"Wyjątek podczas konfiguracji authtoken ngrok: {e}")

    def _parse_output(self, pipe):
        """Parsuje JSON logi ngrok ze stdout i wyciąga URL tunelu."""
        try:
            for line in pipe:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    msg = entry.get("msg", "")
                    lvl = entry.get("lvl", "info")

                    if lvl == "error":
                        logger.error(f"[ngrok] {msg}")
                    elif lvl == "warn":
                        logger.warning(f"[ngrok] {msg}")
                    else:
                        logger.debug(f"[ngrok] {msg}")

                    # Szukamy URL tunelu
                    url = entry.get("url", "") or entry.get("addr", "")
                    if url.startswith("https://") and not self.public_url:
                        self.public_url = url
                        logger.info(f"Tunel ngrok aktywny! Publiczny URL: {self.public_url}")
                except json.JSONDecodeError:
                    # Fallback — szukamy URL w surowej linii
                    if "https://" in line and ".ngrok" in line and not self.public_url:
                        for part in line.split():
                            if part.startswith("https://") and ".ngrok" in part:
                                self.public_url = part.strip()
                                logger.info(f"Tunel ngrok aktywny! Publiczny URL: {self.public_url}")
                                break
                    logger.debug(f"[ngrok] {line}")
        except Exception as e:
            logger.error(f"Błąd parsowania wyjścia ngrok: {e}")

    def _log_stderr(self, pipe):
        try:
            for line in pipe:
                line = line.strip()
                if line:
                    logger.warning(f"[ngrok-stderr] {line}")
        except Exception:
            pass
