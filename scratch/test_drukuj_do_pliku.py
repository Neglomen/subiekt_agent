import os
import sys
import win32com.client

from app.config import settings
from app.sfera.sfera_instance import SferaInstance

sfera = SferaInstance(settings.sfera)

try:
    print("Connecting to Sfera...")
    sfera.connect()
    subiekt = sfera.o_subiekt
    
    doc_number = "FS 12500/MAG/2026"
    print(f"Loading document: {doc_number} ...")
    
    # We will try loading it from SuDokumentyManager
    try:
        mgr = subiekt.SuDokumentyManager
        print("Successfully accessed SuDokumentyManager.")
    except Exception as e:
        print("Failed to access SuDokumentyManager:", e)
        sys.exit(1)
        
    dok = mgr.Wczytaj(doc_number)
    
    if not dok:
        print("Document not found!")
        sys.exit(1)
        
    print("Document loaded successfully. Full number:", dok.NumerPelny)
    
    # Path where we want to save the PDF
    pdf_path = os.path.abspath("scratch/test_print.pdf")
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
        
    print(f"Calling DrukujDoPliku to: {pdf_path} ...")
    
    # Under dynamic dispatch, we don't have access to win32com.client.constants.gtaTypPlikuPDF
    # directly unless we load it, but the integer constant for PDF is 0
    pdf_constant = 0 
    
    print(f"Using PDF constant value: {pdf_constant}")
    dok.DrukujDoPliku(pdf_path, pdf_constant)
    
    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
        print(f"Success! PDF created successfully at {pdf_path} (size: {os.path.getsize(pdf_path)} bytes)")
    else:
        print("Failed! PDF file was not created or is empty.")
        
except Exception as e:
    print("An error occurred during print testing:", e)
finally:
    print("Disconnecting from Sfera...")
    sfera.disconnect()
