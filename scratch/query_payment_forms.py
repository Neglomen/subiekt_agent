# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import win32com.client
from app.config import settings

TARGET = "Pobranie Kurier DPD"

try:
    conn = win32com.client.Dispatch("ADODB.Connection")
    conn_str = (
        f"Provider=SQLOLEDB;"
        f"Data Source={settings.sfera.db_server_name};"
        f"Initial Catalog={settings.sfera.db_name};"
        f"Integrated Security=SSPI;"
    )
    conn.Open(conn_str)

    sql = "SELECT fp_Id, fp_Nazwa, fp_Typ FROM sl_FormaPlatnosci ORDER BY fp_Id"
    rs, _ = conn.Execute(sql)

    print(f"\n{'ID':>4}  {'Typ':>3}  {'Nazwa':<40}  repr(Nazwa)")
    print("-" * 90)

    match_found = False
    while not rs.EOF:
        fp_id  = rs.Fields('fp_Id').Value
        nazwa  = rs.Fields('fp_Nazwa').Value
        typ    = rs.Fields('fp_Typ').Value
        marker = "  <-- SZUKANA" if nazwa and nazwa.upper() == TARGET.upper() else ""
        if marker:
            match_found = True
        print(f"  {fp_id:>4}  {typ:>3}  {str(nazwa):<40}  {repr(nazwa)}{marker}")
        rs.MoveNext()

    rs.Close()
    conn.Close()

    print()
    if match_found:
        print(f"[OK] Znaleziono forme platnosci '{TARGET}' w bazie Subiektu.")
    else:
        print(f"[!!] NIE znaleziono '{TARGET}' w bazie. Sprawdz nazwe!")
        print(f"     Szukano (upper): '{TARGET.upper()}'")

except Exception as e:
    print("Blad:", e)
