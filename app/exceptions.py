# app/exceptions.py

class SferaConnectionError(Exception):
    """Błąd podczas łączenia lub komunikacji ze Sferą."""
    pass

class InvoiceNotFoundError(Exception):
    """Faktura nie została znaleziona w Subiekcie GT."""
    pass

class OutOfStockValidationError(Exception):
    """Błąd walidacji: brak wystarczającego stanu magazynowego w Subiekcie GT.
    
    Ten wyjątek jest rzucany zamiast SferaConnectionError, gdy COM error z Sfery
    zawiera komunikat 'Brak towaru w magazynie'. Dzięki temu nie jest wywoływany
    kosztowny cykl reconnect workera Sfery, a klient otrzymuje HTTP 422.
    """
    pass