import win32com.client

conn = win32com.client.Dispatch("ADODB.Connection")
server = "SERVER\\SQL"
db = "PHU_PATRYK_SIKORA"
conn_str = f"Provider=SQLOLEDB;Data Source={server};Initial Catalog={db};Integrated Security=SSPI;"

try:
    conn.Open(conn_str)
    print("Connected successfully!")
    
    rs = win32com.client.Dispatch("ADODB.Recordset")
    rs.Open("SELECT uz_Id, uz_Login, uz_Nazwisko, uz_Imie FROM pd_Uzytkownik", conn)
    print("Operators in Subiekt GT:")
    while not rs.EOF:
        uid = rs.Fields("uz_Id").Value
        login = rs.Fields("uz_Login").Value
        nazwisko = rs.Fields("uz_Nazwisko").Value
        imie = rs.Fields("uz_Imie").Value
        print(f"  ID: {uid}, Login: {login}, Name: {imie} {nazwisko}")
        rs.MoveNext()
    rs.Close()
except Exception as e:
    print("Error:", e)
finally:
    if conn.State == 1:
        conn.Close()
