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
    
    def get_bundle_components(self, bundle_id: int) -> List[Dict[str, Any]]:
        """
        Zwraca listę składników kompletu dla podanego ID kompletu wraz z cennikami.

        Dla każdego składnika zwraca słownik:
            - 'id':       tw_Id składnika
            - 'symbol':   tw_Symbol składnika
            - 'quantity': kpl_Liczba (wymagana ilość na 1 komplet)
            - 'type':     tw_Rodzaj składnika
            - 'price_brutto': słownik {level_id: cena_brutto} (poziomy cen 1-10)
            - 'price_netto':  słownik {level_id: cena_netto} (poziomy cen 1-10)

        Args:
            bundle_id: tw_Id kompletu (tw_Rodzaj = 8).

        Returns:
            Lista słowników opisujących składniki, lub pusta lista jeśli brak.
        """
        sql_query = f"""
            SELECT
                k.kpl_Liczba  AS quantity,
                t.tw_Id       AS id,
                t.tw_Symbol   AS symbol,
                t.tw_Rodzaj   AS type,
                ISNULL(c.tc_CenaBrutto1, 0)  AS price_brutto_1,
                ISNULL(c.tc_CenaBrutto2, 0)  AS price_brutto_2,
                ISNULL(c.tc_CenaBrutto3, 0)  AS price_brutto_3,
                ISNULL(c.tc_CenaBrutto4, 0)  AS price_brutto_4,
                ISNULL(c.tc_CenaBrutto5, 0)  AS price_brutto_5,
                ISNULL(c.tc_CenaBrutto6, 0)  AS price_brutto_6,
                ISNULL(c.tc_CenaBrutto7, 0)  AS price_brutto_7,
                ISNULL(c.tc_CenaBrutto8, 0)  AS price_brutto_8,
                ISNULL(c.tc_CenaBrutto9, 0)  AS price_brutto_9,
                ISNULL(c.tc_CenaBrutto10, 0) AS price_brutto_10,
                ISNULL(c.tc_CenaNetto1, 0)   AS price_netto_1,
                ISNULL(c.tc_CenaNetto2, 0)   AS price_netto_2,
                ISNULL(c.tc_CenaNetto3, 0)   AS price_netto_3,
                ISNULL(c.tc_CenaNetto4, 0)   AS price_netto_4,
                ISNULL(c.tc_CenaNetto5, 0)   AS price_netto_5,
                ISNULL(c.tc_CenaNetto6, 0)   AS price_netto_6,
                ISNULL(c.tc_CenaNetto7, 0)   AS price_netto_7,
                ISNULL(c.tc_CenaNetto8, 0)   AS price_netto_8,
                ISNULL(c.tc_CenaNetto9, 0)   AS price_netto_9,
                ISNULL(c.tc_CenaNetto10, 0)  AS price_netto_10
            FROM tw_Komplet k
            INNER JOIN tw__Towar t ON k.kpl_IdSkladnik = t.tw_Id
            LEFT JOIN tw_Cena c ON c.tc_IdTowar = t.tw_Id
            WHERE k.kpl_IdKomplet = {int(bundle_id)}
        """
        ado_recordset = None
        try:
            ado_recordset, _ = self.ado_connection.Execute(sql_query)
            components = []
            while not ado_recordset.EOF:
                price_brutto = {}
                price_netto = {}
                for idx in range(1, 11):
                    price_brutto[idx] = float(ado_recordset.Fields(f"price_brutto_{idx}").Value or 0)
                    price_netto[idx] = float(ado_recordset.Fields(f"price_netto_{idx}").Value or 0)

                components.append({
                    "id":       ado_recordset.Fields("id").Value,
                    "symbol":   ado_recordset.Fields("symbol").Value,
                    "quantity": float(ado_recordset.Fields("quantity").Value or 1),
                    "type":     ado_recordset.Fields("type").Value,
                    "price_brutto": price_brutto,
                    "price_netto": price_netto
                })
                ado_recordset.MoveNext()
            logger.debug(f"get_bundle_components: komplet ID={bundle_id} ma {len(components)} składników.")
            return components
        except Exception as e:
            logger.error(f"Błąd SQL podczas pobierania składników kompletu ID={bundle_id}: {e}", exc_info=True)
            return []
        finally:
            if ado_recordset and ado_recordset.State != 0:
                ado_recordset.Close()

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

        Wykonuje jedno zoptymalizowane zapytanie SQL (CTE) do bazy Subiekta GT.
        Logika zależy od rodzaju kartoteki towaru (tw_Rodzaj):

        - Towary zwykłe (tw_Rodzaj != 8): zwraca rzeczywisty stan netto
          = st_Stan - st_StanRez z tabeli tw_Stan dla danego magazynu.

        - Komplety (tw_Rodzaj = 8): oblicza "wirtualny" dostępny stan na podstawie
          stanów składników. Pobiera stan każdego składnika z tw_Stan, dzieli przez
          wymaganą ilość (kpl_Liczba z tw_Komplet) i bierze minimum = maksymalna
          liczba kompletów możliwych do złożenia z dostępnych stanów.

        Symbole nieznalezione w bazie są zwracane z wartością 0.0.

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
            WITH ProductInfo AS (
                SELECT 
                    tw_Id, 
                    tw_Symbol, 
                    tw_Rodzaj
                FROM tw__Towar
                WHERE tw_Symbol IN ({symbols_sql})
            ),
            ComponentStocks AS (
                SELECT 
                    pi.tw_Symbol AS BundleSymbol,
                    pi.tw_Id AS BundleId,
                    comp.tw_Symbol AS ComponentSymbol,
                    k.kpl_Liczba AS RequiredQty,
                    ISNULL((
                        SELECT SUM(st_Stan - st_StanRez) 
                        FROM tw_Stan 
                        WHERE st_TowId = k.kpl_IdSkladnik AND st_MagId = {int(mag_id)}
                    ), 0) AS ComponentAvailableStock
                FROM ProductInfo pi
                INNER JOIN tw_Komplet k ON pi.tw_Id = k.kpl_IdKomplet
                INNER JOIN tw__Towar comp ON k.kpl_IdSkladnik = comp.tw_Id
                WHERE pi.tw_Rodzaj = 8
            ),
            BundleCalculatedStock AS (
                SELECT 
                    BundleSymbol AS Symbol,
                    MIN(FLOOR(ComponentAvailableStock / RequiredQty)) AS CalculatedStock
                FROM ComponentStocks
                GROUP BY BundleSymbol
            ),
            StandardProductStock AS (
                SELECT 
                    pi.tw_Symbol AS Symbol,
                    ISNULL((
                        SELECT SUM(st_Stan - st_StanRez) 
                        FROM tw_Stan 
                        WHERE st_TowId = pi.tw_Id AND st_MagId = {int(mag_id)}
                    ), 0) AS CalculatedStock
                FROM ProductInfo pi
                WHERE pi.tw_Rodzaj != 8
            )
            SELECT Symbol, CalculatedStock
            FROM StandardProductStock
            UNION ALL
            SELECT Symbol, CalculatedStock
            FROM BundleCalculatedStock;
        """

        logger.debug(
            f"get_bulk_stock: zapytanie o {len(symbols)} symboli w magazynie ID={mag_id}."
        )

        ado_recordset = None
        try:
            ado_recordset, _ = self.ado_connection.Execute(sql_query)

            result: Dict[str, float] = {}
            while not ado_recordset.EOF:
                symbol_val = ado_recordset.Fields("Symbol").Value
                dostepne_val = ado_recordset.Fields("CalculatedStock").Value
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

    def get_bulk_components(self, symbols: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Pobiera składniki kompletów dla podanej listy symboli kompletów za pomocą jednego zapytania SQL.

        Args:
            symbols: Lista symboli kompletów (rodziców).

        Returns:
            Słownik mapujący symbol kompletu na listę słowników z kluczami:
                - 'symbol': symbol składnika
                - 'quantity': wymagana ilość składnika
        """
        if not symbols:
            return {}

        sanitized = [s.replace("'", "") for s in symbols]
        symbols_sql = ", ".join(f"'{s}'" for s in sanitized)

        sql_query = f"""
            SELECT 
                parent.tw_Symbol AS BundleSymbol,
                comp.tw_Symbol AS ComponentSymbol,
                k.kpl_Liczba AS RequiredQty
            FROM tw_Komplet k
            INNER JOIN tw__Towar parent ON k.kpl_IdKomplet = parent.tw_Id
            INNER JOIN tw__Towar comp ON k.kpl_IdSkladnik = comp.tw_Id
            WHERE parent.tw_Symbol IN ({symbols_sql})
        """
        
        ado_recordset = None
        try:
            ado_recordset, _ = self.ado_connection.Execute(sql_query)
            result: Dict[str, List[Dict[str, Any]]] = {s: [] for s in symbols}
            
            while not ado_recordset.EOF:
                bundle_sym = ado_recordset.Fields("BundleSymbol").Value
                comp_sym = ado_recordset.Fields("ComponentSymbol").Value
                qty = float(ado_recordset.Fields("RequiredQty").Value or 0)
                
                if bundle_sym in result:
                    result[bundle_sym].append({
                        "symbol": comp_sym,
                        "quantity": qty
                    })
                ado_recordset.MoveNext()
                
            logger.debug(f"get_bulk_components: pobrano składniki dla {len(result)} symboli kompletów.")
            return result
        except Exception as e:
            logger.error(f"Błąd SQL podczas pobierania składników kompletów bulk: {e}", exc_info=True)
            return {s: [] for s in symbols}
        finally:
            if ado_recordset and ado_recordset.State != 0:
                ado_recordset.Close()