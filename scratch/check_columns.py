import win32com.client
import json
from app.sfera.sfera_instance import SferaInstance
from app.config import settings

sfera = SferaInstance(settings.sfera)
sfera.connect()

try:
    # Query database to list columns of tw_Stan
    sql = "SELECT TOP 1 * FROM tw_Stan"
    rs, _ = sfera.ado_connection.Execute(sql)
    fields = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
    print("Columns in tw_Stan:", fields)
    rs.Close()

    # Query database to list columns of tw_Komplet
    sql = "SELECT TOP 1 * FROM tw_Komplet"
    rs, _ = sfera.ado_connection.Execute(sql)
    fields_kpl = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
    print("Columns in tw_Komplet:", fields_kpl)
    rs.Close()

except Exception as e:
    print("Error:", e)
finally:
    sfera.disconnect()
