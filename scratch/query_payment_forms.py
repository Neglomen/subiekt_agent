import win32com.client
from app.config import settings

try:
    conn = win32com.client.Dispatch("ADODB.Connection")
    # Provider can be SQLOLEDB or MSOLEDBSQL
    conn_str = f"Provider=SQLOLEDB;Data Source={settings.sfera.db_server_name};Initial Catalog={settings.sfera.db_name};Integrated Security=SSPI;"
    print("Connecting using conn_str:", conn_str)
    conn.Open(conn_str)
    
    sql = "SELECT fp_Id, fp_Nazwa, fp_Typ FROM sl_FormaPlatnosci"
    rs, _ = conn.Execute(sql)
    print("Formy platnosci:")
    while not rs.EOF:
        fp_id = rs.Fields('fp_Id').Value
        nazwa = rs.Fields('fp_Nazwa').Value
        typ = rs.Fields('fp_Typ').Value
        print(f"  ID={fp_id}, Nazwa='{nazwa}', Typ={typ}")
        rs.MoveNext()
    rs.Close()
    conn.Close()
except Exception as e:
    print("Blad:", e)
