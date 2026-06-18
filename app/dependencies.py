import logging
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from app.config import settings

logger = logging.getLogger(__name__)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_api_key(api_key: str = Security(api_key_header)) -> str:
    """Weryfikuje klucz API i zwraca go."""
    logger.debug(">>> [DEPENDENCY] Sprawdzanie klucza API...")
    if not api_key:
        raise HTTPException(status_code=401, detail="Brak nagłówka X-API-Key.")
    if api_key != settings.sfera.agent_api_key:
        raise HTTPException(status_code=401, detail="Nieprawidłowy klucz API.")
    logger.debug("<<< [DEPENDENCY] Klucz API jest poprawny.")
    return api_key

# Usunęliśmy wszystkie inne zależności (get_sfera_session, get_document_service, etc.)
# oraz protected_deps. Będziemy definiować `Depends(get_api_key)` bezpośrednio w endpointach.