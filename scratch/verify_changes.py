"""
Skrypt weryfikacyjny:
- Sprawdza pobieranie form płatności (id + type)
- Sprawdza aktualizację dok_CzekaNaKSeF dla ostatniej FS
"""
import win32com.client
from app.config import settings

try:
    conn = win32com.client.Dispatch("ADODB.Connection")
    conn_str = (
        f"Provider=SQLOLEDB;Data Source={settings.sfera.db_server_name};"
        f"Initial Catalog={settings.sfera.db_name};Integrated Security=SSPI;"
    )
    conn.Open(conn_str)

    # --- Test 1: pobieranie form płatności z typem ---
    print("=" * 60)
    print("TEST 1: Formy płatności (id + type)")
    print("=" * 60)
    rs, _ = conn.Execute("SELECT fp_Id, fp_Nazwa, fp_Typ FROM sl_FormaPlatnosci")
    while not rs.EOF:
        fp_id   = rs.Fields("fp_Id").Value
        nazwa   = rs.Fields("fp_Nazwa").Value
        fp_typ  = rs.Fields("fp_Typ").Value
        label   = {0: "Odroczony", 1: "Karta (sprzedaż)", 2: "Karta (zakup)", 3: "Kredyt"}.get(fp_typ, f"Typ {fp_typ}")
        print(f"  ID={fp_id:2d}  Typ={fp_typ} ({label:<20})  Nazwa='{nazwa}'")
        rs.MoveNext()
    rs.Close()

    # --- Test 2: pobranie ostatniej FS i sprawdzenie CzekaNaKSeF ---
    print()
    print("=" * 60)
    print("TEST 2: Ostatnie 5 FS i ich flaga dok_CzekaNaKSeF")
    print("=" * 60)
    sql = """
        SELECT TOP 5 dok_Id, dok_NrPelny, dok_CzekaNaKSeF, dok_StatusKSeF
        FROM dok__Dokument
        WHERE dok_Typ = 2
        ORDER BY dok_Id DESC
    """
    rs, _ = conn.Execute(sql)
    while not rs.EOF:
        print(
            f"  ID={rs.Fields('dok_Id').Value}  "
            f"Nr={rs.Fields('dok_NrPelny').Value}  "
            f"CzekaNaKSeF={rs.Fields('dok_CzekaNaKSeF').Value}  "
            f"StatusKSeF={rs.Fields('dok_StatusKSeF').Value}"
        )
        rs.MoveNext()
    rs.Close()

    # --- Test 3: weryfikacja config ksef_enabled ---
    print()
    print("=" * 60)
    print("TEST 3: Konfiguracja ksef_enabled")
    print("=" * 60)
    from app.config import load_config
    cfg = load_config()
    print(f"  ksef_enabled = {cfg.mappings.ksef_enabled}")
    print(f"  payment_type_mappings = {cfg.mappings.payment_type_mappings}")

    conn.Close()
    print()
    print("Wszystkie testy zakończone pomyślnie.")

except Exception as e:
    print("BŁĄD:", e)
