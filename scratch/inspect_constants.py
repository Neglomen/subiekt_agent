import win32com.client
from win32com.client import gencache
import sys

try:
    print("Generating static COM wrappers for InsERT.GT...")
    insert_gt = gencache.EnsureDispatch("InsERT.GT")
    print("Static wrappers generated successfully.")
    
    # Try to print some constants
    print("Constants in win32com.client.constants:")
    try:
        # We can look for constants
        consts = win32com.client.constants
        print("gtaTypPlikuPDF:", getattr(consts, "gtaTypPlikuPDF", "Not Found"))
        print("gtaTypPlikuTekstowy:", getattr(consts, "gtaTypPlikuTekstowy", "Not Found"))
        
        # Let's inspect the names of all constants
        print("\nAll constants starting with gta:")
        gta_consts = [name for name in dir(consts) if name.startswith("gta")]
        for name in gta_consts[:30]:
            print(f"  {name} = {getattr(consts, name)}")
    except Exception as e:
        print("Error getting constants:", e)
except Exception as e:
    print("Failed:", e)
