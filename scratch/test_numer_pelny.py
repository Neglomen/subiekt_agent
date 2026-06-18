import sys
from app.sfera.sfera_instance import SferaInstance
from app.config import settings
import pywintypes

sfera = SferaInstance(settings.sfera)

try:
    sfera.connect()
    subiekt = sfera.o_subiekt
    
    # Tworzymy pusty FS, dodajemy jedną linię by móc zapisać i sprawdzamy NumerPelny
    fs = subiekt.SuDokumentyManager.DodajFS()
    
    # Dodajemy domyslnego klienta (np. jednorazowego detalicznego)
    kh = subiekt.Kontrahenci.Wczytaj("SS-DETAL") # zakladamy ze istnieje, albo dodamy pozycje i zapiszemy jako paragon?
    # sprobujmy po prostu zrobic Zapisz po uzupelnieniu
    
    print("NumerPelny przed Zapisz:", fs.NumerPelny)
    # Zeby zapisać, dokument musi mieć kontrahenta i pozycje. Pomińmy cały test jeśli to trudne do zmockowania.
    # Wypiszmy tylko co zwraca domyślnie.
    
except Exception as e:
    print("Blad:", e)
finally:
    sfera.disconnect()
