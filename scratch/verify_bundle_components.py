import win32com.client

conn = win32com.client.Dispatch("ADODB.Connection")
server = "SERVER\\SQL"
db = "PHU_PATRYK_SIKORA"
conn_str = f"Provider=SQLOLEDB;Data Source={server};Initial Catalog={db};Integrated Security=SSPI;"

bundle_id = 3902  # ZEST_BM_CZARNY_WPB

try:
    conn.Open(conn_str)
    sql = f"""
        SELECT
            k.kpl_Liczba  AS quantity,
            t.tw_Id       AS id,
            t.tw_Symbol   AS symbol,
            t.tw_Rodzaj   AS type
        FROM tw_Komplet k
        INNER JOIN tw__Towar t ON k.kpl_IdSkladnik = t.tw_Id
        WHERE k.kpl_IdKomplet = {bundle_id}
    """
    rs = win32com.client.Dispatch("ADODB.Recordset")
    rs.Open(sql, conn)
    print(f"Składniki kompletu ID={bundle_id}:")
    components = []
    while not rs.EOF:
        comp = {
            "id":       rs.Fields("id").Value,
            "symbol":   rs.Fields("symbol").Value,
            "quantity": float(rs.Fields("quantity").Value or 1),
            "type":     rs.Fields("type").Value,
        }
        components.append(comp)
        print(f"  -> Symbol: {comp['symbol']}, ID: {comp['id']}, Ilość na komplet: {comp['quantity']}, Rodzaj: {comp['type']}")
        rs.MoveNext()
    rs.Close()
    print(f"\nŁącznie {len(components)} składnik(ów).")
except Exception as e:
    print("Error:", e)
finally:
    if conn.State == 1:
        conn.Close()
