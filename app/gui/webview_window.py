"""
app/gui/webview_window.py
Zarządza natywnym oknem pywebview z wbudowanym dashboardem.
Exposes JS API for custom window controls.
"""
import threading
import logging
import time

logger = logging.getLogger(__name__)

_window = None
_webview_started = threading.Event()


class WindowAPI:
    """API wystawione dla JavaScript (window.pywebview.api) do sterowania oknem."""
    def minimize(self):
        global _window
        if _window:
            logger.info("JS API: minimalizacja okna")
            _window.minimize()

    def maximize(self):
        global _window
        if _window:
            logger.info("JS API: maksymalizacja okna")
            if _window.maximized:
                _window.restore()
            else:
                _window.maximize()

    def close(self):
        global _window
        if _window:
            logger.info("JS API: ukrywanie okna (zamknięcie)")
            _window.hide()


def start(url: str):
    """
    Uruchamia pywebview i tworzy natywne okno.
    MUSI być wywołane z głównego wątku na Windows.
    Blokuje wątek do momentu zamknięcia okna.
    """
    global _window

    import webview

    # Tworzymy instancję API do sterowania oknem z poziomu HTML/JS
    api_instance = WindowAPI()

    _window = webview.create_window(
        title="SuppSales Agent",
        url=url,
        width=1280,
        height=820,
        min_size=(900, 600),
        resizable=True,
        hidden=True,            # startuje ukryte, shown po załadowaniu strony
        confirm_close=False,    # X chowa okno zamiast zamykać (obsługiwane przez _on_closing)
        background_color="#0f172a",
        frameless=True,         # Nowoczesne okno bez natywnego obramowania systemu Windows
        js_api=api_instance
    )

    def _on_loaded():
        """Wywoływane gdy strona się załaduje — pokazujemy okno."""
        logger.info("pywebview: strona załadowana, pokazuję okno.")
        _webview_started.set()
        if _window:
            _window.show()

    def _on_closing():
        """
        Wywoływane gdy użytkownik próbuje zamknąć okno.
        Chowamy okno zamiast zamykać aplikację.
        """
        logger.info("pywebview: zamykanie okna -> chowam.")
        if _window:
            _window.hide()
        return False  # False = anuluj zamknięcie okna

    _window.events.loaded += _on_loaded
    _window.events.closing += _on_closing

    logger.info(f"pywebview: start() -> {url}")
    webview.start(debug=False)
    logger.info("pywebview: pętla główna zakończona.")


def show():
    """Pokazuje okno (po ukryciu przez X lub na starcie)."""
    global _window
    if _window is None:
        logger.warning("pywebview: okno nie istnieje.")
        return
    try:
        _window.show()
    except Exception as e:
        logger.error(f"pywebview: błąd show(): {e}")


def hide():
    """Ukrywa okno."""
    global _window
    if _window is None:
        return
    try:
        _window.hide()
    except Exception as e:
        logger.error(f"pywebview: błąd hide(): {e}")


def destroy():
    """
    Zamyka okno i kończy pętlę pywebview.
    Wywoływane przez 'Wyjdź' w zasobniku.
    """
    global _window
    if _window is None:
        return
    try:
        import webview
        # Usuń handler _on_closing żeby okno faktycznie się zamknęło
        _window.events.closing -= lambda: False
        webview.token.set()   # sygnał do zakończenia pętli webview.start()
    except Exception:
        pass
    try:
        _window.destroy()
    except Exception as e:
        logger.error(f"pywebview: błąd destroy(): {e}")
    _window = None
