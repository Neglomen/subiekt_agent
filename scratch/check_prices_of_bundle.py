import win32com.client
import sys

try:
    conn = win32com.client.Dispatch("ADODB.Connection")
    server = r"SERVER\SQL"
    db = "PHU_PATRYK_SIKORA"
    conn_str = f"Provider=SQLOLEDB;Data Source={server};Initial Catalog={db};Integrated Security=SSPI;"
    conn.Open(conn_str)
    
    # Query details of components of bundle 3902
    sql = """
        SELECT
            k.kpl_Liczba  AS quantity,
            t.tw_Id       AS id,
            t.tw_Symbol   AS symbol,
            t.tw_Nazwa    AS name,
            c.tc_CenaBrutto1, c.tc_CenaBrutto2, c.tc_CenaBrutto3, c.tc_CenaBrutto4, c.tc_CenaBrutto5,
            c.tc_CenaNetto1, c.tc_CenaNetto2, c.tc_CenaNetto3, c.tc_CenaNetto4, c.tc_CenaNetto5
        FROM tw_Komplet k
        INNER JOIN tw__Towar t ON k.kpl_IdSkladnik = t.tw_Id
        LEFT JOIN tw_Cena c ON c.tc_IdTowar = t.tw_Id
        WHERE k.kpl_IdKomplet = 3902
    """
    res = conn.Execute(sql)
    rs = res[0]
    while not rs.EOF:
        print(f"Component: {rs.Fields('symbol').Value} (ID: {rs.Fields('id').Value})")
        print(f"  Qty: {rs.Fields('quantity').Value}")
        for i in range(1, 6):
            print(f"  Level {i}: Brutto={rs.Fields(f'tc_CenaBrutto{i}').Value}, Netto={rs.Fields(f'tc_CenaNetto{i}').Value}")
        rs.MoveNext()
    rs.Close()
    
    conn.Close()
except Exception as e:
    import traceback
    traceback.print_exc()
