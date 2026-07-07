import win32com.client
import pythoncom
import pywintypes

operators_to_test = ["Szef", "PHU_PATRYK_SIKORA", "", "Patryk Sikora"]
server = "SERVER\\SQL"
db = "PHU_PATRYK_SIKORA"

for op in operators_to_test:
    print(f"Testing operator login: '{op}'...")
    try:
        pythoncom.CoInitialize()
        gt = win32com.client.Dispatch("InsERT.GT")
        gt.Produkt = 1
        gt.Autentykacja = 0
        gt.Serwer = server
        gt.Baza = db
        gt.Operator = op
        gt.OperatorHaslo = ""
        
        o_subiekt = gt.Uruchom(6)
        if o_subiekt is not None:
            print(f"  SUCCESS! Connected with operator: '{op}'")
            o_subiekt.Zakoncz()
            pythoncom.CoUninitialize()
            break
        else:
            err_code = gt.GetLastError() if hasattr(gt, 'GetLastError') else 'N/A'
            err_msg = gt.GetError_vb(err_code) if hasattr(gt, 'GetError_vb') else 'No desc.'
            print(f"  Failed (None returned). Error code: {err_code}, Desc: {err_msg}")
    except pywintypes.com_error as e:
        print(f"  COM Error: {e}")
    except Exception as e:
        print(f"  Error: {e}")
    finally:
        pythoncom.CoUninitialize()
