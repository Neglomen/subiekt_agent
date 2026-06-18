# -*- coding: utf-8 -*-
import win32com.client
from app.config import settings

try:
    conn = win32com.client.Dispatch("ADODB.Connection")
    conn_str = f"Provider=SQLOLEDB;Data Source={settings.sfera.db_server_name};Initial Catalog={settings.sfera.db_name};Integrated Security=SSPI;"
    conn.Open(conn_str)
    
    sql = "SELECT TOP 10 * FROM uf_Konfiguracja"
    rs, _ = conn.Execute(sql)
    
    # Print column names
    cols = [rs.Fields.Item(i).Name for i in range(rs.Fields.Count)]
    print("Kolumny:", cols)
    
    while not rs.EOF:
        row = [rs.Fields.Item(i).Value for i in range(rs.Fields.Count)]
        print(row)
        rs.MoveNext()
        
    rs.Close()
    conn.Close()
except Exception as e:
    print("Blad:", e)
