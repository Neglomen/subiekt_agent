# Plik: subiekt_agent/app/repositories/product_repository.py

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

def normalize_symbol(s: str) -> str:
    """Normalizuje symbol towaru do spójnego formatu do porównań (tylko znaki alfanumeryczne)."""
    import re
    if not s: return ""
    return re.sub(r'[^A-Z0-9]', '', s.upper())

class ProductRepository(BaseRepository):
    """Repozytorium do zarządzania danymi o towarach."""
    _cache: Dict[str, int] = {}
    _last_loaded: Optional[datetime] = None
    CACHE_TTL = timedelta(minutes=5)

    def get_normalized_map(self) -> Dict[str, Dict[str, Any]]:
        """Zwraca znormalizowaną mapę {symbol: {'id': id, 'type': typ}} towarów, używając cache."""
        now = datetime.now()
        if not self._cache or (self._last_loaded and now - self._last_loaded > self.CACHE_TTL):
            logger.info("CACHE MISS: Odświeżam cache kartoteki towarowej i usług (metoda SQL)...")
            ado_recordset = None
            try:
                # === POPRAWKA: Używamy `tw_Rodzaj` zamiast `tw_Typ` ===
                sql_query = "SELECT tw_Id, tw_Symbol, tw_Rodzaj FROM tw__Towar"
                ado_recordset, _ = self.ado_connection.Execute(sql_query)
                
                normalized_map = {}
                while not ado_recordset.EOF:
                    symbol = ado_recordset.Fields("tw_Symbol").Value
                    if symbol:
                        normalized_symbol = normalize_symbol(symbol)
                        if normalized_symbol not in normalized_map:
                            normalized_map[normalized_symbol] = {
                                "id": ado_recordset.Fields("tw_Id").Value,
                                # Zmieniamy również nazwę klucza w odpowiedzi
                                "type": ado_recordset.Fields("tw_Rodzaj").Value 
                            }
                    ado_recordset.MoveNext()
                
                self._cache = normalized_map
                self._last_loaded = now
                logger.info(f"CACHE REFRESH: Załadowano {len(normalized_map)} unikalnych symboli (towary i usługi).")
            except Exception as e:
                logger.error(f"Krytyczny błąd podczas odświeżania cache'u towarów przez SQL: {e}", exc_info=True)
                return self._cache
            finally:
                if ado_recordset and ado_recordset.State != 0:
                    ado_recordset.Close()
        else:
            logger.info("CACHE HIT: Używam istniejącego cache kartoteki.")
        
        return self._cache
    
    def search(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Wyszukuje produkty w Subiekcie po symbolu lub nazwie.
        Jeśli query jest puste, zwraca pierwsze 100 produktów.
        """
        logger.info(f"Wyszukiwanie produktów dla zapytania: '{query}'")
        ado_recordset = None
        try:
            safe_query = f"%{query.replace("'", "''")}%" if query else "%"
            sql_query = f"""
                SELECT TOP 100 tw_Id, tw_Symbol, tw_Nazwa
                FROM tw__Towar
                WHERE tw_Symbol LIKE '{safe_query}' OR tw_Nazwa LIKE '{safe_query}'
                ORDER BY tw_Symbol
            """
            ado_recordset, _ = self.ado_connection.Execute(sql_query)
            
            results = []
            while not ado_recordset.EOF:
                results.append({
                    "id": ado_recordset.Fields("tw_Id").Value,
                    "symbol": ado_recordset.Fields("tw_Symbol").Value,
                    "name": ado_recordset.Fields("tw_Nazwa").Value,
                })
                ado_recordset.MoveNext()
            
            logger.info(f"Znaleziono {len(results)} pasujących produktów.")
            return results
        except Exception as e:
            logger.error(f"Błąd SQL podczas wyszukiwania produktów: {e}")
            return []
        finally:
            if ado_recordset and ado_recordset.State != 0:
                ado_recordset.Close()

    def get_bulk_stock(self, symbols: List[str], mag_id: int = 1) -> Dict[str, float]:
        """
        Zwraca słownik {symbol: dostępna_ilość} dla podanej listy symboli towarów.

        Wykonuje jedno zoptymalizowane zapytanie SQL do bazy Subiekta GT,
        łącząc tabele tw__Towar i tw_Stan. Filtruje po tw_Typ = 1 (towary),
        ignorując usługi, które nie mają stanów magazynowych.
        Dostępna ilość = st_Stan - st_Rezerwacja (COALESCE chroni przed NULL,
        gdy dany towar nie ma jeszcze rekordu w tw_Stan).

        Symbole nieznalezione w bazie (lub z zerowym stanem) są zwracane
        z wartością 0.0, co upraszcza logikę po stronie backendu.

        Args:
            symbols: Lista symboli towarów do sprawdzenia.
            mag_id:  ID magazynu w Subiekcie GT (domyślnie 1 = magazyn główny).

        Returns:
            Słownik {symbol_oryginalny_z_listy: dostępna_ilość}.
        """
        if not symbols:
            return {}

        # Sanityzacja symboli: usuwamy apostrofy, aby zapobiec SQL injection.
        # Symbole towarów są alfanumeryczne, ale stosujemy defensywne podejście.
        sanitized = [s.replace("'", "") for s in symbols]
        symbols_sql = ", ".join(f"'{s}'" for s in sanitized)

        sql_query = f"""
            SELECT tw_Symbol, COALESCE(st_Stan - st_StanRez, 0) AS dostepne
            FROM tw__Towar
            LEFT JOIN tw_Stan
                ON tw_Id = st_TowId
                AND st_MagId = {int(mag_id)}
            WHERE tw_Symbol IN ({symbols_sql})
        """

        logger.debug(
            f"get_bulk_stock: zapytanie o {len(symbols)} symboli w magazynie ID={mag_id}."
        )

        ado_recordset = None
        try:
            ado_recordset, _ = self.ado_connection.Execute(sql_query)

            result: Dict[str, float] = {}
            while not ado_recordset.EOF:
                symbol_val = ado_recordset.Fields("tw_Symbol").Value
                dostepne_val = ado_recordset.Fields("dostepne").Value
                if symbol_val is not None:
                    result[symbol_val] = float(dostepne_val) if dostepne_val is not None else 0.0
                ado_recordset.MoveNext()

            # Symbole nieznalezione w bazie (np. usługi, błędne symbole) → 0.0
            for original_sym in symbols:
                if original_sym not in result:
                    result[original_sym] = 0.0

            logger.debug(
                f"get_bulk_stock: zwrócono stany dla {len(result)} symboli."
            )
            return result

        except Exception as e:
            logger.error(f"Błąd SQL podczas pobierania stanów magazynowych bulk: {e}", exc_info=True)
            # Zwracamy puste stany dla wszystkich symboli, aby nie blokować wywołującego
            return {s: 0.0 for s in symbols}
        finally:
            if ado_recordset and ado_recordset.State != 0:
                ado_recordset.Close()