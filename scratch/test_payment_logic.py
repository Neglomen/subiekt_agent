import logging
from datetime import date
from pydantic import BaseModel
from app.sfera.sfera_instance import SferaInstance
from app.config import settings, load_config
from app.services.document_service import DocumentService
from app.repositories.product_repository import ProductRepository
from app.repositories.document_repository import DocumentRepository

logging.basicConfig(level=logging.INFO)

# Dummy invoice data class
class DummyInvoiceData(BaseModel):
    payment_type: str
    payment_due_date: date

sfera = SferaInstance(settings.sfera)
sfera.connect()

try:
    config = load_config()
    product_repo = ProductRepository(sfera)
    doc_repo = DocumentRepository(sfera)
    
    doc_service = DocumentService(
        sfera=sfera,
        product_repo=product_repo,
        doc_repo=doc_repo,
        config=config
    )
    
    # We will test three payment types:
    # 1. ONLINE (mapped to PayU, which is Type 1 / Karta)
    # 2. CASH_ON_DELIVERY (mapped to Za pobraniem ROHLIG SUUS, which is Type 3 / Kredyt in DB but False in Karta dict)
    # 3. CASH_ON_DELIVERY:INPOST (mapped to Pobranie kurier InPost, which is Type 1 / Karta)
    
    test_cases = [
        {"payment_type": "ONLINE", "due_days": 0, "desc": "Online payment (PayU)"},
        {"payment_type": "CASH_ON_DELIVERY", "due_days": 7, "desc": "COD (Za pobraniem ROHLIG SUUS) - Type 3"},
        {"payment_type": "CASH_ON_DELIVERY:INPOST", "due_days": 0, "desc": "COD InPost (Pobranie kurier InPost) - Type 1"}
    ]
    
    for case in test_cases:
        print("\n" + "="*60)
        print(f"TEST CASE: {case['desc']}")
        print("="*60)
        
        # Add new FS document
        nowa_fs = sfera.o_subiekt.SuDokumentyManager.DodajFS()
        
        # Add a dummy item so we have a positive KwotaDoZaplaty
        # Towar ID = 1 (usually exists, let's just add any item or use an item ID from DB)
        try:
            # Let's find a valid item id first
            rs, _ = sfera.ado_connection.Execute("SELECT TOP 1 tw_Id FROM tw__Towar")
            if not rs.EOF:
                tw_id = rs.Fields("tw_Id").Value
                pos = nowa_fs.Pozycje.Dodaj(tw_id)
                pos.IloscJm = 1
                pos.CenaBruttoPrzedRabatem = 123.45
        except Exception as e:
            print(f"Warning: could not add item: {e}")
            
        invoice_data = DummyInvoiceData(
            payment_type=case["payment_type"],
            payment_due_date=date.today()
        )
        
        # Run _handle_payment
        doc_service._handle_payment(nowa_fs, invoice_data)
        
        # Verify document properties
        print(f"Results for payment_type '{case['payment_type']}':")
        print(f"  PlatnoscKartaId     = {nowa_fs.PlatnoscKartaId}")
        print(f"  PlatnoscKartaKwota  = {nowa_fs.PlatnoscKartaKwota}")
        print(f"  PlatnoscKredytId    = {nowa_fs.PlatnoscKredytId}")
        print(f"  PlatnoscKredytKwota = {nowa_fs.PlatnoscKredytKwota}")
        print(f"  PlatnoscKredytTermin= {nowa_fs.PlatnoscKredytTermin}")
        
        # Close document without saving
        nowa_fs.Zamknij()

except Exception as e:
    print("Test failed with error:", e)
finally:
    sfera.disconnect()
