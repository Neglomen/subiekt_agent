import win32com.client
from app.config import settings

try:
    gt = win32com.client.Dispatch("InsERT.GT")
    gt.Produkt = 1
    gt.Autentykacja = 0
    gt.Serwer = settings.sfera.db_server_name
    gt.Baza = settings.sfera.db_name
    gt.Operator = settings.sfera.sfera_operator
    gt.OperatorHaslo = settings.sfera.sfera_operator_password
    
    print("Attempting to connect...")
    subiekt = gt.Uruchom(6)
    if subiekt is None:
        code = gt.GetLastError()
        msg = gt.GetError_vb(code)
        print(f"Connection Failed. Error Code: {code}, Msg: {msg}")
    else:
        print("Connection Succeeded!")
        subiekt.Zakoncz()
except Exception as e:
    print("Exception occurred:", e)
