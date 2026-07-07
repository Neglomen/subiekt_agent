import win32com.client

conn = win32com.client.Dispatch("ADODB.Connection")
server = "SERVER\\SQL"
db = "PHU_PATRYK_SIKORA"
conn_str = f"Provider=SQLOLEDB;Data Source={server};Initial Catalog={db};Integrated Security=SSPI;"

component_ids = [3900, 3901, 3960]
ids_sql = ", ".join(str(i) for i in component_ids)

try:
    conn.Open(conn_str)
    rs = win32com.client.Dispatch("ADODB.Recordset")

    # Znajdź wszystkie tabele zawierające 'cen' lub 'twc' lub 'price' w nazwie
    rs.Open("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
          AND (TABLE_NAME LIKE '%cen%' OR TABLE_NAME LIKE 'twc%' OR TABLE_NAME LIKE '%price%')
        ORDER BY TABLE_NAME
    """, conn)
    print("Tabele z 'cen'/'twc':")
    while not rs.EOF:
        print(" ", rs.Fields("TABLE_NAME").Value)
        rs.MoveNext()
    rs.Close()

    # Sprawdź tw__Towar — może zawiera kolumny cen bezpośrednio
    rs.Open(f"SELECT TOP 1 * FROM tw__Towar WHERE tw_Id IN ({ids_sql})", conn)
    col_names = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
    print("\nKolumny tw__Towar zawierające 'cen' lub 'brutto' lub 'netto':")
    for c in col_names:
        if any(k in c.lower() for k in ['cen', 'brutto', 'netto', 'price']):
            print(f"  {c} = {rs.Fields(c).Value}")
    rs.Close()

except Exception as e:
    print("Error:", e)
    import traceback; traceback.print_exc()
finally:
    if conn.State == 1:
        conn.Close()
