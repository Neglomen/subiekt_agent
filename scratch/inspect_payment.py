import win32com.client
from app.sfera.sfera_instance import SferaInstance
from app.config import settings

sfera = SferaInstance(settings.sfera)
sfera.connect()

try:
    print("o_subiekt type:", type(sfera.o_subiekt))
    slowniki = sfera.o_subiekt.Slowniki
    print("Slowniki attributes:")
    for prop in ['FormyPlatnosciKarta', 'FormyPlatnosciPrzelew', 'FormyPlatnosci']:
        try:
            val = getattr(slowniki, prop)
            print(f"  Slowniki.{prop} = '{val}' (type: {type(val)})")
            if prop == 'FormyPlatnosciKarta':
                print(f"    Istnieje 'PayU': {val.Istnieje('PayU')}")
                print(f"    Istnieje 'Odroczony 7 dni': {val.Istnieje('Odroczony 7 dni')}")
        except Exception as e:
            print(f"  Slowniki.{prop} -> Error: {e}")

    print("\nDocument properties:")
    mgr = sfera.o_subiekt.SuDokumentyManager
    nowa_fs = mgr.DodajFS()
    
    props = [
        'PlatnoscKartaKwota', 'PlatnoscKartaNazwa', 'PlatnoscKartaId',
        'PlatnoscPrzelewKwota', 'PlatnoscPrzelewNazwa', 'PlatnoscPrzelewId',
        'PlatnoscKredytKwota', 'PlatnoscKredytNazwa', 'PlatnoscKredytId', 'PlatnoscKredytTermin'
    ]
    for prop in props:
        try:
            val = getattr(nowa_fs, prop)
            print(f"  FS.{prop} = '{val}'")
        except Exception as e:
            print(f"  FS.{prop} -> BRAK/ERROR: {e}")
            
    nowa_fs.Zamknij()

except Exception as e:
    print("Blad:", e)
finally:
    sfera.disconnect()
