import win32com.client
from app.config import settings

try:
    conn = win32com.client.Dispatch("ADODB.Connection")
    conn_str = f"Provider=SQLOLEDB;Data Source={settings.sfera.db_server_name};Initial Catalog={settings.sfera.db_name};Integrated Security=SSPI;"
    conn.Open(conn_str)
    
    # Let's count how many documents have dok_CzekaNaKSeF = 1
    sql_count = "SELECT COUNT(*) as cnt FROM dok__Dokument WHERE dok_CzekaNaKSeF = 1"
    rs, _ = conn.Execute(sql_count)
    print("Number of documents with dok_CzekaNaKSeF = 1:", rs.Fields('cnt').Value)
    rs.Close()
    
    # Query a few documents with dok_CzekaNaKSeF = 1
    sql_docs = """
        SELECT TOP 5 dok_Id, dok_NrPelny, dok_Typ, dok_Podtyp, dok_CzekaNaKSeF, dok_StatusKSeF
        FROM dok__Dokument 
        WHERE dok_CzekaNaKSeF = 1
        ORDER BY dok_Id DESC
    """
    rs, _ = conn.Execute(sql_docs)
    print("\nDocuments with dok_CzekaNaKSeF = 1:")
    while not rs.EOF:
        print(f"  ID={rs.Fields('dok_Id').Value}, Nr={rs.Fields('dok_NrPelny').Value}, "
              f"Typ={rs.Fields('dok_Typ').Value}, Podtyp={rs.Fields('dok_Podtyp').Value}, "
              f"CzekaNaKSeF={rs.Fields('dok_CzekaNaKSeF').Value}, StatusKSeF={rs.Fields('dok_StatusKSeF').Value}")
        rs.MoveNext()
    rs.Close()
    
    # Let's count document KSeF statuses
    sql_statuses = "SELECT dok_StatusKSeF, COUNT(*) as cnt FROM dok__Dokument GROUP BY dok_StatusKSeF"
    rs, _ = conn.Execute(sql_statuses)
    print("\nKSeF statuses in database:")
    while not rs.EOF:
        print(f"  Status={rs.Fields('dok_StatusKSeF').Value}, Count={rs.Fields('cnt').Value}")
        rs.MoveNext()
    rs.Close()
    
    conn.Close()
except Exception as e:
    print("Blad:", e)
