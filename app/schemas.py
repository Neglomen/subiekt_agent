# app/schemas.py

from datetime import date
from typing import Dict, List, Literal, Optional
from app.config import ServiceMappings
from pydantic import BaseModel, Field
from decimal import Decimal

class InvoiceLineItemCheck(BaseModel):
    product_symbol: str
    quantity: Decimal

class InvoiceCheckRequest(BaseModel):
    """Model żądania do weryfikacji istnienia i zawartości faktury."""
    invoice_number: str = Field(..., description="Oryginalny numer faktury do wyszukania.")
    total_amount: Decimal = Field(..., description="Kwota brutto faktury.")
    
    line_items: List[InvoiceLineItemCheck] = Field(..., description="Lista pozycji do weryfikacji.")


class InvoiceCheckResponse(BaseModel):
    """Model odpowiedzi z wynikiem weryfikacji faktury."""
    found: bool


class StatusResponse(BaseModel):
    """Model odpowiedzi dla endpointu statusu."""
    status: str
    sfera_connected: bool
    message: str | None = None

class InvoiceLineItem(BaseModel):
    product_symbol: str
    quantity: Decimal
    net_price: Decimal

class InvoiceCreateRequest(BaseModel):
    """Model żądania do utworzenia nowej faktury lub korekty zakupowej (FZ/KFZ)."""
    document_type: Literal["FZ", "KFZ"] = Field("FZ", description="Typ dokumentu: 'FZ' (faktura zakupowa) lub 'KFZ' (korekta faktury zakupowej).")
    supplier_nip: str = Field(..., description="NIP dostawcy (kontrahenta).")
    original_invoice_number: str = Field(..., description="Oryginalny numer faktury od dostawcy.")
    corrected_invoice_number: Optional[str] = Field(None, description="Numer oryginalnej faktury zakupowej (FZ), której dotyczy korekta.")
    issue_date: date = Field(..., description="Data wystawienia faktury.")
    payment_due_date: date = Field(..., description="Termin płatności.")
    
    line_items: List[InvoiceLineItem] = Field(..., min_length=1, description="Lista pozycji na fakturze.")

class InvoiceCreateResponse(BaseModel):
    """Model odpowiedzi po pomyślnym utworzeniu faktury."""
    success: bool = True
    subiekt_document_number: str = Field(..., description="Numer pełny nowo utworzonego dokumentu FZ w Subiekcie.")
    action_taken: str = Field(..., description="Opis wykonanej akcji: 'created' lub 'existed'.") 
    message: str = "Faktura została pomyślnie utworzona w Subiekcie GT."

    # --- NOWE SCHEMATY DLA FAKTUR SPRZEDAŻY ---

class SalesInvoiceLineItem(BaseModel):
    """Model pozycji na fakturze sprzedaży."""
    product_symbol: str = Field(..., description="Symbol towaru w Subiekcie.")
    quantity: Decimal = Field(..., gt=0, description="Ilość sprzedanego towaru.")
    gross_price: Decimal = Field(..., gt=0, description="Cena jednostkowa brutto.")
    vat_rate: Decimal = Field(..., ge=0, description="Stawka VAT (np. 23.0).")

class SalesInvoiceCustomerData(BaseModel):
    """Model danych nabywcy (dla kontrahenta jednorazowego)."""
    nip: Optional[str] = Field(None, description="NIP nabywcy, jeśli podany.")
    name: str = Field(..., description="Pełna nazwa nabywcy.")
    street: str = Field(..., description="Ulica i numer domu.")
    postal_code: str = Field(..., description="Kod pocztowy.")
    city: str = Field(..., description="Miejscowość.")

class SalesInvoiceCreateRequest(BaseModel):
    """Model żądania do utworzenia nowej Faktury Sprzedaży (FS)."""
    original_order_number: str = Field(..., description="Numer oryginalnego zamówienia (np. z Allegro).")
    
    customer: SalesInvoiceCustomerData = Field(..., description="Szczegółowe dane nabywcy.")
    
    issue_date: date = Field(..., description="Data wystawienia dokumentu.")
    sale_date: date = Field(..., description="Data dokonania lub zakończenia dostawy towarów (data sprzedaży).")
    payment_due_date: date = Field(..., description="Termin płatności.")
    
    payment_type: str = Field(..., description="Forma płatności (np. 'przelew', 'pobranie'). Musi istnieć w Subiekcie.")
    is_paid_in_advance: bool = Field(False, description="Czy płatność została już uregulowana (np. PayU, Przelewy24).")
    
    line_items: List[SalesInvoiceLineItem] = Field(..., min_length=1, description="Lista pozycji na fakturze.")

class SalesInvoiceCreateResponse(BaseModel):
    """Model odpowiedzi po pomyślnym utworzeniu faktury sprzedaży."""
    success: bool = True
    subiekt_document_number: str = Field(..., description="Pełny numer nowo utworzonego dokumentu FS w Subiekcie.")
    action_taken: str = Field(..., description="Opis wykonanej akcji: 'created' lub 'existed'.")
    message: str

class ProductRead(BaseModel):
    id: int
    symbol: str
    name: Optional[str] = None

class ProductSearchResponse(BaseModel):
    products: List[ProductRead]

class PaymentFormRead(BaseModel):
    id: int
    name: str

class AllMappingsRead(BaseModel):
    """Model reprezentujący całą sekcję mapowań w config.json."""
    ksef_enabled: bool = False
    fiscalization_enabled: bool = False
    fiscal_printer_id: Optional[int] = None
    payment_type_mappings: Dict[str, str]
    service_mappings: ServiceMappings
    product_mappings: Dict[str, str]
    distributed_costs_keywords: List[str]


# --- SCHEMATY DLA MASOWEJ WERYFIKACJI STANÓW MAGAZYNOWYCH ---

class BulkStockRequest(BaseModel):
    """Model żądania do masowego sprawdzenia stanów magazynowych."""
    symbols: List[str] = Field(
        ...,
        min_length=1,
        description="Lista symboli towarów do sprawdzenia (tylko towary tw_Typ=1; usługi są ignorowane)."
    )

class BulkStockResponse(BaseModel):
    """Model odpowiedzi z mapowaniem symboli na dostępne stany magazynowe."""
    stocks: Dict[str, float] = Field(
        ...,
        description=(
            "Słownik {symbol: dostępna_ilość_netto}. "
            "Dostępna ilość = stan - rezerwacje. "
            "Symbole nieznalezione w Subiekcie lub nieposiadające stanu są zwracane z wartością 0.0."
        )
    )


# --- SCHEMATY DLA MASOWEGO POBIERANIA SKŁADNIKÓW KOMPLETÓW ---

class ComponentItem(BaseModel):
    symbol: str = Field(..., description="Symbol składnika kompletu.")
    quantity: float = Field(..., description="Wymagana ilość składnika dla 1 kompletu.")

class BulkComponentsRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=1, description="Lista symboli kompletów do pobrania.")

class BulkComponentsResponse(BaseModel):
    components: Dict[str, List[ComponentItem]] = Field(
        ...,
        description="Słownik mapujący symbol kompletu na listę jego składników z ilościami."
    )