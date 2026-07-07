import win32com.client

conn = win32com.client.Dispatch("ADODB.Connection")
# Using the values from .env
server = "SERVER\\SQL"
db = "PHU_PATRYK_SIKORA"
conn_str = f"Provider=SQLOLEDB;Data Source={server};Initial Catalog={db};Integrated Security=SSPI;"

try:
    conn.Open(conn_str)
    print("Connected successfully!")
    
    # Query tw_Stan columns
    rs = win32com.client.Dispatch("ADODB.Recordset")
    rs.Open("SELECT TOP 1 * FROM tw_Stan", conn)
    fields = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
    print("Columns in tw_Stan:", fields)
    rs.Close()
    
    # Query tw_Komplet columns
    rs.Open("SELECT TOP 1 * FROM tw_Komplet", conn)
    fields_kpl = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
    print("Columns in tw_Komplet:", fields_kpl)
    rs.Close()
    
except Exception as e:
    print("Error:", e)
finally:
    if conn.State == 1:
        conn.Close()
