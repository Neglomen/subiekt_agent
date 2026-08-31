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

**Wersja aplikacji:** 0.9.0 — jedyne źródło prawdy to `app/services/updater.py::APP_VERSION` (importują je `app/main.py` i `app/gui_api.py`). Drugie, niezależne miejsce to `AppVersion` w `installer/setup.iss` — Inno Setup nie zaimportuje stałej z Pythona, więc przy wydaniu trzeba podbić oba.
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
├── build.ps1                      # poetry run pyinstaller → usuwa .env/config.json z paczki → ISCC.exe
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

# Testy (czysta logika — nie wymagają Subiekta ani Windows)
poetry install --with dev
poetry run pytest

# Dev: frontend panelu GUI (z katalogu frontend/, hot-reload osobno od backendu)
cd frontend && npm install && npm run dev

# Build frontendu do app/static/ (wymagane przed budową .exe)
cd frontend && npm run build

# Pełny build .exe + instalator (Windows, wymaga Poetry + PyInstaller + Inno Setup 6)
./build.ps1
```

### Wydanie nowej wersji

1. Podbij wersję w **dwóch** miejscach: `app/services/updater.py::APP_VERSION` i `AppVersion`
   w `installer/setup.iss` (Inno Setup nie zaimportuje stałej z Pythona).
2. `cd frontend && npm run build` — inaczej `.exe` spakuje stary panel z `app/static/`.
3. `./build.ps1` — PyInstaller → usunięcie `.env`/`config.json` z `dist/` → ISCC.exe.
4. Sprawdź, że w `dist/` **nie ma** `.env` ani `config.json` (repo jest publiczne, patrz
   "Bezpieczeństwo" #2).
5. Upload na GitHub Releases (`Neglomen/subiekt_agent`) — auto-update klientów bierze stamtąd.

### Instalacja i aktualizacja — dlaczego wygląda tak, jak wygląda

Do 0.9.0 aktualizacja regularnie kończyła się błędami dostępu do plików, a jedynym
pewnym wyjściem było odinstalowanie agenta przed instalacją nowej wersji. Złożyły się na
to trzy niezależne przyczyny — wszystkie naprawione, nie cofaj tych zmian:

1. **Agent nie zamykał się przed startem instalatora.** `apply_update()` wołało
   `sys.exit(0)`, ale biegnie ono w wątku pobierania (`start_download_and_install` →
   `threading.Thread`), a `sys.exit()` poza wątkiem głównym kończy **wyłącznie ten wątek**.
   Proces agenta żył dalej i trzymał własne pliki. Teraz jest `os._exit(0)`, poprzedzone
   `_release_file_locks()`, które przez `AgentManager.stop()` domyka tunele, uvicorna
   i SferaWorkera. **Nie wracaj do `sys.exit`** — pilnuje tego `tests/test_updater_shutdown.py`.
2. **Tunel blokował katalog instalacji.** `cloudflared.exe`/`ngrok.exe` lądują w
   `%APPDATA%\SuppSalesAgent\bin`, czyli **wewnątrz** `{app}` (`DefaultDirName`), a jako
   procesy potomne nie giną razem z agentem. Nie ma ich w `[Files]`, więc Restart Manager
   ich nie widzi — dlatego `setup.iss` ma sekcję `[Code]`, która ubija procesy
   **po ścieżce** (`Get-Process | Where-Object { $_.Path -like '{app}\*' }`). Filtr po
   nazwie obrazu ubiłby też cudzy tunel niezwiązany z agentem.
3. **Stare pliki zostawały po aktualizacji.** PyInstaller w trybie onedir trzyma runtime
   w `_internal`; bez `[InstallDelete]` moduł usunięty między wersjami zostawał obok
   nowych i paczka robiła się niespójna. `config.json` i `.env` leżą poza `_internal`,
   więc konfiguracja klienta to przeżywa.

Dodatkowo `AppId` (trwała tożsamość — **nie zmieniać**) oraz `{autodesktop}` zamiast
`{commondesktop}`: ten drugi wskazuje `C:\Users\Public\Desktop`, gdzie zapis wymaga
uprawnień administratora, a instalator działa z `PrivilegesRequired=lowest` — tworzenie
skrótu kończyło się osobnym błędem dostępu.

**Czego to NIE naprawia:** ostrzeżenia SmartScreen i alarmów antywirusa. Ani `.exe`, ani
instalator **nie są podpisane cyfrowo** (`build.ps1` nie wywołuje `signtool`). Niepodpisany
plik PyInstallera to klasyczny cel heurystyk AV, a agent dodatkowo pobiera i uruchamia
`cloudflared.exe` oraz własny instalator — wzorzec typowy dla downloaderów. Bez certyfikatu
podpisującego (OV buduje reputację tygodniami, EV daje ją od razu) ostrzeżenia zostaną.

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
| `POST /sales-invoices/correct` | Tworzy KFS (korektę FS) — patrz sekcja "Korekty faktur sprzedaży (KFS)" |
| `GET /sales-invoices/pdf`, `/sales-corrections/pdf` | Eksport dokumentu do PDF (plik tymczasowy, sprzątany po wysłaniu) |
| `POST /invoices/check` | Sprawdza czy FZ/KFZ już istnieje (idempotencja) |
| `POST /invoices/create` | Tworzy FZ lub KFZ |
| `GET /products` | Wyszukiwanie towarów po symbolu/nazwie |
| `POST /products/stock/bulk` | Masowe stany magazynowe (jedno zapytanie SQL z CTE, liczy też komplety) |
| `POST /products/components/bulk` | Masowe pobranie składników kompletów |
| `GET /payment-forms` | Formy płatności ze słownika Subiekta (`sl_FormaPlatnosci`): `id`, `name`, `type` (= `fp_Typ`) |
| `GET/POST /config/mappings` | Odczyt/zapis `config.json` |

Pełna, żywa dokumentacja: `/docs` (Swagger UI, FastAPI domyślne — publicznie dostępne, nie wymaga API key).

---

## Korekty faktur sprzedaży (KFS)

Najbardziej zawiła ścieżka w tym komponencie i jedyna, która dotyka trzech repozytoriów naraz.
Przebudowana 2026-08-31 po audycie — poniżej stan docelowy i powody decyzji, żeby nie odtwarzać
usuniętych rozwiązań.

### Kontrakt end-to-end

| Warstwa | Co wysyła |
|---|---|
| `sales-correction-modal.tsx` | `offer_id` pozycji, `$SERVICE_DELIVERY` dla dostawy, `$SERVICE_ADDITIONAL_<definitionId>` dla usług, `payment_form_id` albo `payment_type` (`gotówka`/`przelew`) |
| `subiekt_tasks._resolve_correction_line_symbols` | zamienia `offer_id` → symbol ERP z `ProductErpMapping`, `$SERVICE_DELIVERY` → `_COD`/`_PREPAID` wg `order.payment_type` |
| agent `correct_sales_invoice` | dopasowuje pozycje po `TowarId`, nie po tekście |

**Symbole muszą pochodzić z tego samego źródła co przy wystawianiu FS** (`ProductErpMapping` +
sentinele `$SERVICE_*`). Wcześniej front wysyłał surową nazwę oferty z marketplace'u, agent
próbował ją odgadnąć przez `product_mappings` z `config.json` i dopasowanie po podciągach, a przy
niepowodzeniu **po cichu pomijał pozycję** — powstawała korekta na 0 zł, magazyn się nie ruszał,
a API zwracało sukces. Nie wracaj do dopasowywania po nazwie.

### Dopasowywanie pozycji

Jedna pozycja żądania odpowiada **wielu** pozycjom dokumentu, w dwóch niezależnych wymiarach:

- **komplet** (`tw_Rodzaj = 8`) — `create_sales_invoice` rozkłada go na składniki, więc korekta
  szuka składników (`_expand_to_document_products`), nie kompletu;
- **rozbicie fiskalne** — jeden towar bywa w dwóch pozycjach różniących się o grosz
  (patrz `app/pricing.py`); `_distribute_quantity` wypełnia je po kolei do pierwotnej ilości,
  bo skalowanie proporcjonalne dałoby dwie pozycje po pół sztuki.

Ilość dzielona jest dwustopniowo: proporcją `po/przed` między grupy towarów (poprawnie skaluje
składniki kompletu), a wewnątrz grupy przez wypełnianie po kolei. Cena skaluje się proporcją
`corrected_gross_price / original_gross_price` — dlatego backend **musi** wysyłać pola
`original_*`, inaczej cen kompletów nie da się rozdzielić.

**Źródłem prawdy są pozycje korygowanej faktury, nie symbol z zamówienia.** Mapowanie
`ProductErpMapping` bywa zmieniane już po wystawieniu FS, więc symbol wyprowadzony z `offer_id`
potrafi wskazywać towar, którego na fakturze nie ma. Stąd kolejność dopasowań:

1. `correction_type == "FULL"` → **żadnego dopasowywania**: zerowane są wszystkie pozycje
   faktury. W tym wariancie pomyłka jest z definicji niemożliwa.
2. po `TowarId` z kartoteki (komplet rozwijany na składniki),
3. po znormalizowanym symbolu pozycji dokumentu — kartoteka Subiekta zawiera bliźniacze wpisy
   różniące się samymi białymi znakami (`'CMO-MP012OC-BK'` i `'CMO-MP012OC-BK '`), mające osobne
   `tw_Id`; `get_normalized_map` zostawia z nich tylko pierwszy napotkany, a `SELECT` nie ma
   `ORDER BY`, więc który to będzie, jest w praktyce losowe,
4. po ilości i wartości sprzed korekty,
5. jedna niedopasowana pozycja żądania + jedna wolna pozycja faktury → para jednoznaczna,
   łączona z ostrzeżeniem w logu.

Kroki 2–5 ograniczają się do pozycji **tej jednej faktury** i akceptują wyłącznie trafienie
jednoznaczne — to nie jest powrót do dawnego globalnego dopasowywania po podciągach kartoteki.

Gdy i to zawiedzie: **błąd 422** z listą symboli żądania oraz pozycji faktury. Cicha korekta
zerowa jest gorsza niż błąd.

### Formy zwrotu

Formy nie zgadujemy. `payment_form_id` (z `sl_FormaPlatnosci.fp_Id`) → konkretna forma;
`gotówka` → `PlatnoscGotowkaKwota`; `przelew` → `PlatnoscPrzelewKwota` ("Zapłacono przelewem",
rozliczenie natychmiastowe); cokolwiek innego bez identyfikatora → 422 z listą dostępnych form.
O tym, czy forma jest kartowa, decyduje `Slowniki.FormyPlatnosciKarta.Istnieje(nazwa)` — ta sama
metoda co przy FS; `fp_Typ` to tylko fallback.

Poprzednia wersja brała **pierwszą z brzegu** formę o `fp_Typ == 0` z nieuporządkowanego wyniku
SQL — stąd zgłoszenia "korekta wskazuje inną metodę rozliczenia". `SELECT` bez `ORDER BY` nie ma
gwarantowanej kolejności; nie opieraj na niej logiki.

### Fakty ze Sfery (zweryfikowane w dokumentacji, nie zgadywane)

| Fakt | Konsekwencja |
|---|---|
| `SuPozycjaKorekty` — parametry **przed** korektą są read-only, ustawiać można `*PoKorekcie` | `IloscJmPoKorekcie`, `CenaBruttoPrzedRabatemPoKorekcie`, `CenaNettoPrzedRabatemPoKorekcie`, `VatProcentPoKorekcie` |
| `SuDokument` **nie ma** atrybutu z tekstem przyczyny korekty | przyczyna to `PrzyczynaKorektyId` **na pozycji**, wskazujący `sl_PrzyczynaKorekty.pkr_Id`; wolny tekst idzie do `Uwagi` |
| `UjecieKorektyTypEnum`: 1 = w dacie faktury pierwotnej, 2 = w dacie wystawienia korekty, 3 = w dacie innej | `UjecieKorektyData` wolno ustawić **tylko** przy typie 3; agent ustawia 2 |
| `PlatnoscPrzelewKwota` istnieje i znaczy "Zapłacono przelewem" | zwrot natychmiastowy nie potrzebuje formy odroczonej |
| `SuDokument.DoDokumentuId` = kolumna `dok_DoDokId` | wiązanie KFS→FS; używane do wykrywania duplikatu (nie `dok_Uwagi LIKE`) |
| `SkutekMagazynowy` jest przestarzały ("pozostawiony ze względu na wsteczną zgodność") | zwrot na magazyn dzieje się **automatycznie** na podstawie `IloscJmPoKorekcie`; nie ma czego dodatkowo ustawiać |
| `DoDokumentuNumerKSeF` | numer KSeF faktury źródłowej na korekcie |
| `dok__Dokument.dok_Typ` | 1 = FZ, 2 = FS, 6 = KFS |
| Atrybuty nieistniejące, mimo że były w kodzie | `SuDokument.Przyczyna`, `SuPozycja.StawkaVatProcent`, `SuPozycja.StawkaVat` — nie przywracaj |

### Decyzje właściciela produktu

- **Korekty nie fiskalizują się w ogóle** (2026-08-31). Agent jawnie ustawia
  `RejestrujNaUF = False` na KFS, bo `NaPodstawie` kopiuje nagłówek FS, a ta po wydruku ma tę
  flagę ustawioną. Nie dodawaj automatu drukowania KFS na drukarce fiskalnej.
- **Korekty z NIP-em idą do KSeF** tą samą flagą `dok_CzekaNaKSeF` co faktury (`_mark_for_ksef`).
  O kwalifikacji decyduje NIP płatnika faktury pierwotnej (`DocumentRepository.get_payer_nip`).
- **Druga korekta do tej samej FS jest blokowana** jako duplikat (zwracane `action_taken="existed"`).
  Tak było przed przebudową; jeśli ma się to zmienić, to świadoma decyzja, nie efekt uboczny.

### Otwarte

- **Znak `KwotaDoZaplaty` na KFS** — nieudokumentowany. Ścieżka KFZ używa wartości ze znakiem
  (`create_purchase_invoice`), KFS używa `abs()`. Jedna z nich jest zła. W kodzie jest `TODO`
  i log surowej wartości ze Sfery — do rozstrzygnięcia po pierwszej korekcie na produkcji.
  Alternatywnie: `SuDokument.PodajRozrachunek()` zwraca rozrachunek KFS-a, jego
  `WartoscPoczatkowaWaluta` też pokaże znak.
- `UjecieKorektyTyp = 2` jest zaszyte w kodzie. Jeśli księgowość zażyczy sobie ujęcia w dacie
  faktury pierwotnej — zmiana na 1.

### Referencja zamówienia w uwagach FS

Agent **celowo nie ustawia** `NumerOryginalny` — Subiekt drukowałby wtedy adnotację
"Do zamówienia: ..." pod numerem faktury. Referencja (szablon `erp_sales_reference_template`
z `sync_config` integracji) trafia wyłącznie do `Uwagi`, limit 500 znaków.

Backend obcina sformatowaną referencję do 400 znaków (zapas na prefiks "Zamówienie od klienta: ").
Do 2026-08-31 obcinał do **50**, przez co przy szablonie z `{order_id}` (ID Allegro ma 36 znaków)
ucinało login kupującego.

`safe_original_number[:30]` w `create_sales_invoice` to **wyłącznie** klucz wyszukiwania duplikatu
(`dok_Uwagi LIKE '%prefiks%'`), nie limit pola. Konsekwencja: **szablon musi zawierać
`{order_id}`, najlepiej na początku** — szablon typu `{login}` sprawiłby, że drugie zamówienie
tego samego kupującego zostanie uznane za już zafakturowane.

## Ważne zasady

### Bezpieczeństwo

1. ✅ **NAPRAWIONE** — `/gui/*` i `/ws/logs` były bez ŻADNEJ autoryzacji, mimo komentarza w `main.py` (`"served on localhost only"`), fałszywego założenia skoro Cloudflare/ngrok tunelują **cały port**. Naprawa (2026-08-23):
   - `router = APIRouter(prefix="/gui", ..., dependencies=[Depends(get_api_key)])` w `app/gui_api.py` — każda trasa `/gui/*` wymaga teraz `X-API-Key`.
   - `/ws/logs` sprawdza ręcznie `?api_key=` z query stringa przed `accept()` (WebSocket handshake nie przenosi custom nagłówków z przeglądarki), zamyka z `WS_1008_POLICY_VIOLATION` jeśli brak/zły klucz.
   - `POST /gui/update/download` **nie przyjmuje już `download_url` od klienta** — sam wywołuje `update_manager.check_for_updates()` po stronie serwera i używa TEGO adresu, dodatkowo zweryfikowanego przez `UpdateManager.is_safe_download_url()` (allowlist hostów: `github.com`, `objects.githubusercontent.com`, tylko HTTPS). Usunięto wektor "dowolny URL → pobierz i uruchom".
   - Panel webowy zdobywa klucz przez natywny most pywebview (`window.pywebview.api.get_api_key()`), nie przez HTTP — patrz sekcja "GUI" wyżej. Frontend przebudowany (`npm run build`), `app/static/` zaktualizowane.
   - Zweryfikowano end-to-end przez `starlette.testclient.TestClient`: brak klucza / zły klucz → 401 na REST i disconnect na WS; poprawny klucz → 200/połączenie; `update/download` z poprawnym kluczem ale bez faktycznej nowszej wersji → 400 (serwer sam to sprawdza, nie ufa klientowi).
   - Przy okazji naprawiono niezwiązany, ale blokujący `npm install`, problem: `frontend/package.json` wskazywał na brakujący lokalny plik `rollup-rollup-win32-x64-msvc-4.62.2.tgz` — zmieniono na wersję z rejestru npm (`^4.62.2`).

2. **Sekrety/dane biznesowe w publicznym repo GitHub**: do wersji 0.8.1 włącznie `build.ps1` kopiował lokalny `.env` do paczki dystrybucyjnej, a `setup.iss` pakował go do instalatora — opublikowany na GitHub Releases `.exe` rozpakowuje się zwykłym archiwizerem, więc hasło operatora Sfery, `agent_api_key` i tokeny tuneli mogły być publicznie dostępne. **Naprawione od 0.9.0**: `build.ps1` usuwa `.env`/`config.json` z `dist/`, a `setup.iss` nie pakuje już `.env`. Agent bez `.env` startuje na wartościach domyślnych i konfiguruje się przez panel GUI. Artefakty starszych release'ów nie zostały zweryfikowane ani wycofane. `config.json` zawiera prawdziwe mapowania produktów konkretnego klienta. `.gitignore` ma regułę `.env`, ale nie działa retroaktywnie na już scommitowane pliki — jeśli kiedykolwiek wpisano tam prawdziwe hasło, trzeba je zrotować i wyczyścić historię git (BFG/`git filter-repo`), bo repo jest **publiczne**.

3. SQL budowany przez f-string interpolation w `repositories/product_repository.py` (i pokrewnych) zamiast sparametryzowanych zapytań ADO. Obecne łatanie (`replace("'", "''")`, `replace("'", "")`, rzutowanie na `int()`) broni przed najprostszym SQL injection, ale to kruchy wzorzec — nowe pole dodane bez tej dyscypliny = dziura. Docelowo: `Command` + parametry ADO.

### Konwencje
- Cała logika COM/Sfera **musi** przechodzić przez `sfera_worker.submit_task()` — nigdy bezpośrednio z wątku FastAPI.
- Kwoty pieniężne zawsze jako `Decimal` (nie `float`) w schematach Pydantic.
- Nowe endpointy biznesowe: zawsze `dependencies=[Depends(get_api_key)]`, chyba że to `/status`.
- Frontend GUI buduje się do `app/static/` — po zmianach w `frontend/src` trzeba `npm run build` przed testem pełnej aplikacji (`main_gui.py` serwuje z `app/static/`, nie z Vite dev servera).

---

## Znane problemy / dług techniczny

- **Testy pokrywają na razie tylko arytmetykę cen.** `tests/test_pricing.py` sprawdza `app/pricing.py` (podział wartości kompletu na pozycje fiskalne) — to czysta logika, więc chodzi bez Subiekta i bez Windows. Reszta, w tym tworzenie FS/KFS/FZ/KFZ przez COM, jest nadal nieprzetestowana; brak CI (`.github/workflows` nie istnieje). **Warto wiedzieć:** metody pomocnicze korekty (`_apply_correction_to_positions`, `_distribute_quantity`, `_expand_to_document_products`, `_resolve_correction_product`) nie dotykają COM — da się je testować na atrapach pozycji (obiekt z polami `TowarId`, `IloscJm`, `CenaBruttoPrzedRabatem` i zapisywalnymi `*PoKorekcie`), wstrzykując `SimpleNamespace` w miejsce `product_repo` i `config`. `scratch/` (≈1750 linii) to ręczne skrypty deweloperskie do eksploracji Sfery/SQL, nie test suite.
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
