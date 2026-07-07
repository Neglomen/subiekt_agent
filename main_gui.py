# Plik: subiekt_agent/main_gui.py
import sys
import os

# Zapewnia, że katalog projektu jest w sys.path (niezbędne przy uruchamianiu bezpośrednim i po skompilowaniu)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.gui.tray import TrayApp

if __name__ == "__main__":
    app = TrayApp()
    app.run()
