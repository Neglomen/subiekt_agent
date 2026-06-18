import logging
from decimal import Decimal
from typing import List, Dict

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
            sql_query = f"""
                SELECT dok_Id, dok_NrPelny, dok_WartBrutto 
                FROM dok__Dokument 
                WHERE dok_NrPelnyOryg = '{safe_number}' OR CAST(dok_Uwagi AS VARCHAR(MAX)) LIKE '%{safe_number}%'
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