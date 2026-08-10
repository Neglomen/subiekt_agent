# Plik: subiekt_agent/app/utils.py

import ssl
import urllib.request
import urllib.error
import logging
import sys

logger = logging.getLogger(__name__)

def get_windows_ssl_context() -> ssl.SSLContext:
    """
    Tworzy domyślny kontekst SSL i wczytuje certyfikaty z magazynów systemowych Windows (CA i ROOT).
    Zapobiega to błędom SSL w środowisku skompilowanym za pomocą PyInstaller.
    """
    context = ssl.create_default_context()
    if sys.platform == "win32" and hasattr(ssl, "enum_certificates"):
        logger.debug("Wykryto system Windows, wczytuję certyfikaty z magazynu systemowego...")
        loaded_count = 0
        for storename in ["CA", "ROOT"]:
            try:
                for cert, encoding, trust in ssl.enum_certificates(storename):
                    if encoding == "x509_asn":
                        try:
                            context.load_verify_locations(cadata=cert)
                            loaded_count += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Błąd podczas wczytywania certyfikatów z magazynu {storename}: {e}")
        logger.info(f"Załadowano {loaded_count} certyfikatów systemowych Windows do kontekstu SSL.")
    return context

def urlopen_with_fallback(req, ignore_ssl: bool = False, **kwargs):
    """
    Wykonuje zapytanie HTTP(S) za pomocą urllib.request.urlopen.
    Obsługuje automatyczne wczytywanie systemowych certyfikatów Windows.
    Jeśli weryfikacja SSL nie powiedzie się:
      - jeśli ignore_ssl=True: ignoruje błąd, loguje ostrzeżenie i ponawia z ssl._create_unverified_context().
      - jeśli ignore_ssl=False: zgłasza błąd z jasnym komunikatem dla użytkownika o możliwości
        włączenia opcji 'ignore_ssl_errors': true w pliku config.json lub w GUI.
    """
    # Zawsze domyślnie próbujemy z bezpiecznym kontekstem zawierającym certyfikaty systemowe
    if 'context' not in kwargs:
        try:
            kwargs['context'] = get_windows_ssl_context()
        except Exception as e:
            logger.warning(f"Nie udało się utworzyć rozszerzonego kontekstu SSL: {e}. Używam domyślnego.")

    try:
        return urllib.request.urlopen(req, **kwargs)
    except (urllib.error.URLError, ssl.SSLError, Exception) as e:
        err_msg = str(e).lower()
        is_ssl_err = False
        
        # Weryfikacja czy to błąd certyfikatu SSL
        if isinstance(e, urllib.error.URLError):
            reason_msg = str(e.reason).lower()
            if any(term in reason_msg for term in ["ssl", "cert", "verify", "handshake", "certificate"]):
                is_ssl_err = True
        elif any(term in err_msg for term in ["ssl", "cert", "verify", "handshake", "certificate"]):
            is_ssl_err = True
            
        if is_ssl_err:
            if ignore_ssl:
                logger.warning(
                    f"Weryfikacja certyfikatu SSL nie powiodła się: {e}. "
                    "Ponawiam próbę z pominięciem weryfikacji SSL (opcja ignore_ssl_errors jest włączona)..."
                )
                try:
                    context = ssl._create_unverified_context()
                    kwargs['context'] = context
                    return urllib.request.urlopen(req, **kwargs)
                except Exception as retry_err:
                    logger.error(f"Próba bez weryfikacji SSL również się nie powiodła: {retry_err}")
                    raise retry_err
            else:
                # Informujemy użytkownika o możliwości włączenia ignore_ssl_errors
                msg = (
                    f"Błąd SSL: {e}. Jeśli jesteś w bezpiecznej sieci prywatnej "
                    "i chcesz pominąć weryfikację certyfikatów SSL, możesz włączyć opcję "
                    "'Ignoruj błędy SSL' w zakładce 'System' w konfiguracji agenta."
                )
                logger.error(msg)
                raise Exception(msg) from e
        # Jeśli to nie błąd SSL, rzucamy oryginalny wyjątek
        raise
