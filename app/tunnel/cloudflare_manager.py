import os
import sys
import subprocess
import threading
import logging
import urllib.request
import re
from pathlib import Path

logger = logging.getLogger(__name__)

class CloudflareManager:
    """
    Zarządza procesem cloudflared.exe do tworzenia tunelu (Quick lub Named).
    """
    def __init__(self, port=8000, token=None, custom_url=None):
        self.port = port
        self.token = token
        self.custom_url = custom_url
        self.process = None
        self.public_url = None
        self._thread = None
        self._stop_event = threading.Event()
        self.is_running = False
        
        # Wyznaczanie ścieżki do cloudflared.exe
        self.bin_dir = Path(os.getenv("APPDATA", str(Path.home()))) / "SuppSalesAgent" / "bin"
        self.bin_path = self.bin_dir / "cloudflared.exe"
        
        # Jeśli jesteśmy w paczce PyInstaller (sys._MEIPASS), sprawdzamy najpierw tam
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            bundle_bin = Path(sys._MEIPASS) / "cloudflared.exe"
            if bundle_bin.exists():
                self.bin_path = bundle_bin

    def _ensure_binary(self):
        """Upewnia się, że cloudflared.exe istnieje. Jeśli nie, pobiera go."""
        if self.bin_path.exists():
            return True
            
        logger.info(f"Brak pliku cloudflared.exe w: {self.bin_path}. Rozpoczynam automatyczne pobieranie...")
        try:
            self.bin_dir.mkdir(parents=True, exist_ok=True)
            
            # Pobieranie najnowszej oficjalnej wersji dla Windows x64
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
            
            # Request z User-Agentem, żeby uniknąć blokowania przez GitHub
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            
            logger.info("Łączenie z GitHub w celu pobrania cloudflared...")
            with urllib.request.urlopen(req) as response, open(self.bin_path, 'wb') as out_file:
                # Pobieranie w blokach z raportowaniem postępu
                total_size = int(response.info().get('Content-Length', 0))
                downloaded = 0
                block_size = 1024 * 256  # 256 KB
                
                last_percent = -10
                while True:
                    block = response.read(block_size)
                    if not block:
                        break
                    out_file.write(block)
                    downloaded += len(block)
                    if total_size > 0:
                        percent = int((downloaded / total_size) * 100)
                        if percent >= last_percent + 10:
                            logger.info(f"Pobieranie cloudflared: {percent}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)")
                            last_percent = percent
                            
            logger.info(f"Pomyślnie pobrano cloudflared.exe i zapisano w {self.bin_path}")
            return True
        except Exception as e:
            logger.error(f"Nie udało się pobrać cloudflared.exe: {e}", exc_info=True)
            return False

    def start(self):
        """Uruchamia tunel w tle."""
        if self.is_running:
            return
            
        self._stop_event.clear()
        self.is_running = True
        self._thread = threading.Thread(target=self._run_tunnel_loop, daemon=True)
        self._thread.start()
        logger.info("Inicjalizacja wątku managera Cloudflare Tunnel...")

    def stop(self):
        """Zatrzymuje tunel."""
        if not self.is_running:
            return
            
        logger.info("Zamykanie tunelu Cloudflare...")
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
                logger.error(f"Błąd podczas zabijania procesu cloudflared: {e}")
            self.process = None
            
        self.public_url = None
        logger.info("Tunel Cloudflare został zatrzymany.")

    def _run_tunnel_loop(self):
        """Pętla uruchamiająca i monitorująca proces cloudflared."""
        while not self._stop_event.is_set():
            if not self._ensure_binary():
                logger.error("Brak cloudflared.exe, ponowna próba pobrania za 30 sekund...")
                self._stop_event.wait(30)
                continue
                
            cmd = []
            if self.token:
                # Named Tunnel z tokenem
                cmd = [str(self.bin_path), "tunnel", "--no-autoupdate", "run", "--token", self.token]
                self.public_url = self.custom_url or "Konfiguracja CF (własna domena)"
                logger.info("Uruchamianie własnego tunelu Cloudflare (z tokenem)...")
                # Quick Tunnel (trycloudflare.com)
                cmd = [str(self.bin_path), "tunnel", "--url", f"http://127.0.0.1:{self.port}"]
                self.public_url = None
                logger.info(f"Uruchamianie Quick Tunnel dla portu {self.port}...")

            try:
                # cloudflared pisze większość informacji diagnostycznych na stderr
                # Uruchamiamy w ukrytym oknie na Windows (brak czarnego okna)
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    startupinfo=startupinfo
                )
                
                # Wątek pomocniczy do czytania stderr procesu i wyciągania URL
                stderr_thread = threading.Thread(target=self._parse_output, args=(self.process.stderr,), daemon=True)
                stderr_thread.start()
                
                # Czekamy na zakończenie procesu
                exit_code = self.process.wait()
                if not self._stop_event.is_set():
                    logger.warning(f"Proces cloudflared zakończył się z kodem {exit_code}. Restart za 5 sekund...")
                    self.public_url = None
                    self._stop_event.wait(5)
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Wyjątek podczas działania cloudflared: {e}. Restart za 5 sekund...")
                    self.public_url = None
                    self._stop_event.wait(5)

    def _parse_output(self, pipe):
        """Parsuje stderr/stdout z cloudflared w celu znalezienia URL Quick Tunnel."""
        # Szablon szukający adresu trycloudflare.com
        url_regex = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")
        
        try:
            for line in pipe:
                line_str = line.strip()
                if not line_str:
                    continue
                # Przekazujemy logi z cloudflared do głównego logera jako DEBUG/INFO
                if "ERR" in line_str:
                    logger.error(f"[cloudflared] {line_str}")
                elif "WRN" in line_str:
                    logger.warning(f"[cloudflared] {line_str}")
                else:
                    logger.debug(f"[cloudflared] {line_str}")
                    
                # Jeśli to Quick Tunnel i jeszcze nie mamy URL, szukamy go
                if not self.token and not self.public_url:
                    match = url_regex.search(line_str)
                    if match:
                        self.public_url = match.group(0)
                        logger.info(f"Utworzono Quick Tunnel! Publiczny URL: {self.public_url}")
        except Exception as e:
            logger.error(f"Błąd podczas parsowania wyjścia cloudflared: {e}")
