# Plik: subiekt_agent/main_gui.py
import sys
import os
import io

# Gdy aplikacja jest skompilowana jako windowsowa (console=False),
# PyInstaller ustawia sys.stdout i sys.stderr na None.
# Uvicorn i inne biblioteki wywołują .isatty() → AttributeError.
# Rozwiązanie: przekierowanie do null stream przed importem czegokolwiek.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

# Zapewnia, że katalog projektu jest w sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.gui.tray import TrayApp

if __name__ == "__main__":
    app = TrayApp()
    app.run()
