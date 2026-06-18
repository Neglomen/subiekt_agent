import sys
import win32com.client
from win32com.client import gencache

from app.config import settings

# Force generation of static COM wrappers for InsERT
try:
    print("Generating static COM wrappers for InsERT.GT...")
    # This will generate python classes for the COM objects, allowing reflection/inspection
    insert_gt = gencache.EnsureDispatch("InsERT.GT")
    print("Static wrappers generated successfully.")
except Exception as e:
    print("Failed to generate static wrappers:", e)
    sys.exit(1)

# Now connect using our SferaInstance config
from app.sfera.sfera_instance import SferaInstance
sfera = SferaInstance(settings.sfera)

try:
    sfera.connect()
    subiekt = sfera.o_subiekt
    
    print("\n--- Inspecting SuDokumentyManager ---")
    mgr = subiekt.SuDokumentyManager
    
    # We can inspect the attributes/methods of the generated class
    # The generated class will be in win32com.client.gencache
    mgr_class = mgr.__class__
    print(f"Class of SuDokumentyManager: {mgr_class}")
    
    print("\nMethods/Properties on SuDokumentyManager containing 'FS' or 'KSeF' or 'ksef' or 'Faktura':")
    methods = sorted(list(dir(mgr)))
    for m in methods:
        m_lower = m.lower()
        if 'fs' in m_lower or 'ksef' in m_lower or 'faktura' in m_lower or 'korekta' in m_lower:
            print(f"  {m}")
            
    print("\nCreating a dummy FS to inspect its properties...")
    fs = mgr.DodajFS()
    print("\nProperties on FS containing 'KSeF' or 'ksef':")
    fs_methods = sorted(list(dir(fs)))
    for m in fs_methods:
        if 'ksef' in m.lower():
            try:
                val = getattr(fs, m)
                print(f"  {m} = {val} (type: {type(val)})")
            except Exception as e:
                print(f"  {m} -> error: {e}")
                
    fs.Zamknij()

except Exception as e:
    print("Error during inspection:", e)
finally:
    sfera.disconnect()
