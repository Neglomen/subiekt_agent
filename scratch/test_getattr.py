import sys
import win32com.client
from win32com.client import gencache

print("Ensuring InsERT.GT COM dispatch...")
insert_gt = gencache.EnsureDispatch("InsERT.GT")

from app.config import settings
from app.sfera.sfera_instance import SferaInstance

sfera = SferaInstance(settings.sfera)

try:
    print("Connecting to Sfera...")
    sfera.connect()
    subiekt = sfera.o_subiekt
    
    print("Subiekt class:", subiekt.__class__)
    
    # Try accessing SuDokumentyManager directly
    try:
        mgr = subiekt.SuDokumentyManager
        print("SuDokumentyManager successfully accessed. Class:", mgr.__class__)
        
        # Let's check if we can load a document by number or ID using Wczytaj
        # We know FS 12500/MAG/2026 exists
        doc_number = "FS 12500/MAG/2026"
        print(f"Trying to load {doc_number} using SuDokumentyManager.Wczytaj...")
        try:
            # Let's check what methods are available on mgr or try calling Wczytaj
            dok = mgr.Wczytaj(doc_number)
            print("Wczytaj succeeded! Document full number:", dok.NumerPelny)
        except Exception as e:
            print("Wczytaj failed on SuDokumentyManager:", e)
            
    except Exception as e:
        print("Failed to access SuDokumentyManager:", e)
        
except Exception as e:
    print("An error occurred:", e)
finally:
    sfera.disconnect()
