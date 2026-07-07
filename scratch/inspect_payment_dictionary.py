from app.sfera.sfera_instance import SferaInstance
from app.config import settings

sfera = SferaInstance(settings.sfera)
sfera.connect()

try:
    slowniki = sfera.o_subiekt.Slowniki
    karta_dict = slowniki.FormyPlatnosciKarta
    
    # Query database for all forms of payment
    sql = "SELECT fp_Nazwa, fp_Typ FROM sl_FormaPlatnosci"
    rs, _ = sfera.ado_connection.Execute(sql)
    print("Verification of Istnieje in FormyPlatnosciKarta:")
    while not rs.EOF:
        nazwa = rs.Fields("fp_Nazwa").Value
        typ = rs.Fields("fp_Typ").Value
        exists = karta_dict.Istnieje(nazwa)
        print(f"  Nazwa='{nazwa}' (Typ={typ}) -> FormyPlatnosciKarta.Istnieje = {exists}")
        rs.MoveNext()
    rs.Close()

except Exception as e:
    print("Blad:", e)
finally:
    sfera.disconnect()
