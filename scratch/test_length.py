import sys
from app.sfera.sfera_instance import SferaInstance
from app.config import settings
import pywintypes

sfera = SferaInstance(settings.sfera)

try:
    sfera.connect()
    subiekt = sfera.o_subiekt
    
    fs = subiekt.SuDokumentyManager.DodajFS()
    print("Obiekt FS utworzony.")
    
    # Próbujemy ustawić długi i krótki numer
    try:
        fs.NumerOryginalny = "12345678901234567890" # 20 znaków
        print("Ustawienie 20 znaków: SUKCES")
    except Exception as e:
        print("Ustawienie 20 znaków: BLAD", e)
        
    try:
        fs.NumerOryginalny = "marzenka12389 - b2271a90-3e7c-11f1-aaeb-5bdde598bd" # 50 znaków
        print("Ustawienie 50 znaków: SUKCES")
    except Exception as e:
        print("Ustawienie 50 znaków: BLAD", type(e).__name__)
        
except Exception as e:
    print("Blad glowny:", e)
finally:
    sfera.disconnect()
