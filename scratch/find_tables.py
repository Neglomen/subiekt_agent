import win32com.client
import sys

try:
    conn = win32com.client.Dispatch("ADODB.Connection")
    server = r"SERVER\SQL"
    db = "PHU_PATRYK_SIKORA"
    conn_str = f"Provider=SQLOLEDB;Data Source={server};Initial Catalog={db};Integrated Security=SSPI;"
    print("Connecting...")
    conn.Open(conn_str)
    print("Connected successfully!")
    
    # Let's list some tables
    res = conn.Execute("SELECT TOP 50 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_NAME")
    rs = res[0]
    print("Tables list:")
    while not rs.EOF:
        print(rs.Fields('TABLE_NAME').Value)
        rs.MoveNext()
    rs.Close()
    
    # Check if tw_Cena or similar exists
    print("\nSearching for Cena/Cennik tables...")
    res = conn.Execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE '%cena%' OR TABLE_NAME LIKE '%Cena%'")
    rs = res[0]
    while not rs.EOF:
        print("Found:", rs.Fields('TABLE_NAME').Value)
        rs.MoveNext()
    rs.Close()
    
    conn.Close()
except Exception as e:
    import traceback
    traceback.print_exc()
