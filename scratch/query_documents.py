import win32com.client
from app.config import settings

try:
    conn = win32com.client.Dispatch("ADODB.Connection")
    conn_str = f"Provider=SQLOLEDB;Data Source={settings.sfera.db_server_name};Initial Catalog={settings.sfera.db_name};Integrated Security=SSPI;"
    conn.Open(conn_str)
    
    # 1. Find all columns in dok__Dokument containing 'ksef'
    print("Columns in dok__Dokument containing 'ksef':")
    sql_cols = """
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = 'dok__Dokument' AND COLUMN_NAME LIKE '%ksef%'
    """
    rs, _ = conn.Execute(sql_cols)
    cols = []
    while not rs.EOF:
        col_name = rs.Fields('COLUMN_NAME').Value
        cols.append(col_name)
        print(f"  {col_name}")
        rs.MoveNext()
    rs.Close()
    
    # 2. Query the last 20 documents of type 2 (FS - Faktura Sprzedaży)
    print("\nLast 20 Sales Invoices (type=2):")
    ksef_cols_str = ", ".join(cols) if cols else ""
    select_fields = "dok_Id, dok_NrPelny, dok_Typ, dok_Podtyp"
    if ksef_cols_str:
        select_fields += ", " + ksef_cols_str
        
    sql_docs = f"""
        SELECT TOP 20 {select_fields}
        FROM dok__Dokument 
        WHERE dok_Typ = 2
        ORDER BY dok_Id DESC
    """
    rs, _ = conn.Execute(sql_docs)
    while not rs.EOF:
        dok_id = rs.Fields('dok_Id').Value
        nr = rs.Fields('dok_NrPelny').Value
        typ = rs.Fields('dok_Typ').Value
        podtyp = rs.Fields('dok_Podtyp').Value
        ksef_vals = {c: rs.Fields(c).Value for c in cols} if cols else {}
        print(f"  ID={dok_id}, Nr={nr}, Typ={typ}, Podtyp={podtyp}, KSeF={ksef_vals}")
        rs.MoveNext()
    rs.Close()
    
    # 3. Let's see if there is any other type of invoice (like 20, 21, etc.)
    print("\nTypes of documents in the system:")
    sql_types = "SELECT DISTINCT dok_Typ, COUNT(*) as cnt FROM dok__Dokument GROUP BY dok_Typ"
    rs, _ = conn.Execute(sql_types)
    while not rs.EOF:
        print(f"  Typ={rs.Fields('dok_Typ').Value}, Count={rs.Fields('cnt').Value}")
        rs.MoveNext()
    rs.Close()
    
    conn.Close()
except Exception as e:
    print("Blad:", e)
