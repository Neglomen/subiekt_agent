import sys
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
    
    print("Connecting to Sfera...")
    subiekt = gt.Uruchom(6)
    if subiekt is None:
        print("Failed to connect.")
        sys.exit(1)
        
    print("Connection Succeeded!")
    mgr = subiekt.SuDokumentyManager
    fs = mgr.DodajFS()
    
    print("\nTesting potential properties on FS object:")
    properties_to_try = [
        'CzekaNaKSeF', 'CzekaNaKsef', 'WyslijDoKSeF', 'dok_CzekaNaKSeF',
        'KSeF', 'Ksef', 'StatusKSeF', 'StatusKsef', 'RodzajKSeF',
        'KseFStatus', 'FormatKSeF', 'ObslugaKSeF', 'DoKSeF', 'DoKsef'
    ]
    for prop in properties_to_try:
        try:
            val = getattr(fs, prop)
            print(f"  [FOUND] {prop}: value={val}, type={type(val)}")
        except Exception as e:
            # print(f"  [ERROR] {prop}: {e}")
            pass
            
    print("\nAttempting to set properties...")
    for prop in properties_to_try:
        try:
            setattr(fs, prop, True)
            print(f"  [SET SUCCESS] Set {prop} to True. Read back value: {getattr(fs, prop)}")
        except Exception as e:
            pass

    fs.Zamknij()
    subiekt.Zakoncz()

except Exception as e:
    print("Error:", e)
