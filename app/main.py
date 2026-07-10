import logging
import os
import sys
import time
import tempfile
import uuid
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.lifespan import lifespan
from app.dependencies import get_api_key
from app.services.document_service import DocumentService
from app.services.config_service import ConfigService
from app.repositories.product_repository import ProductRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.payment_form_repository import PaymentFormRepository
from app.sfera.sfera_worker import sfera_worker
import app.config as app_config
from app.schemas import (
    AllMappingsRead, BulkStockRequest, BulkStockResponse,
    PaymentFormRead, ProductSearchResponse, SalesInvoiceCreateRequest, SalesInvoiceCreateResponse,
    InvoiceCreateRequest, InvoiceCreateResponse,
    InvoiceCheckRequest, InvoiceCheckResponse,
    StatusResponse, BulkComponentsRequest, BulkComponentsResponse
)
from app.exceptions import InvoiceNotFoundError, OutOfStockValidationError

# --- GUI API & WebSocket router ---
from app.gui_api import router as gui_router, ws_router, BroadcastLogHandler, agent_stats

log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
logging.basicConfig(level=logging.DEBUG, format=log_format)
logger = logging.getLogger(__name__)

# Install the broadcast handler so all Python logs stream to the GUI terminal
_broadcast_handler = BroadcastLogHandler()
_broadcast_handler.setFormatter(logging.Formatter(log_format))
_broadcast_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_broadcast_handler)

app = FastAPI(
    title="SuppSales Subiekt GT Agent",
    version="0.5.1-web",
    description="Agent do integracji platformy SuppSales z systemem InsERT Subiekt GT przez Sferę.",
    lifespan=lifespan
)

# --- LATENCY / STATS MIDDLEWARE ---
@app.middleware("http")
async def stats_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    # Only record genuine external API calls (skip GUI and static file requests)
    path = request.url.path
    if not path.startswith("/gui") and not path.startswith("/ws") and path != "/":
        agent_stats.record_request(latency_ms)
    return response

# --- Register GUI routers (no auth — served on localhost only) ---
app.include_router(gui_router)
app.include_router(ws_router)

# --- Serve React SPA from app/static/ (built by `npm run build`) ---
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    STATIC_DIR = Path(sys._MEIPASS) / "app" / "static"
else:
    STATIC_DIR = app_config.BASE_DIR / "app" / "static"

def _serve_frontend():
    """Mount React SPA assets and index.html root."""
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def serve_spa_root():
            return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

_serve_frontend()

# ---------------------------------------------------------------------------
def create_service() -> DocumentService:
    """Funkcja pomocnicza do tworzenia instancji serwisów wewnątrz workera."""
    product_repo = ProductRepository(sfera_worker._sfera)
    doc_repo = DocumentRepository(sfera_worker._sfera)
    return DocumentService(sfera_worker._sfera, product_repo, doc_repo, app_config.settings)

# ---------------------------------------------------------------------------
@app.get("/status", response_model=StatusResponse, tags=["Health"])
async def get_status():
    if not sfera_worker.is_ready:
        raise HTTPException(status_code=503, detail="Agent online, ale SferaWorker inicjalizuje się lub wystąpił błąd.")
    return StatusResponse(status="ok", sfera_connected=True, message="Agent i SferaWorker są gotowe.")

@app.post("/sales-invoices/create", response_model=SalesInvoiceCreateResponse, tags=["Sales Invoices"], dependencies=[Depends(get_api_key)])
async def create_sales_invoice(request: SalesInvoiceCreateRequest):
    logger.info(f"Otrzymano żądanie utworzenia FS: {request.model_dump_json(indent=2)}")
    try:
        def task_to_run():
            service = create_service()
            return service.create_sales_invoice(request)

        doc_number, action = await sfera_worker.submit_task(task_to_run)
        
        # Record stats
        agent_stats.record_invoice(doc_number, success=True)
        
        if action == "existed": message = f"FS dla zamówienia '{request.original_order_number}' już istniała."
        else: message = f"Pomyślnie utworzono FS. Nowy numer: {doc_number}"
        
        return SalesInvoiceCreateResponse(subiekt_document_number=doc_number, action_taken=action, message=message)
    except (InvoiceNotFoundError, OutOfStockValidationError, ValueError) as e:
        agent_stats.record_invoice("", success=False)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        agent_stats.record_invoice("", success=False)
        raise HTTPException(status_code=500, detail=f"Wewnętrzny błąd agenta: {e}")

@app.get("/sales-invoices/pdf", tags=["Sales Invoices"], dependencies=[Depends(get_api_key)])
async def get_sales_invoice_pdf(doc_number: str, background_tasks: BackgroundTasks):
    logger.info(f"Otrzymano żądanie pobrania PDF dla dokumentu: {doc_number}")
    try:
        def task_to_run():
            temp_dir = tempfile.gettempdir()
            temp_file_name = f"fv_{uuid.uuid4().hex}.pdf"
            temp_file_path = os.path.join(temp_dir, temp_file_name)
            service = create_service()
            service.export_document_to_pdf(doc_number, temp_file_path)
            return temp_file_path
            
        temp_file_path = await sfera_worker.submit_task(task_to_run)
        
        def cleanup_temp_file():
            try:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                    logger.info(f"Usunięto plik tymczasowy: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Błąd podczas usuwania pliku tymczasowego {temp_file_path}: {e}")
                
        background_tasks.add_task(cleanup_temp_file)
        
        safe_filename = doc_number.replace('/', '_').replace(' ', '_') + ".pdf"
        return FileResponse(path=temp_file_path, media_type="application/pdf", filename=safe_filename)
        
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Błąd podczas pobierania PDF faktury")
        raise HTTPException(status_code=500, detail=f"Wewnętrzny błąd agenta: {e}")

@app.post("/invoices/check", response_model=InvoiceCheckResponse, tags=["Purchase Invoices (FZ)"], dependencies=[Depends(get_api_key)])
async def check_invoice(request: InvoiceCheckRequest):
    try:
        def task_to_run():
            service = create_service()
            return service.check_invoice_exists(request)

        found = await sfera_worker.submit_task(task_to_run)
        return InvoiceCheckResponse(found=found)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Wewnętrzny błąd agenta: {e}")
    
@app.post("/invoices/create", response_model=InvoiceCreateResponse, tags=["Purchase Invoices (FZ)"], dependencies=[Depends(get_api_key)])
async def create_invoice(request: InvoiceCreateRequest):
    logger.info(f"Otrzymano żądanie utworzenia FZ: {request.model_dump_json(indent=2)}")
    try:
        def task_to_run():
            service = create_service()
            return service.create_purchase_invoice(request)

        doc_number, action = await sfera_worker.submit_task(task_to_run)
        
        agent_stats.record_invoice(doc_number, success=True)
        
        if action == "existed": message = f"FZ '{request.original_invoice_number}' już istniała."
        else: message = f"Pomyślnie utworzono FZ. Nowy numer: {doc_number}"
        
        return InvoiceCreateResponse(subiekt_document_number=doc_number, action_taken=action, message=message)
    except (InvoiceNotFoundError, ValueError) as e:
        agent_stats.record_invoice("", success=False)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        agent_stats.record_invoice("", success=False)
        raise HTTPException(status_code=500, detail=f"Wewnętrzny błąd agenta: {e}")
    
@app.get("/products", response_model=ProductSearchResponse, tags=["Products"], dependencies=[Depends(get_api_key)])
async def search_products(q: Optional[str] = Query(None)):
    try:
        def task_to_run():
            repo = ProductRepository(sfera_worker._sfera)
            return repo.search(q)

        products = await sfera_worker.submit_task(task_to_run)
        return ProductSearchResponse(products=products)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Wewnętrzny błąd agenta: {e}")

@app.post(
    "/products/stock/bulk",
    response_model=BulkStockResponse,
    tags=["Products"],
    dependencies=[Depends(get_api_key)],
    summary="Masowe sprawdzenie stanów magazynowych",
)
async def get_bulk_stock(request: BulkStockRequest):
    """Szybka, masowa weryfikacja stanów magazynowych przez bezpośrednie zapytanie SQL."""
    try:
        def task_to_run():
            repo = ProductRepository(sfera_worker._sfera)
            return repo.get_bulk_stock(request.symbols)

        stocks = await sfera_worker.submit_task(task_to_run)
        agent_stats.record_bulk_stock(request.symbols, success=True)
        return BulkStockResponse(stocks=stocks)
    except Exception as e:
        agent_stats.record_bulk_stock(request.symbols if request else [], success=False)
        raise HTTPException(status_code=500, detail=f"Wewnętrzny błąd agenta: {e}")

@app.get("/payment-forms", response_model=List[PaymentFormRead], tags=["Configuration"], dependencies=[Depends(get_api_key)])
async def get_payment_forms():
    try:
        def task_to_run():
            repo = PaymentFormRepository(sfera_worker._sfera)
            return repo.get_all()

        forms = await sfera_worker.submit_task(task_to_run)
        return forms
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Wewnętrzny błąd agenta: {e}")

@app.get("/config/mappings", response_model=AllMappingsRead, tags=["Configuration"], dependencies=[Depends(get_api_key)])
async def get_all_mappings():
    try:
        service = ConfigService()
        settings = service.get_config()
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd odczytu konfiguracji: {e}")

@app.post("/config/mappings", response_model=AllMappingsRead, tags=["Configuration"], dependencies=[Depends(get_api_key)])
async def set_all_mappings(mappings: AllMappingsRead):
    try:
        service = ConfigService()
        service.save_config(mappings)
        return mappings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd zapisu konfiguracji: {e}")

@app.post(
    "/products/components/bulk",
    response_model=BulkComponentsResponse,
    tags=["Products"],
    dependencies=[Depends(get_api_key)],
    summary="Masowe pobieranie składników kompletów",
)
async def get_bulk_components(request: BulkComponentsRequest):
    try:
        def task_to_run():
            repo = ProductRepository(sfera_worker._sfera)
            return repo.get_bulk_components(request.symbols)

        components = await sfera_worker.submit_task(task_to_run)
        return BulkComponentsResponse(components=components)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Wewnętrzny błąd agenta: {e}")

# --- Register catch-all wildcard route at the very end to avoid hijacking API paths ---
def _register_catch_all():
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
        async def serve_spa_catch_all(full_path: str):
            # If path matches a known prefix but wasn't handled by FastAPI, return 404
            if any(full_path.startswith(p) for p in [
                "gui", "ws", "sales-invoices", "invoices",
                "products", "config", "status", "payment-forms", "docs", "openapi",
            ]):
                raise HTTPException(status_code=404)
            return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

_register_catch_all()