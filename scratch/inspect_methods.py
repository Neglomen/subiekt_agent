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
    
    print("\n--- Properties/Methods of Subiekt (o_subiekt) ---")
    subiekt_attrs = sorted(list(dir(subiekt)))
    print("All attributes:")
    for attr in subiekt_attrs:
        if attr.startswith("_"):
            continue
        print(f"  {attr}")
        
    print("\n--- Properties/Methods of SuDokumentyManager ---")
    if hasattr(subiekt, "SuDokumentyManager"):
        mgr = subiekt.SuDokumentyManager
        mgr_attrs = sorted(list(dir(mgr)))
        for attr in mgr_attrs:
            if attr.startswith("_"):
                continue
            print(f"  {attr}")
            
except Exception as e:
    print("An error occurred:", e)
finally:
    sfera.disconnect()
