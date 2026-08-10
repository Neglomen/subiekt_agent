import logging
from decimal import Decimal
from typing import List, Dict, Optional

import win32com.client

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)

class DocumentRepository(BaseRepository):
    """
    Repozytorium do odczytu danych o dokumentach bezpośrednio z bazy danych Subiekta.
    """

    def find_by_original_number(self, original_invoice_number: str) -> List[Dict]:
        """
        Wyszukuje dokumenty po numerze oryginalnym (dok_NrPelnyOryg) za pomocą SQL.
        Zwraca kluczowe dane, w tym ID dokumentu potrzebne do dalszych zapytań.
        """
        ado_recordset = None
        try:
            # Zabezpieczenie przed SQL Injection
            safe_number = original_invoice_number.replace("'", "''")

            # 1. Szybka ścieżka (indeksowana): Szukamy w dok_NrPelnyOryg
            sql_query = f"""
                SELECT dok_Id, dok_NrPelny, dok_WartBrutto 
                FROM dok__Dokument 
                WHERE dok_NrPelnyOryg = '{safe_number}'
            """
            ado_recordset, _ = self.ado_connection.Execute(sql_query)
            
            results = []
            while not ado_recordset.EOF:
                results.append({
                    "doc_id": ado_recordset.Fields("dok_Id").Value,
                    "doc_number": ado_recordset.Fields("dok_NrPelny").Value,
                    "total_gross": Decimal(str(ado_recordset.Fields("dok_WartBrutto").Value))
                })
                ado_recordset.MoveNext()
            
            ado_recordset.Close()
            ado_recordset = None

            # 2. Wolniejsza ścieżka (fallback dla starych zamówień w Uwagi)
            # Ograniczamy do ostatnich 90 dni dla wydajności (unika pełnego skanowania tabeli)
            if not results:
                sql_query_fallback = f"""
                    SELECT dok_Id, dok_NrPelny, dok_WartBrutto 
                    FROM dok__Dokument 
                    WHERE dok_Uwagi LIKE '%{safe_number}%' 
                      AND dok_DataWyst >= GETDATE() - 90
                """
                ado_recordset, _ = self.ado_connection.Execute(sql_query_fallback)
                while not ado_recordset.EOF:
                    results.append({
                        "doc_id": ado_recordset.Fields("dok_Id").Value,
                        "doc_number": ado_recordset.Fields("dok_NrPelny").Value,
                        "total_gross": Decimal(str(ado_recordset.Fields("dok_WartBrutto").Value))
                    })
                    ado_recordset.MoveNext()

            return results
        finally:
            if ado_recordset and ado_recordset.State != 0:
                ado_recordset.Close()

    def get_line_items_by_doc_id(self, doc_id: int) -> List[Dict]:
        """
        Pobiera pozycje (towary i ilości) dla danego ID dokumentu.
        """
        ado_recordset = None
        db_name = self._sfera.settings.db_name
        try:
            sql_query = f"""
                SELECT T.tw_Symbol, P.ob_Ilosc AS Ilosc
                FROM [{db_name}].[dbo].[dok_Pozycja] AS P
                JOIN [{db_name}].[dbo].[tw__Towar] AS T ON P.ob_TowId = T.tw_Id
                WHERE P.ob_DokHanId = {doc_id}
            """
            ado_recordset, _ = self.ado_connection.Execute(sql_query)

            results = []
            while not ado_recordset.EOF:
                results.append({
                    "symbol": ado_recordset.Fields("tw_Symbol").Value,
                    "quantity": Decimal(str(ado_recordset.Fields("Ilosc").Value)),
                })
                ado_recordset.MoveNext()
            return results
        finally:
            if ado_recordset and ado_recordset.State != 0:
                ado_recordset.Close()

    def find_fz_by_number_and_nip(self, corrected_invoice_number: str, supplier_nip: str) -> List[Dict]:
        """
        Wyszukuje fakturę zakupową (FZ, typ 5) po jej numerze oryginalnym i NIP-ie dostawcy.
        """
        import re
        clean_nip = re.sub(r'\D', '', supplier_nip)
        if supplier_nip.upper().startswith("PL"):
            clean_nip = re.sub(r'\D', '', supplier_nip[2:])
            
        safe_number = corrected_invoice_number.replace("'", "''")
        
        sql_query = f"""
            SELECT d.dok_Id, d.dok_NrPelny, d.dok_WartBrutto 
            FROM dok__Dokument d
            JOIN kh__Kontrahent k ON d.dok_PlatnikId = k.kh_Id
            JOIN adr__Ewid a ON a.adr_IdObiektu = k.kh_Id AND a.adr_TypAdresu = 1
            WHERE d.dok_Typ = 1
              AND (d.dok_NrPelnyOryg = '{safe_number}' OR d.dok_NrPelny = '{safe_number}')
              AND REPLACE(REPLACE(a.adr_Nip, '-', ''), ' ', '') = '{clean_nip}'
        """
        
        ado_recordset = None
        results = []
        try:
            logger.debug(f"Wyszukiwanie FZ: {sql_query}")
            ado_recordset, _ = self.ado_connection.Execute(sql_query)
            while not ado_recordset.EOF:
                results.append({
                    "doc_id": ado_recordset.Fields("dok_Id").Value,
                    "doc_number": ado_recordset.Fields("dok_NrPelny").Value,
                    "total_gross": Decimal(str(ado_recordset.Fields("dok_WartBrutto").Value))
                })
                ado_recordset.MoveNext()
        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania FZ po numerze i NIP: {e}")
        finally:
            if ado_recordset and ado_recordset.State != 0:
                ado_recordset.Close()
        return results

    def find_fs_by_number_or_order(self, doc_number: Optional[str], order_number: Optional[str]) -> List[Dict]:
        """
        Wyszukuje fakturę sprzedaży (FS, typ 2) po jej pełnym numerze lub numerze zamówienia.
        """
        conditions = []
        if doc_number:
            safe_doc_num = doc_number.replace("'", "''")
            conditions.append(f"d.dok_NrPelny = '{safe_doc_num}'")
        if order_number:
            safe_order_num = order_number.replace("'", "''")
            conditions.append(f"d.dok_NrPelnyOryg = '{safe_order_num}'")
            conditions.append(f"d.dok_Uwagi LIKE '%{safe_order_num}%'")
            
        if not conditions:
            return []
            
        sql_query = f"""
            SELECT d.dok_Id, d.dok_NrPelny, d.dok_WartBrutto 
            FROM dok__Dokument d
            WHERE d.dok_Typ = 2 AND ({' OR '.join(conditions)})
        """
        
        ado_recordset = None
        results = []
        try:
            logger.debug(f"Wyszukiwanie FS: {sql_query}")
            ado_recordset, _ = self.ado_connection.Execute(sql_query)
            while not ado_recordset.EOF:
                results.append({
                    "doc_id": ado_recordset.Fields("dok_Id").Value,
                    "doc_number": ado_recordset.Fields("dok_NrPelny").Value,
                    "total_gross": Decimal(str(ado_recordset.Fields("dok_WartBrutto").Value))
                })
                ado_recordset.MoveNext()
        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania FS: {e}")
        finally:
            if ado_recordset and ado_recordset.State != 0:
                ado_recordset.Close()
        return results