import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class PaymentFormRepository(BaseRepository):
    """Repozytorium do odczytu danych o formach płatności z bazy Subiekta."""

    _cache: List[Dict[str, Any]] = []
    _last_loaded: Optional[datetime] = None
    CACHE_TTL = timedelta(hours=1) # Formy płatności zmieniają się rzadko

    def get_all(self) -> List[Dict[str, Any]]:
        """Zwraca listę wszystkich form płatności, używając cache."""
        now = datetime.now()
        if not self._cache or (self._last_loaded and now - self._last_loaded > self.CACHE_TTL):
            logger.info("PAYMENT CACHE MISS: Odświeżam cache form płatności...")
            ado_recordset = None
            try:
                sql_query = "SELECT fp_Id, fp_Nazwa FROM sl_FormaPlatnosci ORDER BY fp_Nazwa"
                ado_recordset, _ = self.ado_connection.Execute(sql_query)
                
                results = []
                while not ado_recordset.EOF:
                    results.append({
                        "id": ado_recordset.Fields("fp_Id").Value,
                        "name": ado_recordset.Fields("fp_Nazwa").Value,
                    })
                    ado_recordset.MoveNext()
                
                self._cache = results
                self._last_loaded = now
                logger.info(f"PAYMENT CACHE REFRESH: Załadowano {len(results)} form płatności.")
            except Exception as e:
                logger.error(f"Krytyczny błąd podczas odświeżania cache'u form płatności: {e}", exc_info=True)
                return self._cache # Zwróć stary cache w razie błędu
            finally:
                if ado_recordset and ado_recordset.State != 0:
                    ado_recordset.Close()
        else:
            logger.info("PAYMENT CACHE HIT: Używam istniejącego cache form płatności.")
        
        return self._cache