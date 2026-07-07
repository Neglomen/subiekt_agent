import win32com.client
import sys

try:
    conn = win32com.client.Dispatch("ADODB.Connection")
    server = r"SERVER\SQL"
    db = "PHU_PATRYK_SIKORA"
    conn_str = f"Provider=SQLOLEDB;Data Source={server};Initial Catalog={db};Integrated Security=SSPI;"
    conn.Open(conn_str)
    
    # Query tw_Cena table definition
    res = conn.Execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'tw_Cena'")
    rs = res[0]
    while not rs.EOF:
        print(f"{rs.Fields('COLUMN_NAME').Value}: {rs.Fields('DATA_TYPE').Value}")
        rs.MoveNext()
    rs.Close()
    
    # Also select a sample row from tw_Cena
    print("\nSample row from tw_Cena:")
    res = conn.Execute("SELECT TOP 1 * FROM tw_Cena")
    rs = res[0]
    if not rs.EOF:
        for i in range(rs.Fields.Count):
            field = rs.Fields(i)
            print(f"{field.Name}: {field.Value}")
    rs.Close()
    
    conn.Close()
except Exception as e:
    import traceback
    traceback.print_exc()
