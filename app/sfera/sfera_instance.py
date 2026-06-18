# Plik: subiekt_agent/app/sfera/sfera_instance.py

import logging
import win32com.client
import pythoncom
import pywintypes

from app.config import SferaSettings
from app.exceptions import SferaConnectionError

logger = logging.getLogger(__name__)

class SferaInstance:
    """
    Zarządza pojedynczą instancją i cyklem życia połączenia ze Sferą GT.
    Ta klasa hermetyzuje obiekt COM.
    """
    def __init__(self, settings: SferaSettings):
        self.settings = settings
        self.o_subiekt = None
        self.is_connected = False
        logger.info("Instancja SferaInstance została utworzona (bez połączenia).")

    def connect(self):
        """Nawiązuje połączenie z instancją Subiekta GT."""
        if self.is_connected:
            logger.debug("Połączenie ze Sferą jest już aktywne.")
            return

        try:
            pythoncom.CoInitialize()
            gt = win32com.client.Dispatch("InsERT.GT")
            gt.Produkt = 1
            gt.Autentykacja = 0
            gt.Serwer = self.settings.db_server_name
            gt.Baza = self.settings.db_name
            gt.Operator = self.settings.sfera_operator
            gt.OperatorHaslo = self.settings.sfera_operator_password
            
            self.o_subiekt = gt.Uruchom(6)  # Tryb cichy

            if self.o_subiekt is None or (hasattr(gt, 'GetLastError') and gt.GetLastError() != 0):
                error_code = gt.GetLastError() if hasattr(gt, 'GetLastError') else 'N/A'
                error_message = gt.GetError_vb(error_code) if hasattr(gt, 'GetError_vb') else 'Brak opisu.'
                raise SferaConnectionError(f"Nie udało się uruchomić Sfery. Kod: {error_code}. Opis: {error_message}")

            self.is_connected = True
            logger.info("Pomyślnie połączono ze Sferą Subiekta GT.")
        except pywintypes.com_error as e:
            self.is_connected = False
            logger.exception("Błąd COM podczas łączenia ze Sferą.")
            raise SferaConnectionError(f"Błąd COM podczas łączenia: {e.strerror}")
        except Exception as e:
            self.is_connected = False
            logger.exception("Krytyczny błąd podczas łączenia ze Sferą.")
            raise SferaConnectionError(f"Krytyczny błąd: {e}")

    def reconnect(self):
        """Rozłącza i ponownie nawiązuje połączenie ze Sferą."""
        logger.warning("Próba ponownego połączenia ze Sferą...")
        try:
            self.disconnect()
        except Exception:
            pass
        finally:
            self.o_subiekt = None
            self.is_connected = False
        self.connect()

    def disconnect(self):
        """Zamyka połączenie ze Sferą."""
        if self.o_subiekt:
            try:
                self.o_subiekt.Zakoncz()
                logger.info("Połączenie ze Sferą zostało zamknięte.")
            except Exception as e:
                logger.error(f"Błąd podczas zamykania połączenia ze Sferą: {e}")
            finally:
                self.o_subiekt = None
                self.is_connected = False

    @property
    def ado_connection(self):
        """Zwraca aktywne połączenie ADO do bazy danych."""
        if not self.is_connected or not self.o_subiekt:
            raise SferaConnectionError("Brak aktywnego połączenia ze Sferą do pobrania ADO.")
        try:
            return self.o_subiekt.Baza.Polaczenie
        except AttributeError as e:
            # Gdy o_subiekt jest obiektem Uruchom (launcher), a nie sesją,
            # to atrybut 'Baza' nie istnieje -> Sfera się rozłączyła.
            logger.error(f"Wykryto utratę sesji Sfery (błąd: {e}). Oznaczam jako rozłączone.")
            self.is_connected = False
            self.o_subiekt = None
            raise SferaConnectionError(f"Sfera utraciła sesję ({e}). Przetwórz zadanie ponownie po chwili.")