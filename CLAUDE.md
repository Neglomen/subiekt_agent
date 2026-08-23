# CLAUDE.md — subiekt_agent

## Cel komponentu
On-premise agent (Python) instalowany lokalnie na komputerze klienta w tej samej sieci co baza **Subiekt GT**. Komunikuje się z Subiektem przez **Sferę** (COM/ActiveX, `InsERT.GT`) i wystawia lokalne REST API, przez które platforma SuppSales (backend w chmurze) tworzy faktury sprzedaży (FS), korekty (KFS), faktury zakupu (FZ/KFZ), sprawdza stany magazynowe i pobiera PDF-y dokumentów. Odpowiednik `Agent ERP` wspominany w [../CLAUDE.md](../CLAUDE.md) i obsługiwany w `suppsales_frontend` przez `ErpStatusIndicator`.

Działa jako aplikacja w **zasobniku systemowym Windows** (tray icon) z natywnym oknem GUI (pywebview) do konfiguracji, podglądu logów na żywo i statystyk.

**To NIE jest serwer .NET** (wcześniejsza dokumentacja w root `CLAUDE.md` była nieaktualna) — to FastAPI (Python) + `pywin32` do wywołań COM.

---

## Stack technologiczny

| Warstwa | Technologia | Rola |
|---|---|---|
| Backend agenta | Python ≥3.10,<3.14, FastAPI, Uvicorn | REST API + WebSocket |
| Integracja z ERP | `pywin32` (`win32com.client`), COM/Sfera (`InsERT.GT`) | komunikacja z Subiekt GT |
| Konfiguracja | `pydantic-settings` (`.env`) + `config.json` (mapowania) | sekrety + reguły biznesowe |
| GUI (tray) | `pystray` + `Pillow` | ikona w zasobniku, menu |
| GUI (okno) | `pywebview` (natywne okno, frameless) | osadza frontend React |
| GUI (frontend) | React 19 + TypeScript + Vite + TailwindCSS v4 + Framer Motion | panel webowy (`frontend/`, build → `app/static/`) |
| Tunelowanie | `cloudflared.exe` (auto-pobierany) / `pyngrok`-style ngrok | wystawienie agenta na świat (dla backendu SuppSales) |
| Dystrybucja | PyInstaller (`.spec`) + Inno Setup (`installer/setup.iss`) | budowa `.exe` i instalatora Windows |
| Auto-update | własny `UpdateManager` + GitHub Releases (`Neglomen/subiekt_agent`) | sprawdzanie/pobieranie nowych wersji |
| Zarządzanie zależnościami | Poetry (`pyproject.toml`, `poetry.lock`) | — |

**Wersja aplikacji:** 0.8.1 (`app/main.py`, `app/services/updater.py::APP_VERSION`)
**GitHub Releases:** `Neglomen/subiekt_agent`

---

## Struktura katalogów

```
subiekt_agent/
├── app/
│   ├── main.py                    # FastAPI app, wszystkie endpointy biznesowe, montowanie SPA
│   ├── lifespan.py                # start/stop SferaWorker przy starcie/zamknięciu FastAPI
│   ├── config.py                  # SferaSettings (.env) + MappingSettings (config.json) + zapis
│   ├── dependencies.py            # get_api_key — jedyny mechanizm auth (nagłówek X-API-Key)
│   ├── exceptions.py              # SferaConnectionError, InvoiceNotFoundError, OutOfStockValidationError
│   ├── schemas.py                 # Pydantic modele request/response (Decimal dla kwot)
│   ├── utils.py                   # urlopen_with_fallback — SSL z magazynu certyfikatów Windows
│   ├── gui_api.py                 # Router /gui/* + WebSocket /ws/logs (BEZ autoryzacji — patrz "Bezpieczeństwo")
│   ├── gui/
│   │   ├── tray.py                # AgentManager (start/stop uvicorn+tunele), TrayApp (pystray)
│   │   ├── webview_window.py      # Natywne okno pywebview + WindowAPI (JS↔Python bridge)
│   │   └── log_handler.py         # QueueLogHandler
│   ├── sfera/
│   │   ├── sfera_instance.py      # Cykl życia połączenia COM (connect/reconnect/disconnect)
│   │   └── sfera_worker.py        # Single-thread worker + kolejka asyncio — SERIALIZUJE wywołania COM
│   ├── repositories/              # Dostęp do danych: product/document/payment_form (surowe zapytania SQL przez ADO)
│   ├── services/
│   │   ├── document_service.py    # ⚠️ 1200+ linii — cała logika tworzenia/korekty FS/FZ/KFZ, płatności, KSeF, PDF
│   │   ├── config_service.py      # CRUD dla config.json (mapowania)
│   │   └── updater.py             # Sprawdzanie/pobieranie/instalacja aktualizacji z GitHub Releases
│   ├── tunnel/
│   │   ├── cloudflare_manager.py  # Zarządza procesem cloudflared.exe (auto-download + Quick/Named Tunnel)
│   │   └── ngrok_manager.py       # Alternatywa dla Cloudflare
│   └── static/                    # Zbudowany frontend (React SPA), serwowany przez FastAPI pod "/"
├── frontend/                      # Źródła panelu webowego (React+Vite) — build trafia do app/static/
├── scratch/                       # Ad-hoc skrypty deweloperskie do debugowania Sfery/SQL (NIE testy — patrz "Znane problemy")
├── installer/setup.iss            # Konfiguracja instalatora Inno Setup
├── build.ps1                      # poetry run pyinstaller → kopiuje .env/config.json → ISCC.exe
├── subiekt_agent.spec             # Konfiguracja PyInstaller (co trafia do .exe)
├── config.json                    # Mapowania biznesowe (płatności, usługi, produkty) — commitowane do repo
├── .env                           # Sekrety (DB, hasło operatora, API key, tokeny tuneli) — gitignored, ale patrz niżej
└── pyproject.toml / poetry.lock
```

---

## Komendy

```bash
# Dev: backend (z katalogu subiekt_agent/)
poetry install
poetry run python main_gui.py

# Dev: frontend panelu GUI (z katalogu frontend/, hot-reload osobno od backendu)
cd frontend && npm install && npm run dev

# Build frontendu do app/static/ (wymagane przed budową .exe)
cd frontend && npm run build

# Pełny build .exe + instalator (Windows, wymaga Poetry + PyInstaller + Inno Setup 6)
./build.ps1
```

> **Uwaga:** `main_gui.py` blokuje wątek główny pętlą `pywebview` — na Windows to wymóg (`webview.start()` musi być na głównym wątku). `pystray` (tray) działa w osobnym wątku (`run_detached()`), Uvicorn w kolejnym.

---

## Architektura

### Warstwy
`main.py` (routing FastAPI) → `services/` (logika biznesowa, np. `DocumentService`) → `repositories/` (zapytania SQL/COM przez ADO) → `sfera/` (surowa instancja COM `InsERT.GT`).

### SferaWorker — serializacja wywołań COM
Sfera/COM **nie jest thread-safe** i musi żyć w jednym dedykowanym wątku z `pythoncom.CoInitialize()`. `SferaWorker` (`app/sfera/sfera_worker.py`) implementuje wzorzec **single-thread worker + kolejka `asyncio.Queue`**: każdy request FastAPI (async, wielowątkowy) pakuje swoją pracę jako `(future, func, args, kwargs)` i czeka na wynik przez `await sfera_worker.submit_task(...)`. Worker wykonuje zadania sekwencyjnie w swoim wątku. Przy `SferaConnectionError` worker próbuje automatycznego `reconnect()` i ponawia zadanie raz.

**Nie omijaj tego wzorca** — żadne repozytorium/serwis nie powinno wywoływać `sfera_worker._sfera` bezpośrednio spoza kontekstu `submit_task`.

### `OutOfStockValidationError` vs `SferaConnectionError`
COM-owy błąd "Brak towaru w magazynie" jest przechwytywany i rzucany jako `OutOfStockValidationError` (→ HTTP 422), a NIE jako `SferaConnectionError`, żeby nie wywoływać kosztownego cyklu reconnect przy zwykłym błędzie walidacji biznesowej.

### Konfiguracja — dwa źródła
- **`.env`** (`SferaSettings`) — sekrety i ustawienia środowiskowe: dane logowania do bazy/Sfery, `agent_api_key`, port, tokeny Cloudflare/ngrok. Zapisywane przez `save_sfera_settings()` (nadpisuje cały plik).
- **`config.json`** (`MappingSettings`) — reguły biznesowe: mapowania metod płatności → forma płatności w Subiekcie, mapowania usług, mapowania symboli produktów, słowa kluczowe kosztów rozłożonych, flagi KSeF/fiskalizacji.
- Oba wczytywane raz do globalnego `app_config.settings` przy starcie; GUI (`/gui/config` POST) i restart agenta odświeżają go w pamięci.

### Tunelowanie (Cloudflare / ngrok)
Agent nasłuchuje **tylko na `127.0.0.1:{agent_port}`** (uvicorn `host="127.0.0.1"`). Jeśli `cloudflare_enabled`/`ngrok_enabled`, `CloudflareManager`/`NgrokManager` uruchamia lokalny proces tunelujący (`cloudflared.exe`, auto-pobierany z GitHub przy pierwszym użyciu), który **proxuje CAŁY port na publiczny URL** — to jedyny sposób, żeby backend SuppSales w chmurze dotarł do agenta stojącego za NAT-em klienta.

**Konsekwencja bezpieczeństwa:** skoro tunel proxuje cały port, każdy route (łącznie z `/gui/*` i `/ws/logs`) staje się publicznie dostępny, gdy tunel jest aktywny. **Naprawione** (patrz "Bezpieczeństwo" niżej) — `/gui/*` i `/ws/logs` wymagają teraz tego samego `X-API-Key` co API biznesowe.

### GUI (tray + webview + WebSocket)
- `TrayApp`/`AgentManager` (`app/gui/tray.py`) uruchamia/zatrzymuje: Uvicorn (w wątku), `SferaWorker`, tunele.
- Panel webowy (React, zbudowany do `app/static/`) jest serwowany przez ten sam FastAPI pod `/`, komunikuje się z backendem przez `/gui/*` (REST, wymaga `X-API-Key`) i `/ws/logs` (WebSocket, wymaga `?api_key=`, strumień logów na żywo).
- Logi: `RotatingFileHandler` (10MB × 5 plików, `logs/agent.log`) + `BroadcastLogHandler` wysyłający każdy log do WebSocket-owych klientów panelu.
- **Jak panel poznaje klucz API:** WYŁĄCZNIE przez natywny most pywebview — `WindowAPI.get_api_key()` (`app/gui/webview_window.py`), wywoływany z frontendu jako `window.pywebview.api.get_api_key()` (JS↔Python IPC, proces lokalny, niedostępny przez sieć/tunel). Frontend czeka na `pywebviewready` zanim odpali pierwsze żądanie — patrz `frontend/src/App.tsx`. Ktoś, kto otworzy publiczny URL tunelu w zwykłej przeglądarce, nie ma `window.pywebview` i nie może w ten sposób zdobyć klucza.

---

## Endpointy API (wybrane)

Wszystkie poza `/status` wymagają nagłówka `X-API-Key` (`Depends(get_api_key)`, porównanie z `settings.sfera.agent_api_key`) — łącznie z `/gui/*` (router-level `dependencies=[Depends(get_api_key)]`) i `/ws/logs` (ręczna weryfikacja `?api_key=` przed `accept()`, bo przeglądarki nie pozwalają ustawiać customowych nagłówków na handshake WebSocketa).

| Endpoint | Opis |
|---|---|
| `GET /status` | Health check (czy SferaWorker gotowy) |
| `POST /sales-invoices/create` | Tworzy FS (fakturę sprzedaży) |
| `POST /sales-invoices/correct` | Tworzy KFS (korektę FS) |
| `GET /sales-invoices/pdf`, `/sales-corrections/pdf` | Eksport dokumentu do PDF (plik tymczasowy, sprzątany po wysłaniu) |
| `POST /invoices/check` | Sprawdza czy FZ/KFZ już istnieje (idempotencja) |
| `POST /invoices/create` | Tworzy FZ lub KFZ |
| `GET /products` | Wyszukiwanie towarów po symbolu/nazwie |
| `POST /products/stock/bulk` | Masowe stany magazynowe (jedno zapytanie SQL z CTE, liczy też komplety) |
| `POST /products/components/bulk` | Masowe pobranie składników kompletów |
| `GET/POST /config/mappings` | Odczyt/zapis `config.json` |

Pełna, żywa dokumentacja: `/docs` (Swagger UI, FastAPI domyślne — publicznie dostępne, nie wymaga API key).

---

## Ważne zasady

### Bezpieczeństwo

1. ✅ **NAPRAWIONE** — `/gui/*` i `/ws/logs` były bez ŻADNEJ autoryzacji, mimo komentarza w `main.py` (`"served on localhost only"`), fałszywego założenia skoro Cloudflare/ngrok tunelują **cały port**. Naprawa (2026-08-23):
   - `router = APIRouter(prefix="/gui", ..., dependencies=[Depends(get_api_key)])` w `app/gui_api.py` — każda trasa `/gui/*` wymaga teraz `X-API-Key`.
   - `/ws/logs` sprawdza ręcznie `?api_key=` z query stringa przed `accept()` (WebSocket handshake nie przenosi custom nagłówków z przeglądarki), zamyka z `WS_1008_POLICY_VIOLATION` jeśli brak/zły klucz.
   - `POST /gui/update/download` **nie przyjmuje już `download_url` od klienta** — sam wywołuje `update_manager.check_for_updates()` po stronie serwera i używa TEGO adresu, dodatkowo zweryfikowanego przez `UpdateManager.is_safe_download_url()` (allowlist hostów: `github.com`, `objects.githubusercontent.com`, tylko HTTPS). Usunięto wektor "dowolny URL → pobierz i uruchom".
   - Panel webowy zdobywa klucz przez natywny most pywebview (`window.pywebview.api.get_api_key()`), nie przez HTTP — patrz sekcja "GUI" wyżej. Frontend przebudowany (`npm run build`), `app/static/` zaktualizowane.
   - Zweryfikowano end-to-end przez `starlette.testclient.TestClient`: brak klucza / zły klucz → 401 na REST i disconnect na WS; poprawny klucz → 200/połączenie; `update/download` z poprawnym kluczem ale bez faktycznej nowszej wersji → 400 (serwer sam to sprawdza, nie ufa klientowi).
   - Przy okazji naprawiono niezwiązany, ale blokujący `npm install`, problem: `frontend/package.json` wskazywał na brakujący lokalny plik `rollup-rollup-win32-x64-msvc-4.62.2.tgz` — zmieniono na wersję z rejestru npm (`^4.62.2`).

2. **Sekrety/dane biznesowe w publicznym repo GitHub**: `.env` jest zacommitowany (obecnie same placeholdery, ale mechanizm zapisu istnieje i `build.ps1` kopiuje lokalny `.env` do paczki dystrybucyjnej — łatwo przypadkiem zbudować i opublikować `.exe` z prawdziwym hasłem w środku). `config.json` zawiera prawdziwe mapowania produktów konkretnego klienta. `.gitignore` ma regułę `.env`, ale nie działa retroaktywnie na już scommitowane pliki — jeśli kiedykolwiek wpisano tam prawdziwe hasło, trzeba je zrotować i wyczyścić historię git (BFG/`git filter-repo`), bo repo jest **publiczne**.

3. SQL budowany przez f-string interpolation w `repositories/product_repository.py` (i pokrewnych) zamiast sparametryzowanych zapytań ADO. Obecne łatanie (`replace("'", "''")`, `replace("'", "")`, rzutowanie na `int()`) broni przed najprostszym SQL injection, ale to kruchy wzorzec — nowe pole dodane bez tej dyscypliny = dziura. Docelowo: `Command` + parametry ADO.

### Konwencje
- Cała logika COM/Sfera **musi** przechodzić przez `sfera_worker.submit_task()` — nigdy bezpośrednio z wątku FastAPI.
- Kwoty pieniężne zawsze jako `Decimal` (nie `float`) w schematach Pydantic.
- Nowe endpointy biznesowe: zawsze `dependencies=[Depends(get_api_key)]`, chyba że to `/status`.
- Frontend GUI buduje się do `app/static/` — po zmianach w `frontend/src` trzeba `npm run build` przed testem pełnej aplikacji (`main_gui.py` serwuje z `app/static/`, nie z Vite dev servera).

---

## Znane problemy / dług techniczny

- **Brak testów automatycznych.** `scratch/` (≈1750 linii) to ręczne skrypty deweloperskie do eksploracji Sfery/SQL, nie prawdziwy test suite — brak pytest, brak CI (`.github/workflows` nie istnieje). Przy logice tak krytycznej jak tworzenie faktur/korekt to duże ryzyko regresji przy każdej zmianie.
- `scratch/` zawiera scommitowane skompilowane `.pyc` (`__pycache__`) i binarny `test_print.pdf` — `.gitignore` próbuje je wykluczyć, ale zostały dodane wcześniej; warto `git rm --cached` i wyczyścić.
- `app/services/document_service.py` — ponad 1200 linii w jednej klasie (FS, KFS, FZ/KFZ, płatności, KSeF, PDF). Kandydat do rozbicia na mniejsze serwisy per typ dokumentu.
- Brak `README.md` w katalogu głównym repo (jest tylko generyczny `frontend/README.md` z boilerplate Vite) — brak instrukcji setupu dla kogoś innego niż autor.
- Brak CI/CD — build/release są w pełni ręczne (`build.ps1` lokalnie + ręczny upload na GitHub Releases).
- Drobne: `app/sfera/sfera_worker.py::_run()` w bloku `finally` odwołuje się do `pythoncom`, importowanego dopiero wewnątrz `try` — teoretyczny `NameError`, gdyby import zawiódł przed przypisaniem (bardzo mało prawdopodobne, ale maskowałoby prawdziwy błąd).

## Mocne strony
- Wzorzec single-thread worker + kolejka do serializacji COM — poprawne, przemyślane rozwiązanie realnego ograniczenia Sfery, z sensowną logiką reconnect.
- Czysty podział warstw (routing → serwisy → repozytoria → COM).
- `Decimal` dla kwot, Pydantic do walidacji requestów.
- Osobny wyjątek na brak towaru (unika zbędnego, kosztownego reconnectu Sfery).
- GUI: tray + natywne okno pywebview zamiast wymuszania przeglądarki, streaming logów przez WebSocket w czasie rzeczywistym — dobre UX jak na lokalnego agenta działającego w tle.
- Auto-update i auto-pobieranie `cloudflared.exe` — mniej ręcznej pracy dla użytkownika końcowego (choć patrz luka bezpieczeństwa #1 wyżej).
