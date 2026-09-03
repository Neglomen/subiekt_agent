import logging
import pywintypes
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.config import AppConfig
from app.exceptions import InvoiceNotFoundError, OutOfStockValidationError, SferaConnectionError
from app.repositories.document_repository import DocumentRepository
from app.pricing import lines_total, split_gross_into_fiscal_lines
from app.repositories.product_repository import ProductRepository, normalize_symbol
from app.schemas import SalesInvoiceCreateRequest, InvoiceCreateRequest, InvoiceCheckRequest, SalesInvoiceCorrectRequest
from app.sfera.sfera_instance import SferaInstance

logger = logging.getLogger(__name__)

class DocumentService:
    """
    Serwis zawierający całą logikę biznesową do tworzenia i weryfikacji
    dokumentów w Subiekcie GT. Orkiestruje pracę repozytoriów i Sfery.
    """
    def __init__(
        self, 
        sfera: SferaInstance, 
        product_repo: ProductRepository, 
        doc_repo: DocumentRepository,
        config: AppConfig
    ):
        """
        Konstruktor serwisu. Otrzymuje wszystkie zależności poprzez
        wstrzykiwanie (Dependency Injection).
        """
        self._sfera = sfera
        self._product_repo = product_repo
        self._doc_repo = doc_repo
        self._config = config

    def check_invoice_exists(self, check_data: InvoiceCheckRequest) -> bool:
        """
        Sprawdza, czy faktura zakupowa o podanych kryteriach istnieje, 
        korzystając z repozytoriów do odczytu danych.
        """
        logger.debug(f"Weryfikacja istnienia FZ o numerze oryginalnym: '{check_data.invoice_number}'")
        
        potential_matches = self._doc_repo.find_by_original_number(check_data.invoice_number)
        if not potential_matches:
            logger.info(f"Nie znaleziono żadnych dokumentów z numerem oryginalnym: '{check_data.invoice_number}'.")
            return False
            
        input_items_aggregated = {
            normalize_symbol(item.product_symbol): item.quantity.normalize()
            for item in check_data.line_items
        }

        for doc in potential_matches:
            logger.debug(f"Sprawdzam kandydata: {doc['doc_number']} (ID: {doc['doc_id']})")
            
            if doc['total_gross'].compare(check_data.total_amount) != Decimal('0'):
                logger.debug(f"  -> ODRZUCONY: Niezgodna kwota brutto (Subiekt: {doc['total_gross']}, Oczekiwano: {check_data.total_amount})")
                continue

            subiekt_items = self._doc_repo.get_line_items_by_doc_id(doc['doc_id'])
            subiekt_items_aggregated = {
                normalize_symbol(item['symbol']): item['quantity'].normalize()
                for item in subiekt_items
            }
            
            if input_items_aggregated == subiekt_items_aggregated:
                logger.info(f"WYNIK: ZNALEZIONO! Dokument {doc['doc_number']} idealnie pasuje do kryteriów.")
                return True
            else:
                 logger.debug(f"  -> ODRZUCONY: Niezgodne pozycje. Wejście: {input_items_aggregated}, Subiekt: {subiekt_items_aggregated}")

        logger.info(f"Wyczerpano wszystkie potencjalne dokumenty. Ostatecznie nie znaleziono dopasowania dla FZ '{check_data.invoice_number}'.")
        return False

    def create_purchase_invoice(self, invoice_data: InvoiceCreateRequest) -> tuple[str, str]:
        """Tworzy Fakturę Zakupową (FZ) lub Korektę FZ (KFZ) w Subiekcie."""
        doc_type = invoice_data.document_type  # "FZ" lub "KFZ"
        
        # Fallback: jeśli aplikacja-matka nie wysłała doc_type="KFZ",
        # próbujemy wykryć korektę po wzorcu numeru faktury
        if doc_type == "FZ":
            num = invoice_data.original_invoice_number.upper()
            correction_patterns = ("IK", "KOR", "KOREK", "KOREKTA", "FAK")
            if any(num.startswith(p) or f"/{p}" in num for p in correction_patterns):
                doc_type = "KFZ"
                logger.info(f"Auto-wykryto korektę po wzorcu numeru '{invoice_data.original_invoice_number}' -> traktuję jako KFZ.")
        
        # Bezpieczne przycięcie do 30 znaków, ponieważ pole dok_NrPelnyOryg ma limit długości w bazie
        safe_original_number = str(invoice_data.original_invoice_number)[:30] if invoice_data.original_invoice_number else ""

        logger.info(f"Rozpoczynam proces tworzenia {doc_type} dla nr: '{safe_original_number}'")
        
        existing_docs = self._doc_repo.find_by_original_number(safe_original_number)
        if existing_docs:
            doc_to_return = existing_docs[0]['doc_number']
            logger.info(f"Dokument {doc_type} dla '{invoice_data.original_invoice_number}' już istnieje: {doc_to_return}.")
            return doc_to_return, "existed"

        nowy_dok = None
        try:
            kontrahent = self._sfera.o_subiekt.Kontrahenci.Wczytaj(invoice_data.supplier_nip)
            if not kontrahent:
                raise InvoiceNotFoundError(f"Nie znaleziono kontrahenta o NIP: {invoice_data.supplier_nip}")

            # === KLUCZOWA POPRAWKA LOGIKI ===
            
            # Pobieramy pełną mapę szczegółów, a nie tylko ID
            product_map = self._product_repo.get_normalized_map()
            product_details_map = {}
            missing_items = []
            product_mappings = self._config.mappings.product_mappings
            transport_keywords = [kw.lower() for kw in self._config.mappings.distributed_costs_keywords]
            
            # Rozdzielamy pozycje na: koszty do dystrybucji i towary
            goods_items = []
            distributed_costs_total = Decimal('0')
            
            for item in invoice_data.line_items:
                symbol_lower = item.product_symbol.strip().lower()
                is_distributed_cost = any(kw in symbol_lower for kw in transport_keywords)
                
                if is_distributed_cost:
                    distributed_costs_total += item.net_price * item.quantity
                    logger.info(f"Pozycja '{item.product_symbol}' rozpoznana jako koszt do dystrybucji. "
                                f"Wartość: {item.net_price * item.quantity} zł")
                else:
                    goods_items.append(item)
            
            if not goods_items:
                raise InvoiceNotFoundError("Faktura nie zawiera żadnych pozycji towarowych (wszystkie zostały odfiltrowane jako koszty transportu).")
            
            logger.info(f"Suma kosztów do proporcjonalnego rozdzielenia: {distributed_costs_total} zł "
                        f"na {len(goods_items)} pozycjê/i.")
            
            # Mapujemy towary na produkty w Subiekcie
            for i, item in enumerate(goods_items):
                original_symbol = item.product_symbol
                
                # Najpierw sprawdzamy jawne mapowania z config.json
                if original_symbol in product_mappings:
                    mapped_symbol = product_mappings[original_symbol]
                    logger.debug(f"Użyto jawnego mapowania: '{original_symbol}' -> '{mapped_symbol}'")
                    normalized_input = normalize_symbol(mapped_symbol)
                else:
                    normalized_input = normalize_symbol(original_symbol)
                
                details = product_map.get(normalized_input)
                
                # Fuzzy match was disabled for purchase invoices (FZ) to prevent incorrect index assignments.
                # All supplier indices must map exactly (either directly or via config.json mappings).

                if details:
                    product_details_map[i] = details
                else:
                    missing_items.append(original_symbol)

            if missing_items:
                raise InvoiceNotFoundError(f"Nie znaleziono towarów w Subiekcie: {', '.join(missing_items)}")

            # Proporcjonalne rozdzielenie kosztów na towary
            if distributed_costs_total > 0:
                total_goods_value = sum(item.net_price * item.quantity for item in goods_items)
                if total_goods_value > 0:
                    adjusted_goods = []
                    for item in goods_items:
                        item_value = item.net_price * item.quantity
                        proportion = item_value / total_goods_value
                        if item.quantity != 0:
                            added_cost_per_unit = (distributed_costs_total * proportion / item.quantity).quantize(Decimal('0.0001'))
                        else:
                            added_cost_per_unit = Decimal('0')
                        new_price = item.net_price + added_cost_per_unit
                        adjusted_goods.append((item, new_price))
                        logger.debug(f"  '{item.product_symbol}': cena {item.net_price} -> {new_price} (proporcja: {proportion:.2%})")
                else:
                    adjusted_goods = [(item, item.net_price) for item in goods_items]
            else:
                adjusted_goods = [(item, item.net_price) for item in goods_items]

            # === KONIEC LOGIKI PRZETWARZANIA POZYCJI ===

            # --- INTELIGENTNE POWIĄZANIE KOREKTY ---
            base_fz_id = None
            if doc_type == "KFZ":
                if not invoice_data.corrected_invoice_number:
                    raise ValueError("Numer faktury korygowanej (corrected_invoice_number) jest wymagany dla dokumentów typu KFZ.")
                matches = self._doc_repo.find_fz_by_number_and_nip(invoice_data.corrected_invoice_number, invoice_data.supplier_nip)
                if matches:
                    base_fz_id = matches[0]['doc_id']
                    logger.info(f"Znaleziono fakturę bazową w bazie: {matches[0]['doc_number']} (ID: {base_fz_id}). Tworzę korektę powiązaną.")
                else:
                    raise InvoiceNotFoundError(f"Brak faktury pierwotnej {invoice_data.corrected_invoice_number} w Subiekcie.")

            # Tworzymy odpowiedni typ dokumentu w Sferze
            if doc_type == "KFZ":
                nowy_dok = self._sfera.o_subiekt.SuDokumentyManager.DodajKFZ()
                nowy_dok.NaPodstawie(base_fz_id)
                issue_datetime = datetime.combine(invoice_data.issue_date, time(12, 0))
            else:
                nowy_dok = self._sfera.o_subiekt.SuDokumentyManager.DodajFZ()
                issue_datetime = datetime.combine(invoice_data.issue_date, time(12, 0))
            
            nowy_dok.KontrahentId = kontrahent.Identyfikator
            nowy_dok.NumerOryginalny = safe_original_number
            nowy_dok.DataWystawienia = pywintypes.Time(issue_datetime)
            nowy_dok.DataOtrzymania = pywintypes.Time(issue_datetime)
            nowy_dok.LiczonyOdCenNetto = True
            
            if doc_type == "KFZ" and base_fz_id:
                # === POWIĄZANA KOREKTA KFZ (NaPodstawie) ===
                # Sfera automatycznie kopiuje pozycje z FZ. Właściwości "przed korektą"
                # (IloscJm, CenaNettoPrzedRabatem) są READ-ONLY.
                # Można ustawiać TYLKO: IloscJmPoKorekcie, CenaNettoPrzedRabatemPoKorekcie.
                #
                # WAŻNE: Symbole produktów w payloadzie (np. "MFD 45S200X.2") mogą NIE pasować
                # do symboli na FZ (np. "DW-10F2EE(S)"). Dlatego iterujemy po pozycjach
                # skopiowanych z FZ i wyznaczamy docelową ilość na podstawie payloadu.
                #
                # Payload wysyła pary pozycji (przed/po) z tym samym symbolem:
                #   - Pozycja z quantity > 0 = ilość PRZED korektą
                #   - Pozycja z quantity = 0 = ilość PO korekcie (docelowa)

                # Payload opisuje stan PRZED i PO korekcie parami pozycji o tym samym
                # symbolu. Zwrot ilościowy różni je ilością, korekta rabatowa — ceną.
                from collections import defaultdict
                payload_groups = defaultdict(list)
                for item, _adj_price in adjusted_goods:
                    # Ceny bierzemy surowe, sprzed rozdzielenia kosztów transportu:
                    # proporcja rabatu ma wynikać z faktury dostawcy, a nie z tego, ile
                    # kosztów doliczyliśmy akurat do tej pozycji.
                    payload_groups[item.product_symbol].append(
                        (float(item.quantity), float(item.net_price))
                    )

                payload_targets = {}
                for symbol, entries in payload_groups.items():
                    quantities = [q for q, _ in entries]
                    payload_targets[symbol] = {
                        "qty_after": min(quantities),   # np. min(1, 0) = 0 -> pełny zwrot
                        "price_before": entries[0][1],
                        "price_after": entries[-1][1],
                    }

                logger.info(f"KFZ powiązana: wyznaczone cele z payloadu: {payload_targets}")

                changed_positions = 0

                # Iterujemy po pozycjach na dokumencie KFZ (skopiowanych z FZ)
                for p in nowy_dok.Pozycje:
                    original_qty = float(p.IloscJm)
                    original_price = float(p.CenaNettoPrzedRabatem)

                    target = self._match_kfz_target(p, payload_targets)
                    if target is None:
                        logger.warning(
                            f"KFZ powiązana: pozycji '{p.TowarSymbol}' nie da się jednoznacznie "
                            "powiązać z payloadem — zostawiam bez zmian."
                        )
                        continue

                    target_qty_after = target["qty_after"]

                    # Cena z FZ zawiera doliczony koszt transportu, więc nie wpisujemy ceny
                    # z payloadu wprost. Rabat przenosimy jako RÓŻNICĘ, nie proporcję:
                    # doliczony transport jest kwotą stałą i nie ma się kurczyć dlatego,
                    # że dostawca obniżył cenę towaru. Przy zwrocie ilościowym różnica
                    # wynosi 0 i cena zostaje nietknięta.
                    price_before = target["price_before"]
                    price_after = target["price_after"]
                    price_delta = price_after - price_before
                    if abs(price_delta) > 1e-9:
                        target_price_after = round(original_price + price_delta, 4)
                        if target_price_after < 0:
                            logger.warning(
                                f"KFZ rabatowa: rabat {abs(price_delta)} zł/jm przekracza cenę "
                                f"{original_price} zł z faktury pierwotnej dla '{p.TowarSymbol}'. "
                                "Ustawiam 0 — sprawdź dane korekty."
                            )
                            target_price_after = 0.0
                        logger.info(
                            f"KFZ rabatowa: pozycja '{p.TowarSymbol}' cena {original_price} -> "
                            f"{target_price_after} (rabat {price_delta} zł/jm, dostawca: "
                            f"{price_before} -> {price_after})"
                        )
                    else:
                        target_price_after = original_price

                    p.IloscJmPoKorekcie = target_qty_after
                    p.CenaNettoPrzedRabatemPoKorekcie = target_price_after

                    if (abs(target_qty_after - original_qty) > 1e-9
                            or abs(target_price_after - original_price) > 1e-9):
                        changed_positions += 1

                    logger.info(f"KFZ powiązana: pozycja '{p.TowarSymbol}' (TowarId={p.TowarId}), "
                                f"IloscPrzed={original_qty} -> IloscPo={target_qty_after}, "
                                f"CenaPrzed={original_price} -> CenaPo={target_price_after}")

                if changed_positions == 0:
                    # Dokument na 0 zł powstawał wcześniej po cichu i wyglądał jak sukces.
                    raise ValueError(
                        f"Korekta {invoice_data.original_invoice_number} nie zmienia żadnej pozycji "
                        f"faktury {invoice_data.corrected_invoice_number} — ani ilości, ani ceny. "
                        "Sprawdź dane korekty; dokument nie został utworzony."
                    )
            else:
                # === STANDARDOWA ŚCIEŻKA (FZ lub KFZ niepowiązana) ===
                for i, (item, adjusted_price) in enumerate(adjusted_goods):
                    if float(item.quantity) == 0:
                        logger.debug(f"Pominięto pozycję o zerowej ilości w dokumencie: {item.product_symbol}")
                        continue

                    details = product_details_map[i]

                    pozycja = nowy_dok.Pozycje.Dodaj(details["id"])
                    if doc_type == "KFZ":
                        qty = abs(float(item.quantity))
                        pozycja.IloscJm = qty
                        pozycja.IloscJmPoKorekcie = 0.0
                        pozycja.CenaNettoPrzedRabatem = float(adjusted_price)
                        pozycja.CenaNettoPrzedRabatemPoKorekcie = float(adjusted_price)
                    else:
                        pozycja.IloscJm = float(item.quantity)
                        pozycja.CenaNettoPrzedRabatem = float(adjusted_price)
            
            if nowy_dok.Pozycje.Liczba == 0:
                raise ValueError("Dokument nie posiada żadnych prawidłowych pozycji (wszystkie miały ilość równą 0). Nie można zapisać pustego dokumentu.")

            nowy_dok.Przelicz()
            nowy_dok.PlatnoscKredytKwota = nowy_dok.KwotaDoZaplaty
            nowy_dok.PlatnoscKredytTermin = pywintypes.Time(datetime.combine(invoice_data.payment_due_date, time(12, 0)))
            
            nowy_dok.Zapisz()
            if not nowy_dok.Identyfikator:
                raise ValueError(f"Nie udało się zapisać dokumentu {doc_type} w Subiekcie.")
            utworzony_numer = nowy_dok.NumerPelny
            logger.info(f"SUKCES! Zapisano dokument {doc_type}: {utworzony_numer}")
            return utworzony_numer, "created"
        except (InvoiceNotFoundError, OutOfStockValidationError) as e:
            raise e
        except pywintypes.com_error as e:
            try:
                raw_message = e.args[2][2] if e.args and len(e.args) > 2 and e.args[2] else None
                com_message = raw_message or ""   # guard against None in e.args[2][2]
            except (IndexError, TypeError):
                com_message = ""

            if "Brak towaru w magazynie" in com_message:
                logger.warning(
                    f"Walidacja magazynu nieudana podczas zapisu {doc_type}: {com_message.strip()}. "
                    "Rzucam OutOfStockValidationError (bez reconnect Sfery)."
                )
                raise OutOfStockValidationError("Brak towaru w magazynie.")

            error_details = f"Błąd COM: {e.strerror}"
            logger.exception(f"Błąd COM podczas tworzenia {doc_type} dla nr '{invoice_data.original_invoice_number}': {error_details}")
            raise SferaConnectionError(error_details)
        except ValueError as e:
            # ValueError to błąd biznesowy — NIE wyzwalamy reconnect Sfery.
            logger.error(f"Błąd walidacji danych podczas tworzenia {doc_type} dla nr '{invoice_data.original_invoice_number}': {e}")
            raise
        finally:
            if nowy_dok:
                try: 
                    nowy_dok.Zamknij()
                except Exception: 
                    logger.warning(f"Nie udało się poprawnie zamknąć obiektu {doc_type}.")

    def create_sales_invoice(self, invoice_data: SalesInvoiceCreateRequest) -> tuple[str, str]:
        """Tworzy Fakturę Sprzedaży (FS) w Subiekcie, wywołując skutek magazynowy."""
        # Skrót WYŁĄCZNIE do wyszukiwania duplikatu: find_by_original_number robi
        # dok_Uwagi LIKE '%...%', więc prefiks wystarcza. Do samych uwag dokumentu trafia
        # pełna referencja (patrz niżej) — nie obcinaj jej tutaj.
        safe_original_number = str(invoice_data.original_order_number)[:30] if invoice_data.original_order_number else ""

        logger.info(f"Rozpoczynam proces tworzenia FS dla zamówienia '{safe_original_number}'.")
        
        existing_docs = self._doc_repo.find_by_original_number(safe_original_number)
        if existing_docs:
            doc_to_return = existing_docs[0]['doc_number']
            logger.info(f"Dokument dla zamówienia '{invoice_data.original_order_number}' już istnieje: {doc_to_return}.")
            return doc_to_return, "existed"

        nowa_fs = None
        try:
            kontrahent_id = self._handle_customer(invoice_data.customer)
            product_details_map = self._map_line_item_products(invoice_data.line_items)

            nowa_fs = self._sfera.o_subiekt.SuDokumentyManager.DodajFS()

            nowa_fs.KontrahentId = kontrahent_id
            
            # Budujemy tekst uwag (Uwagi) z numeru zamówienia oraz ewentualnych dodatkowych uwag.
            # WAŻNE: Nie przypisujemy nowa_fs.NumerOryginalny, aby Subiekt GT nie drukował pod numerem FV
            # adnotacji "Do zamówienia: ...". Informacja o zamówieniu znajduje się wyłącznie w uwagach dokumentu.
            # Do celów zapobiegania duplikatom, repository i tak przeszukuje pole Uwagi (dok_Uwagi LIKE '%...%').
            notes_text = ""
            if invoice_data.original_order_number:
                notes_text = f"Zamówienie od klienta: {invoice_data.original_order_number}"
            
            additional_notes = invoice_data.notes or invoice_data.comments or invoice_data.remarks or invoice_data.uwagi
            if additional_notes:
                if notes_text:
                    notes_text += f"\n{additional_notes}"
                else:
                    notes_text = str(additional_notes)
            
            if notes_text:
                # Maksymalnie 500 znaków (limit kolumny dok_Uwagi w bazie danych)
                nowa_fs.Uwagi = notes_text[:500]
            
            nowa_fs.LiczonyOdCenBrutto = True
            logger.debug(" -> Ustawiono dane nagłówka (Kontrahent, Numery, Daty, Liczenie od brutto).")

            if invoice_data.customer.nip:
                # Dla faktur B2B (z NIP) ustawiamy tytuł dokumentu na "Potwierdzenie sprzedaży"
                # tak jak Subiekt GT robi to automatycznie przy ręcznym wydruku FV z NIP.
                try:
                    nowa_fs.Tytul = "Potwierdzenie sprzedaży"
                    logger.debug(" -> Ustawiono Tytul dokumentu na 'Potwierdzenie sprzedaży' (faktura B2B z NIP).")
                except Exception as e:
                    logger.debug(f" -> Nie udało się ustawić Tytul dokumentu: {e}")

            if self._config.mappings.ksef_enabled and invoice_data.customer.nip:
                nowa_fs.FormaDokumentu = 1  # gtaFormaDokumentuFakturaKSeF
                try:
                    nowa_fs.RejestrujWKSeF = True
                except Exception as e:
                    logger.debug(f" -> Zignorowano próbę ustawienia RejestrujWKSeF: {e}")
                logger.debug(" -> Ustawiono FormaDokumentu jako Faktura KSeF (1) oraz RejestrujWKSeF.")

            logger.debug("ETAP 4: Dodawanie pozycji do dokumentu.")
            for i, item in enumerate(invoice_data.line_items):
                details = product_details_map[i]

                # Komplety (tw_Rodzaj = 8) rozkładamy na składniki,
                # bo Subiekt GT blokuje zapis FS gdy fizyczny stan kompletu = 0.
                if details.get("type") == 8:
                    logger.info(
                        f" -> Pozycja {i} to komplet (ID: {details['id']}). "
                        "Rozkładam na składniki."
                    )
                    components = self._product_repo.get_bundle_components(details["id"])
                    if not components:
                        raise InvoiceNotFoundError(
                            f"Komplet o ID={details['id']} nie ma zdefiniowanych składników w tw_Komplet. "
                            "Nie można rozłożyć kompletu na pozycje FS."
                        )
                    bundle_qty = float(item.quantity)
                    # Cena brutto kompletu dzielona proporcjonalnie na składniki na podstawie ich cen katalogowych
                    price_level = 1
                    try:
                        doc_price_level = int(nowa_fs.PoziomCenyId)
                        if 1 <= doc_price_level <= 10:
                            price_level = doc_price_level
                    except Exception as pe:
                        logger.debug(f"Nie udało się pobrać PoziomCenyId z dokumentu: {pe}. Używam domyślnego poziomu 1.")

                    def get_base_price(c, level):
                        # Pobieranie ceny z wybranego poziomu, z hierarchią fallbacków
                        p = c["price_brutto"].get(level, 0.0)
                        if p > 0:
                            return p
                        p = c["price_brutto"].get(1, 0.0)
                        if p > 0:
                            return p
                        for lvl in sorted(c["price_brutto"].keys()):
                            p_val = c["price_brutto"][lvl]
                            if p_val > 0:
                                return p_val
                        return 1.0

                    total_catalog_price = sum(get_base_price(comp, price_level) * comp["quantity"] for comp in components)
                    target_total_gross = round(float(item.gross_price) * bundle_qty, 2)
                    
                    sum_assigned_values = 0.0
                    for idx, comp in enumerate(components):
                        comp_qty = comp["quantity"] * bundle_qty
                        
                        if idx == len(components) - 1:
                            item_gross_value = round(target_total_gross - sum_assigned_values, 2)
                        else:
                            share = (get_base_price(comp, price_level) * comp["quantity"]) / total_catalog_price
                            item_gross_value = round(share * target_total_gross, 2)
                            sum_assigned_values += item_gross_value
                        
                        # Cena jednostkowa MUSI mieć 2 miejsca po przecinku. Drukarka
                        # fiskalna nie dostaje wartości pozycji — liczy ją sama z ceny
                        # podanej w groszach, więc cena typu 8,3317 była przez nią
                        # zaokrąglana i suma rozjeżdżała się o grosz-dwa (faktura
                        # nie przechodziła fiskalizacji). Gdy wartość nie dzieli się
                        # równo, składnik trafia na dwie pozycje różniące się o grosz.
                        fiscal_lines = split_gross_into_fiscal_lines(item_gross_value, comp_qty)
                        if lines_total(fiscal_lines) != Decimal(str(item_gross_value)):
                            logger.warning(
                                f"    -> Składnik {comp['symbol']}: nie udało się rozbić "
                                f"{item_gross_value:.2f} zł na {comp_qty} szt bez reszty "
                                f"(wyszło {lines_total(fiscal_lines)} zł). Prawdopodobna "
                                "przyczyna: ilość ułamkowa."
                            )

                        for line_qty, line_price in fiscal_lines:
                            pozycja = nowa_fs.Pozycje.Dodaj(comp["id"])
                            pozycja.IloscJm = float(line_qty)
                            pozycja.CenaBruttoPrzedRabatem = float(line_price)
                            logger.debug(
                                f"    -> Składnik: {comp['symbol']} (ID: {comp['id']}), "
                                f"Ilość: {line_qty}, Cena bazowa: {get_base_price(comp, price_level):.2f}, "
                                f"Cena jednostkowa FS: {line_price}, "
                                f"Wartość pozycji: {line_qty * line_price}"
                            )
                else:
                    pozycja = nowa_fs.Pozycje.Dodaj(details["id"])
                    pozycja.IloscJm = float(item.quantity)
                    # Używamy ceny PRZED rabatem, aby dać Subiektowi kontrolę
                    pozycja.CenaBruttoPrzedRabatem = float(item.gross_price)
                    logger.debug(f" -> Dodano pozycję {i} (ID: {details['id']}, Typ: {details['type']}, Cena Brutto: {item.gross_price})")

            self._handle_payment(nowa_fs, invoice_data)

            # Bezpiecznik: wartość dokumentu musi zgadzać się z tym, co klient
            # zapłacił na marketplace. Rozjazd o grosze bierze się zwykle
            # z zaokrągleń przy rozkładzie kompletu na składniki i objawia się
            # dopiero jako nieudana fiskalizacja — ślad w logu pozwala go złapać
            # od razu. Nie przerywamy zapisu: dokument jest poprawny księgowo,
            # a blokowanie sprzedaży za jeden grosz byłoby gorsze niż ostrzeżenie.
            try:
                expected_gross = sum(
                    (Decimal(str(li.gross_price)) * Decimal(str(li.quantity))
                     for li in invoice_data.line_items),
                    Decimal("0"),
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                document_gross = Decimal(str(nowa_fs.KwotaDoZaplaty)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                if document_gross != expected_gross:
                    logger.warning(
                        f"Wartość FS ({document_gross} zł) różni się od kwoty zamówienia "
                        f"({expected_gross} zł) o {document_gross - expected_gross} zł. "
                        "Fiskalizacja może się nie powieść — sprawdź zaokrąglenia pozycji."
                    )
            except Exception as check_err:
                logger.debug(f"Nie udało się zweryfikować sumy dokumentu: {check_err}")

            logger.debug("ETAP 6: Zapisywanie dokumentu...")
            nowa_fs.Zapisz()
            if not nowa_fs.Identyfikator:
                try:
                    nowa_fs.WypiszBledy()
                except Exception as err:
                    logger.warning(f"Nie udało się wywołać WypiszBledy: {err}")
                raise ValueError("Nie udało się zapisać dokumentu FS w Subiekcie.")
            
            try:
                doc_id = nowa_fs.Identyfikator
                # Wymuszamy odczyt z bazy danych, ponieważ obiekt COM czasem zwraca domyślną nazwę dokumentu po zapisie
                sql = f"SELECT dok_NrPelny FROM dok__Dokument WITH (NOLOCK) WHERE dok_Id = {doc_id}"
                rs, _ = self._doc_repo.ado_connection.Execute(sql)
                if not rs.EOF:
                    utworzony_numer = rs.Fields("dok_NrPelny").Value
                else:
                    utworzony_numer = nowa_fs.NumerPelny
            except Exception as e:
                logger.warning(f"Nie udało się pobrać numeru za pomocą SQL: {e}. Próba odczytu z obiektu COM.")
                utworzony_numer = nowa_fs.NumerPelny

            logger.info(f"SUKCES! Pomyślnie utworzono FS (ze skutkiem magazynowym): {utworzony_numer}")

            # --- DODANIE FISKALIZACJI PO ZAPISIE ---
            if self._config.mappings.fiscalization_enabled and not invoice_data.customer.nip:
                fiscal_id = self._config.mappings.fiscal_printer_id
                if fiscal_id is not None:
                    dok_do_druku = None
                    try:
                        logger.debug(f"Rozpoczynam próbę fiskalizacji na drukarce o ID: {fiscal_id}")
                        dok_do_druku = self._sfera.o_subiekt.SuDokumentyManager.Wczytaj(utworzony_numer)
                        dok_do_druku.RejestrujNaUF = True
                        dok_do_druku.DrukarkaFiskalnaId = fiscal_id
                        # Wywołanie wydruku bez pokazywania okna dialogowego
                        dok_do_druku.Drukuj(False)
                        logger.info(f" -> Pomyślnie zrejestrowano dokument '{utworzony_numer}' na drukarce fiskalnej (ID: {fiscal_id}).")
                    except Exception as e:
                        logger.warning(f" -> Dokument został zapisany, ale wystąpił błąd podczas wydruku fiskalnego: {e}")
                    finally:
                        if dok_do_druku:
                            try:
                                dok_do_druku.Zamknij()
                            except Exception:
                                pass
                else:
                    logger.warning(" -> Fiskalizacja włączona, ale brak zdefiniowanego ID drukarki (fiscal_printer_id).")
            # --------------------------------------

            # ETAP 7: Opcjonalne oznaczenie do KSeF (tylko B2B z NIP)
            if self._config.mappings.ksef_enabled and invoice_data.customer.nip:
                try:
                    self._mark_for_ksef(utworzony_numer)
                except Exception as ksef_err:
                    logger.warning(
                        f"Nie udało się oznaczyć faktury '{utworzony_numer}' do KSeF: {ksef_err}. "
                        "Faktura została utworzona poprawnie."
                    )

            return utworzony_numer, "created"

        except (InvoiceNotFoundError, OutOfStockValidationError) as e:
            raise e
        except pywintypes.com_error as e:
            # Sprawdzamy, czy to błąd braku towaru w magazynie (walidacja biznesowa),
            # a nie faktyczny błąd połączenia ze Sferą.
            try:
                raw_message = e.args[2][2] if e.args and len(e.args) > 2 and e.args[2] else None
                com_message = raw_message or ""   # guard against None in e.args[2][2]
                com_hresult = e.args[2][5] if e.args and len(e.args) > 2 and e.args[2] and len(e.args[2]) > 5 else None
            except (IndexError, TypeError):
                com_message = ""
                com_hresult = None

            if "Brak towaru w magazynie" in com_message:
                logger.warning(
                    f"Walidacja magazynu nieudana podczas zapisu FS: {com_message.strip()}. "
                    "Rzucam OutOfStockValidationError (bez reconnect Sfery)."
                )
                raise OutOfStockValidationError("Brak towaru w magazynie.")

            # Błąd KSeF (np. -2147214764) lub inne błędy biznesowe Subiekta — NIE są błędem połączenia.
            # Traktujemy jako ValueError, żeby nie wywoływać reconnectu Sfery.
            KSEF_HRESULT = -2147214764
            if com_hresult == KSEF_HRESULT or "e-Faktury" in com_message or "KSeF" in com_message:
                logger.error(
                    f"Błąd biznesowy KSeF/e-Faktura podczas zapisu FS (HRESULT={com_hresult}): "
                    f"{com_message.strip()}. Rzucam ValueError (bez reconnect Sfery)."
                )
                raise ValueError(
                    f"Błąd generowania e-Faktury (KSeF): {com_message.strip() or e.strerror}. "
                    "Sprawdź poprawność danych kontrahenta (NIP, adres) oraz konfigurację KSeF w Subiekcie."
                )

            # Inny błąd COM — faktyczny problem z połączeniem; wywołujemy reconnect.
            error_details = f"Błąd COM: {e.strerror}"
            logger.exception(f"Błąd COM podczas tworzenia FS: {error_details}")
            raise SferaConnectionError(error_details)
        except ValueError as e:
            # ValueError to błąd biznesowy (np. walidacja NIP, KSeF) — NIE wyzwalamy reconnect.
            logger.error(f"Błąd walidacji danych podczas tworzenia FS: {e}")
            raise
        finally:
            if nowa_fs:
                try: nowa_fs.Zamknij()
                except Exception: logger.warning("Nie udało się poprawnie zamknąć obiektu FS.")

    def _match_kfz_target(self, position, payload_targets: dict):
        """
        Dopasowuje pozycję dokumentu KFZ do celu wyliczonego z payloadu.

        Symbole dostawcy nie muszą pokrywać się z symbolami w kartotece Subiekta — to
        właśnie dlatego ta ścieżka iteruje po pozycjach dokumentu zamiast po payloadzie.
        Przy jednym celu stosujemy go do każdej pozycji (tak działało to od początku),
        a gdy celów jest więcej, dopasowujemy po znormalizowanym symbolu i przy braku
        trafienia wolimy zostawić pozycję nietkniętą niż wpisać jej cudzy rabat.
        """
        if not payload_targets:
            return None
        if len(payload_targets) == 1:
            return next(iter(payload_targets.values()))

        position_symbol = normalize_symbol(str(position.TowarSymbol))
        product_mappings = self._config.mappings.product_mappings
        for symbol, target in payload_targets.items():
            mapped = product_mappings.get(symbol, symbol)
            if normalize_symbol(mapped) == position_symbol:
                return target
        return None

    def correct_sales_invoice(self, invoice_data: SalesInvoiceCorrectRequest) -> tuple[str, Decimal, str]:
        """Tworzy Korektę Faktury Sprzedaży (KFS) w Subiekcie na podstawie pierwotnej FS."""
        logger.info(f"Rozpoczynam proces tworzenia KFS. Dokument pierwotny: '{invoice_data.original_sales_document_number}', zamówienie: '{invoice_data.original_order_number}'")

        matches = self._doc_repo.find_fs_by_number_or_order(
            invoice_data.original_sales_document_number,
            invoice_data.original_order_number
        )
        if not matches:
            identyfikator = invoice_data.original_sales_document_number or invoice_data.original_order_number or "brak"
            raise InvoiceNotFoundError(f"Brak faktury pierwotnej {identyfikator} w Subiekcie.")

        base_fs_id = matches[0]['doc_id']
        base_fs_num = matches[0]['doc_number']

        # Korekty wystawione już do tej faktury. Nie blokujemy na tym etapie: do jednej FS
        # wolno wystawić kilka korekt (np. najpierw ilościową, potem wartościową).
        # O duplikacie rozstrzygamy niżej, po przeliczeniu wartości.
        existing_corrections = self._doc_repo.find_kfs_for_base_document(base_fs_id)
        if existing_corrections:
            logger.info(
                f"Do faktury {base_fs_num} wystawiono już {len(existing_corrections)} korekt(y): "
                f"{[c['doc_number'] for c in existing_corrections]}."
            )

        logger.info(f"Znaleziono fakturę bazową: {base_fs_num} (ID: {base_fs_id}). Tworzę KFS.")

        nowy_dok = None
        try:
            nowy_dok = self._sfera.o_subiekt.SuDokumentyManager.DodajKFS()
            nowy_dok.NaPodstawie(base_fs_id)

            issue_datetime = datetime.combine(invoice_data.issue_date, time(12, 0))
            nowy_dok.DataWystawienia = pywintypes.Time(issue_datetime)

            # FS wystawiamy licząc od cen brutto — korekta musi liczyć tak samo,
            # inaczej Subiekt przelicza pozycje od netto i wartość rozjeżdża się o grosze.
            try:
                nowy_dok.LiczonyOdCenBrutto = True
            except Exception as e:
                logger.debug(f"Nie udało się ustawić LiczonyOdCenBrutto na KFS: {e}")

            # Subiekt GT to aplikacja Windows — pole Uwagi łamie wiersz dopiero na CRLF.
            # Samo \n sklejało kolejne wpisy w jedną linię, dlatego normalizujemy też
            # uwagi przeniesione z FS przez NaPodstawie.
            note_lines = []
            existing_notes = (nowy_dok.Uwagi or "").replace("\r\n", "\n").rstrip()
            if existing_notes:
                note_lines.append(existing_notes)
            if invoice_data.correction_description:
                note_lines.append(invoice_data.correction_description.replace("\r\n", "\n").strip())
            note_lines.append(f"Przyczyna korekty: {invoice_data.correction_reason}")

            combined = "\n".join(line for line in note_lines if line)
            # Przycinamy do 500 znaków (limit dok_Uwagi) dopiero po zamianie na CRLF, żeby
            # limit liczył się tak, jak zapisze go baza; osierocony \r ucinamy.
            uwagi = combined.replace("\n", "\r\n")
            if len(uwagi) > 500:
                logger.warning(
                    f"Uwagi korekty mają {len(uwagi)} znaków i zostaną obcięte do 500 "
                    "(limit kolumny dok_Uwagi). Skróć opis korekty."
                )
            nowy_dok.Uwagi = uwagi[:500].rstrip("\r")

            # Ujęcie korekty w VAT. Domyślnie gtaUjecieKorektyTypWDacieWystawieniaKorekty (2)
            # — tak rozlicza się zwrot uzgodniony z nabywcą. Wartość 1 to ujęcie w dacie
            # faktury pierwotnej, 3 wymaga dodatkowo ustawienia UjecieKorektyData.
            try:
                nowy_dok.UjecieKorektyTyp = 2
            except Exception as e:
                logger.debug(f"Nie udało się ustawić UjecieKorektyTyp na KFS: {e}")

            # Korekty nie podlegają fiskalizacji. Ustawiamy to jawnie, bo NaPodstawie
            # kopiuje nagłówek faktury pierwotnej, a ta po wydruku ma RejestrujNaUF = True.
            try:
                nowy_dok.RejestrujNaUF = False
            except Exception as e:
                logger.debug(f"Nie udało się wyłączyć RejestrujNaUF na KFS: {e}")

            # KSeF: korekta faktury B2B idzie do KSeF tą samą flagą co faktura pierwotna
            # (dok_CzekaNaKSeF) i powinna wskazywać numer KSeF dokumentu źródłowego.
            ksef_b2b = False
            if self._config.mappings.ksef_enabled:
                ksef_b2b = bool(self._doc_repo.get_payer_nip(base_fs_id))

            if ksef_b2b:
                try:
                    nowy_dok.FormaDokumentu = 1  # gtaFormaDokumentuFakturaKSeF
                except Exception as e:
                    logger.debug(f"Nie udało się ustawić FormaDokumentu na KFS: {e}")
                try:
                    nowy_dok.RejestrujWKSeF = True
                except Exception as e:
                    logger.debug(f"Zignorowano próbę ustawienia RejestrujWKSeF na KFS: {e}")

                source_ksef = self._get_source_ksef_number(base_fs_num)
                if source_ksef:
                    try:
                        nowy_dok.DoDokumentuNumerKSeF = source_ksef
                        logger.info(f"KFS powiązana z numerem KSeF faktury pierwotnej: {source_ksef}")
                    except Exception as e:
                        logger.warning(f"Nie udało się ustawić DoDokumentuNumerKSeF: {e}")
                else:
                    logger.warning(
                        f"Faktura {base_fs_num} nie ma numeru KSeF — korekta pójdzie bez powiązania "
                        "z dokumentem źródłowym."
                    )

            # SuDokument nie ma atrybutu z tekstem przyczyny korekty — Sfera przyjmuje
            # wyłącznie SuPozycjaKorekty.PrzyczynaKorektyId wskazujący wpis słownika
            # sl_PrzyczynaKorekty. Wolny tekst z formularza zostaje w uwagach.
            reason_id = self._resolve_correction_reason_id(invoice_data.correction_reason)

            # Jedna pozycja żądania może odpowiadać wielu pozycjom dokumentu: komplet
            # rozłożony na składniki oraz rozbicie fiskalne ceny na dwie linie różniące
            # się groszem (patrz create_sales_invoice). Dlatego grupujemy pozycje po
            # TowarId i korygujemy WSZYSTKIE pasujące, a nie pierwszą znalezioną.
            positions_by_product = {}
            positions_by_symbol = {}
            document_symbols = []
            for p in nowy_dok.Pozycje:
                try:
                    towar_id = int(p.TowarId)
                except (TypeError, ValueError):
                    logger.warning(f"Pozycja '{p.TowarSymbol}' bez TowarId (usługa jednorazowa?) — pomijam w dopasowaniu.")
                    continue
                positions_by_product.setdefault(towar_id, []).append(p)
                document_symbols.append(str(p.TowarSymbol))
                symbol_key = normalize_symbol(str(p.TowarSymbol))
                if symbol_key and towar_id not in positions_by_symbol.setdefault(symbol_key, []):
                    positions_by_symbol[symbol_key].append(towar_id)

            logger.debug(f"Pozycje na KFS: {document_symbols}")

            corrected_products = set()

            if (invoice_data.correction_type or "").upper() == "FULL":
                # Korekta całkowita nie wymaga dopasowywania czegokolwiek: zerujemy
                # wszystko, co jest na fakturze. To jedyny wariant, w którym pomyłka
                # w dopasowaniu jest z definicji niemożliwa, więc nie ma powodu
                # przepuszczać go przez rozwiązywanie symboli.
                for towar_id, group in positions_by_product.items():
                    for pozycja in group:
                        pozycja.IloscJmPoKorekcie = 0.0
                        if reason_id is not None:
                            try:
                                pozycja.PrzyczynaKorektyId = reason_id
                            except Exception as e:
                                logger.debug(f"Nie udało się ustawić PrzyczynaKorektyId: {e}")
                    corrected_products.add(towar_id)
                logger.info(
                    f"Korekta całkowita faktury {base_fs_num}: wyzerowano "
                    f"{len(document_symbols)} pozycji: {document_symbols}"
                )
            else:
                available_ids = set(positions_by_product)
                unresolved = []

                for item in invoice_data.line_items:
                    present_ids = self._find_positions_for_item(
                        item, positions_by_product, positions_by_symbol, available_ids
                    )
                    if not present_ids:
                        unresolved.append(item)
                        continue

                    groups = [positions_by_product[tid] for tid in present_ids]
                    self._apply_correction_to_positions(groups, item, reason_id)
                    corrected_products.update(present_ids)
                    available_ids.difference_update(present_ids)

                # Gdy zostaje dokładnie jedna niedopasowana pozycja żądania i dokładnie
                # jedna wolna pozycja faktury, para jest jednoznaczna. Korygujemy zawsze
                # konkretną fakturę o zamkniętym zbiorze pozycji, więc to bezpieczniejsze
                # niż odesłanie błędu — ale zostawiamy głośne ostrzeżenie, bo rozjazd
                # symboli oznacza problem w mapowaniach.
                if len(unresolved) == 1 and len(available_ids) == 1:
                    leftover_id = available_ids.pop()
                    leftover_symbol = str(positions_by_product[leftover_id][0].TowarSymbol)
                    logger.warning(
                        f"Symbol '{unresolved[0].product_symbol}' nie pasuje do żadnej pozycji "
                        f"faktury {base_fs_num}, ale została dokładnie jedna wolna pozycja "
                        f"('{leftover_symbol}') i jedna nieprzypisana pozycja żądania — łączę je. "
                        "Sprawdź mapowanie produktu, bo symbol z zamówienia rozjechał się z fakturą."
                    )
                    self._apply_correction_to_positions(
                        [positions_by_product[leftover_id]], unresolved.pop(), reason_id
                    )
                    corrected_products.add(leftover_id)

                if unresolved:
                    # Cicha korekta zerowa jest gorsza niż błąd: dokument powstawał, magazyn
                    # się nie ruszał, a API zwracało sukces.
                    raise ValueError(
                        f"Nie odnaleziono na fakturze {base_fs_num} pozycji dla: "
                        f"{', '.join(i.product_symbol for i in unresolved)}. "
                        f"Pozycje na fakturze: {', '.join(repr(s) for s in document_symbols)}. "
                        "Sprawdź mapowanie symboli towarów — korekta nie została wystawiona."
                    )

            if not corrected_products:
                raise ValueError(
                    f"Żadna pozycja faktury {base_fs_num} nie została zmieniona — korekta byłaby pusta."
                )

            nowy_dok.Przelicz()
            kwota_do_zaplaty = Decimal(str(nowy_dok.KwotaDoZaplaty))
            logger.info(
                f"KFS: skorygowano {len(corrected_products)} towarów, "
                f"KwotaDoZaplaty wg Sfery = {kwota_do_zaplaty} zł."
            )

            # Idempotencja bez blokowania kolejnych korekt: ponowione zadanie Dramatiq
            # przynosi ten sam payload, a więc i tę samą wartość — to uznajemy za duplikat.
            # Korekta o innej wartości to świadome, kolejne rozliczenie tej samej faktury
            # i wolno ją wystawić.
            duplicate = next(
                (c for c in existing_corrections
                 if abs(abs(c["total_gross"]) - abs(kwota_do_zaplaty)) <= Decimal("0.01")),
                None,
            )
            if duplicate:
                logger.info(
                    f"Korekta o wartości {kwota_do_zaplaty} zł do faktury {base_fs_num} już "
                    f"istnieje ({duplicate['doc_number']}) — nie tworzę duplikatu."
                )
                return duplicate["doc_number"], duplicate["total_gross"], "existed"

            # Kwota rozliczenia idzie ZE ZNAKIEM, tak jak na korekcie zakupu
            # (create_purchase_invoice: PlatnoscKredytKwota = KwotaDoZaplaty). Wcześniej
            # było tu abs(), przez co zwrot zapisywał się jak wpłata od klienta. Znaku nie
            # potwierdza dokumentacja Sfery — decyduje analogia do ścieżki KFZ, która
            # działa na produkcji od dawna bez skarg na rozrachunki. Gdyby okazało się to
            # błędne, widać to w zakładce płatności KFS-a i wraca tu abs().
            self._handle_kfs_payment(nowy_dok, invoice_data, kwota_do_zaplaty)

            nowy_dok.Zapisz()
            if not nowy_dok.Identyfikator:
                try:
                    nowy_dok.WypiszBledy()
                except Exception as err:
                    logger.warning(f"Nie udało się wywołać WypiszBledy: {err}")
                raise ValueError("Nie udało się zapisać dokumentu KFS w Subiekcie.")

            try:
                doc_id = nowy_dok.Identyfikator
                sql = f"SELECT dok_NrPelny FROM dok__Dokument WITH (NOLOCK) WHERE dok_Id = {doc_id}"
                rs, _ = self._doc_repo.ado_connection.Execute(sql)
                if not rs.EOF:
                    utworzony_numer = rs.Fields("dok_NrPelny").Value
                else:
                    utworzony_numer = nowy_dok.NumerPelny
            except Exception as e:
                logger.warning(f"Nie udało się pobrać numeru KFS za pomocą SQL: {e}. Używam obiektu COM.")
                utworzony_numer = nowy_dok.NumerPelny

            if ksef_b2b:
                try:
                    self._mark_for_ksef(utworzony_numer)
                except Exception as ksef_err:
                    logger.warning(
                        f"Nie udało się oznaczyć korekty '{utworzony_numer}' do KSeF: {ksef_err}. "
                        "Korekta została utworzona poprawnie."
                    )

            logger.info(f"SUKCES! Pomyślnie utworzono KFS: {utworzony_numer}, Wartość różnicy: {kwota_do_zaplaty}")

            return utworzony_numer, kwota_do_zaplaty, "created"

        except pywintypes.com_error as e:
            try:
                raw_message = e.args[2][2] if e.args and len(e.args) > 2 and e.args[2] else None
                com_message = raw_message or ""
            except (IndexError, TypeError):
                com_message = ""
            error_details = f"Błąd COM: {com_message or e.strerror}"
            logger.exception(f"Błąd COM podczas tworzenia KFS: {error_details}")
            raise SferaConnectionError(error_details)
        finally:
            if nowy_dok:
                try:
                    nowy_dok.Zamknij()
                except Exception:
                    logger.warning("Nie udało się zamknąć obiektu KFS.")

    def _resolve_correction_product(self, raw_symbol: str):
        """
        Zamienia symbol z żądania korekty na (wpis kartoteki, znormalizowany symbol).

        Rozumie te same sentinele usług co wystawianie FS ($SERVICE_*), dzięki czemu
        korekta trafia dokładnie w pozycję, którą FS wcześniej dodała. Wcześniej korekta
        dopasowywała pozycje po tekstowej nazwie oferty z marketplace'u — działało to
        tylko dla nazw obecnych w product_mappings z config.json.

        Znormalizowany symbol zwracamy osobno, bo kartoteka Subiekta bywa niejednoznaczna
        (bliźniacze wpisy różniące się białymi znakami) i wywołujący potrzebuje go do
        dopasowania awaryjnego po symbolu pozycji dokumentu.
        """
        product_map = self._product_repo.get_normalized_map()
        service_map = self._config.mappings.service_mappings

        if raw_symbol.startswith('$SERVICE_'):
            final_symbol = None
            if raw_symbol == '$SERVICE_DELIVERY_PREPAID':
                final_symbol = service_map.delivery_prepaid
            elif raw_symbol == '$SERVICE_DELIVERY_COD':
                final_symbol = service_map.delivery_cod
            elif raw_symbol.startswith('$SERVICE_ADDITIONAL_'):
                service_id = raw_symbol.replace('$SERVICE_ADDITIONAL_', '')
                final_symbol = (service_map.additional_services or {}).get(service_id)

            if not final_symbol:
                logger.warning(f"Brak mapowania usługi dla sentinela '{raw_symbol}' w config.json.")
                return None, ""
            normalized = normalize_symbol(final_symbol)
            return product_map.get(normalized), normalized

        mapped_symbol = self._config.mappings.product_mappings.get(raw_symbol, raw_symbol)
        normalized = normalize_symbol(mapped_symbol)
        details = product_map.get(normalized)
        if details:
            return details, normalized

        # Dopasowanie rozmyte tylko wtedy, gdy jest jednoznaczne — przy wielu kandydatach
        # korekta trafiłaby w przypadkowy towar (dokładnie to robiła poprzednia wersja).
        candidates = [norm for norm in product_map if norm and (norm in normalized or normalized in norm)]
        if len(candidates) == 1:
            logger.info(f"Symbol '{raw_symbol}' dopasowany rozmyto do '{candidates[0]}'.")
            return product_map.get(candidates[0]), normalized
        if len(candidates) > 1:
            logger.warning(f"Symbol '{raw_symbol}' pasuje rozmyto do {len(candidates)} towarów — odmawiam zgadywania.")
        return None, normalized

    def _get_source_ksef_number(self, doc_number: str) -> Optional[str]:
        """
        Odczytuje numer KSeF faktury pierwotnej przez Sferę (SuDokument.NumerKSeF).

        Czytamy przez COM, a nie SQL-em, bo numer KSeF leży w bazie w osobnej tabeli
        pod identyfikatorem (dok_NumerKSeFId) — atrybut Sfery jest tu jedynym pewnym źródłem.
        """
        dok = None
        try:
            dok = self._sfera.o_subiekt.SuDokumentyManager.Wczytaj(doc_number)
            numer = dok.NumerKSeF
            return str(numer).strip() if numer and str(numer).strip() else None
        except Exception as e:
            logger.warning(f"Nie udało się odczytać numeru KSeF dokumentu '{doc_number}': {e}")
            return None
        finally:
            if dok:
                try:
                    dok.Zamknij()
                except Exception:
                    pass

    def _find_positions_for_item(self, item, positions_by_product, positions_by_symbol, available_ids) -> list:
        """
        Znajduje pozycje faktury odpowiadające jednej pozycji żądania korekty.

        Kolejno, od najpewniejszego do najluźniejszego:
        1. po `TowarId` z kartoteki (komplet rozwijany na składniki),
        2. po znormalizowanym symbolu pozycji dokumentu — kartoteka Subiekta zawiera
           bliźniacze wpisy różniące się białymi znakami ('CMO-MP012OC-BK' kontra
           'CMO-MP012OC-BK '), które mają osobne `tw_Id`, a `get_normalized_map`
           zostawia z nich tylko jeden,
        3. po ilości i wartości sprzed korekty — ratuje sytuację, gdy symbol
           z zamówienia rozjechał się z tym, co faktycznie poszło na fakturę.

        Każdy krok ogranicza się do pozycji **tej** faktury i akceptuje wyłącznie
        dopasowanie jednoznaczne.
        """
        details, normalized_symbol = self._resolve_correction_product(item.product_symbol)

        target_ids = self._expand_to_document_products(details) if details else []
        present_ids = [tid for tid in target_ids if tid in available_ids]
        if present_ids:
            return present_ids

        for candidate_key in (normalized_symbol, normalize_symbol(item.product_symbol)):
            if not candidate_key:
                continue
            by_symbol = [tid for tid in positions_by_symbol.get(candidate_key, []) if tid in available_ids]
            if by_symbol:
                logger.info(
                    f"Symbol '{item.product_symbol}' dopasowany po symbolu pozycji dokumentu "
                    f"(TowarId={by_symbol}) — kartoteka ma prawdopodobnie bliźniacze wpisy."
                )
                return by_symbol

        by_value = self._match_positions_by_value(item, positions_by_product, available_ids)
        if by_value:
            return by_value

        return []

    def _match_positions_by_value(self, item, positions_by_product, available_ids) -> list:
        """
        Dopasowuje pozycję żądania do pozycji faktury po ilości i wartości sprzed korekty.

        Używane, gdy symbol zawiódł — np. mapowanie oferty na towar ERP zmieniono już po
        wystawieniu faktury. Akceptujemy wyłącznie trafienie jednoznaczne; przy dwóch
        pozycjach o tej samej wartości wolimy błąd niż losowy wybór.
        """
        if item.original_quantity is None or item.original_gross_price is None:
            return []

        want_qty = float(item.original_quantity)
        want_value = want_qty * float(item.original_gross_price)
        if want_qty <= 0:
            return []

        matches = []
        for towar_id in available_ids:
            group = positions_by_product[towar_id]
            group_qty = sum(float(pozycja.IloscJm) for pozycja in group)
            group_value = sum(
                float(pozycja.IloscJm) * float(pozycja.CenaBruttoPrzedRabatem) for pozycja in group
            )
            if abs(group_qty - want_qty) > 1e-6:
                continue
            # Tolerancja grosza na pozycję: rozbicie fiskalne celowo różnicuje ceny.
            if abs(group_value - want_value) > 0.01 * len(group):
                continue
            matches.append(towar_id)

        if len(matches) == 1:
            logger.warning(
                f"Symbol '{item.product_symbol}' dopasowany po ilości i wartości "
                f"({want_qty} x {item.original_gross_price} zł), nie po symbolu. "
                "Sprawdź mapowanie produktu — symbol z zamówienia nie zgadza się z fakturą."
            )
            return matches
        if len(matches) > 1:
            logger.warning(
                f"Symbol '{item.product_symbol}' pasuje po wartości do {len(matches)} pozycji "
                "faktury — odmawiam zgadywania."
            )
        return []

    def _expand_to_document_products(self, details: dict) -> list:
        """
        Zwraca identyfikatory towarów, których należy szukać na dokumencie.

        Komplet (tw_Rodzaj = 8) nie trafia na FS jako jedna pozycja — create_sales_invoice
        rozkłada go na składniki, więc korekta musi szukać składników, nie kompletu.
        """
        product_id = int(details["id"])
        if details.get("type") != 8:
            return [product_id]

        try:
            components = self._product_repo.get_bundle_components(product_id)
        except Exception as e:
            logger.warning(f"Nie udało się pobrać składników kompletu ID={product_id}: {e}")
            return [product_id]

        if not components:
            return [product_id]

        component_ids = [int(c["id"]) for c in components]
        logger.info(f"Komplet ID={product_id} rozłożony na składniki: {component_ids}")
        return component_ids

    def _apply_correction_to_positions(self, groups, item, reason_id: Optional[int]) -> None:
        """
        Przenosi jedną pozycję żądania na pasujące pozycje dokumentu korekty.

        `groups` to lista grup pozycji — po jednej na towar znaleziony na dokumencie
        (komplet daje kilka grup, po jednej na składnik; wewnątrz grupy bywa kilka
        pozycji tego samego towaru z rozbicia fiskalnego).

        Ilość dzielimy dwustopniowo: proporcją "po korekcie / przed korektą" między grupy
        (to poprawnie skaluje składniki kompletu), a wewnątrz grupy rozdzielamy ją
        wypełniając pozycje po kolei — patrz _distribute_quantity.
        """
        symbol = item.product_symbol
        all_positions = [p for group in groups for p in group]

        target_qty = item.target_quantity
        if target_qty is not None:
            if item.original_quantity is not None and item.original_quantity > 0:
                base_qty = float(item.original_quantity)
            else:
                base_qty = sum(float(p.IloscJm) for p in all_positions)

            if base_qty > 0:
                ratio = float(target_qty) / base_qty
                for group in groups:
                    group_sum = sum(float(p.IloscJm) for p in group)
                    self._distribute_quantity(group, round(group_sum * ratio, 4))
                logger.info(
                    f"Korekta ilości '{symbol}': {base_qty} -> {target_qty} "
                    f"(proporcja {ratio:.4f} na {len(all_positions)} poz. w {len(groups)} grupach)"
                )
            else:
                logger.warning(f"Korekta ilości '{symbol}' pominięta — ilość pierwotna wynosi 0.")

        target_price = item.target_gross_price
        if target_price is not None:
            if item.original_gross_price is not None and item.original_gross_price > 0:
                ratio = float(target_price) / float(item.original_gross_price)
                for p in all_positions:
                    p.CenaBruttoPrzedRabatemPoKorekcie = round(float(p.CenaBruttoPrzedRabatem) * ratio, 2)
                logger.info(
                    f"Korekta ceny '{symbol}': {item.original_gross_price} -> {target_price} zł brutto "
                    f"(proporcja {ratio:.4f} na {len(all_positions)} poz. dokumentu)"
                )
            elif len(all_positions) == 1:
                all_positions[0].CenaBruttoPrzedRabatemPoKorekcie = float(target_price)
                logger.info(f"Korekta ceny '{symbol}': ustawiono {target_price} zł brutto.")
            else:
                logger.warning(
                    f"Korekta ceny '{symbol}' pominięta — bez original_gross_price nie da się "
                    f"rozdzielić nowej ceny na {len(all_positions)} pozycji dokumentu."
                )
        elif item.new_net_price is not None:
            if len(all_positions) == 1:
                all_positions[0].CenaNettoPrzedRabatemPoKorekcie = float(item.new_net_price)
                logger.info(f"Korekta ceny '{symbol}': ustawiono {item.new_net_price} zł netto.")
            else:
                logger.warning(
                    f"Korekta ceny netto '{symbol}' pominięta — pozycja odpowiada "
                    f"{len(all_positions)} pozycjom dokumentu."
                )

        if reason_id is not None:
            for p in all_positions:
                try:
                    p.PrzyczynaKorektyId = reason_id
                except Exception as e:
                    logger.debug(f"Nie udało się ustawić PrzyczynaKorektyId na pozycji '{symbol}': {e}")

    def _distribute_quantity(self, positions, target: float) -> None:
        """
        Rozdziela docelową ilość między pozycje tego samego towaru.

        Jeden towar bywa na dokumencie w dwóch pozycjach różniących się o grosz
        (rozbicie fiskalne w create_sales_invoice — patrz app/pricing.py). Wypełniamy
        pozycje po kolei do ich pierwotnej ilości zamiast skalować każdą proporcjonalnie:
        inaczej zwrot 1 z 2 sztuk dałby dwie pozycje po pół sztuki.
        """
        remaining = max(target, 0.0)
        for p in positions:
            available = float(p.IloscJm)
            take = min(available, remaining)
            p.IloscJmPoKorekcie = round(take, 4)
            remaining = round(remaining - take, 4)

        if remaining > 0:
            logger.warning(
                f"Ilość docelowa przekracza ilość na dokumencie o {remaining} — "
                "korekta nie może zwiększyć sprzedaży ponad pierwotną fakturę."
            )

    def _resolve_correction_reason_id(self, reason_text: str) -> Optional[int]:
        """
        Mapuje wolny tekst przyczyny korekty na pkr_Id ze słownika sl_PrzyczynaKorekty.

        Zwraca None, gdy słownik jest pusty albo nie ma dopasowania — przyczyna zostaje
        wtedy wyłącznie w uwagach dokumentu, ale korekta i tak się wystawia.
        """
        if not reason_text:
            return None

        reasons = self._doc_repo.get_correction_reasons()
        if not reasons:
            logger.warning(
                "Słownik 'Przyczyny korekty' w Subiekcie jest pusty lub niedostępny — "
                "przyczyna trafi wyłącznie do uwag dokumentu."
            )
            return None

        normalized = normalize_symbol(reason_text)

        for entry in reasons:
            if normalize_symbol(entry.get("name") or "") == normalized:
                return int(entry["id"])

        for entry in reasons:
            name_norm = normalize_symbol(entry.get("name") or "")
            if name_norm and (name_norm in normalized or normalized in name_norm):
                logger.info(f"Przyczynę '{reason_text}' dopasowano do słownikowej '{entry.get('name')}'.")
                return int(entry["id"])

        logger.warning(
            f"Przyczyny korekty '{reason_text}' nie ma w słowniku Subiekta "
            f"(dostępne: {[e.get('name') for e in reasons]}). Zostanie tylko w uwagach."
        )
        return None

    def _handle_kfs_payment(self, document_obj, request, kwota_zwrotu):
        """
        Ustawia formę zwrotu na dokumencie KFS.

        Formy nie zgadujemy: albo dostajemy jej identyfikator ze słownika Subiekta
        (payment_form_id), albo jedną z dwóch form bezidentyfikatorowych (gotówka /
        "zapłacono przelewem"), albo zgłaszamy błąd walidacji. Poprzednia wersja brała
        pierwszą z brzegu formę o fp_Typ == 0 z nieuporządkowanego wyniku SQL, przez co
        na korekcie lądowała przypadkowa metoda rozliczenia.
        """
        kwota = float(kwota_zwrotu)

        if request.payment_form_id is not None:
            forms = self._get_payment_forms_map()
            match = next(
                ((name, data) for name, data in forms.items() if data["id"] == request.payment_form_id),
                None
            )
            if not match:
                raise ValueError(
                    f"Forma płatności o identyfikatorze {request.payment_form_id} nie istnieje w Subiekcie GT."
                )
            self._set_kfs_payment_form(document_obj, request, match[0], match[1], kwota)
            return

        key = (request.payment_type or "").strip().upper()

        if not key or "GOT" in key or "CASH" in key:
            document_obj.PlatnoscGotowkaKwota = kwota
            logger.info(f"Zwrot KFS: gotówka ({kwota} zł)")
            return

        if "PRZELEW" in key or "TRANSFER" in key:
            # PlatnoscPrzelewKwota odpowiada formie "Zapłacono przelewem" — rozliczenie
            # natychmiastowe. Zwrot z terminem wymaga wskazania konkretnej formy
            # odroczonej przez payment_form_id.
            document_obj.PlatnoscPrzelewKwota = kwota
            logger.info(f"Zwrot KFS: zapłacono przelewem ({kwota} zł)")
            return

        forms = self._get_payment_forms_map()
        mapped_name = self._config.mappings.payment_type_mappings.get(key, key).strip()
        form_data = forms.get(mapped_name.upper())
        if not form_data:
            raise ValueError(
                f"Nie można ustalić formy zwrotu dla '{request.payment_type}'. "
                f"Podaj payment_form_id albo użyj 'gotówka'/'przelew'. "
                f"Formy dostępne w Subiekcie: {sorted(forms.keys())}"
            )
        self._set_kfs_payment_form(document_obj, request, mapped_name, form_data, kwota)

    def _set_kfs_payment_form(self, document_obj, request, form_name, form_data, kwota) -> None:
        """Przypisuje konkretną formę płatności ze słownika Subiekta do dokumentu KFS."""
        if self._is_card_payment_form(form_name, form_data["type"]):
            document_obj.PlatnoscKartaId = form_data["id"]
            document_obj.PlatnoscKartaKwota = kwota
            logger.info(f"Zwrot KFS: karta '{form_name}' (ID={form_data['id']}, {kwota} zł)")
            return

        document_obj.PlatnoscKredytId = form_data["id"]
        document_obj.PlatnoscKredytKwota = kwota
        if request.payment_due_date:
            due_datetime = datetime.combine(request.payment_due_date, time(23, 59))
            document_obj.PlatnoscKredytTermin = pywintypes.Time(due_datetime)
        logger.info(
            f"Zwrot KFS: płatność odroczona '{form_name}' "
            f"(ID={form_data['id']}, {kwota} zł, termin={request.payment_due_date})"
        )

    def _is_card_payment_form(self, form_name: str, form_type) -> bool:
        """
        Rozstrzyga, czy forma płatności jest kartowa.

        Pytamy słownik Subiekta — tą samą metodą co przy wystawianiu FS. fp_Typ służy
        wyłącznie jako zapasowa heurystyka, gdy słownik jest niedostępny.
        """
        try:
            return bool(self._sfera.o_subiekt.Slowniki.FormyPlatnosciKarta.Istnieje(form_name))
        except Exception as e:
            logger.warning(f"Nie udało się sprawdzić słownika kart płatniczych dla '{form_name}': {e}")
            return form_type == 1

    # --- PRYWATNE METODY POMOCNICZE DLA FS ---

    def _handle_customer(self, customer_data) -> int:
        """Wyszukuje lub tworzy kontrahenta i zwraca jego ID."""
        
        def _normalize_for_symbol(name: str) -> str:
            """Tworzy bezpieczny, skrócony fragment symbolu z podanej nazwy."""
            import re
            # Normalizacja nazwy: wielkie litery, usunięcie polskich znaków i znaków specjalnych
            safe_name = re.sub(r'[^A-Z0-9]', '', 
                name.upper()
                .replace('Ą', 'A').replace('Ć', 'C').replace('Ę', 'E')
                .replace('Ł', 'L').replace('Ń', 'N').replace('Ó', 'O')
                .replace('Ś', 'S').replace('Ź', 'Z').replace('Ż', 'Z')
            )
            return safe_name

        def _sanitize_nip(raw_nip: str) -> str:
            """Usuwa znaki niebędące cyframi z NIP-u (np. prefix 'NIP: ', myślniki, spacje)."""
            import re
            digits = re.sub(r'\D', '', raw_nip)
            return digits

        # Sanityzacja NIP – usuwa prefix "NIP: ", myślniki, spacje itp.
        if customer_data.nip:
            clean_nip = _sanitize_nip(customer_data.nip)
            if clean_nip != customer_data.nip:
                logger.info(f"NIP '{customer_data.nip}' znormalizowany do '{clean_nip}'.")
            customer_data = customer_data.model_copy(update={"nip": clean_nip if clean_nip else None})

        if customer_data.nip:
            try:
                kontrahent = self._sfera.o_subiekt.Kontrahenci.Wczytaj(customer_data.nip)
                if kontrahent:
                    logger.info(f"Znaleziono istniejącego kontrahenta '{kontrahent.Symbol}' (ID: {kontrahent.Identyfikator}).")
                    return kontrahent.Identyfikator
            except pywintypes.com_error:
                logger.debug(f"Nie znaleziono kontrahenta o NIP: {customer_data.nip}. Zostanie utworzony nowy.")
        
        logger.info("Kontrahent nie istnieje. Tworzenie nowego.")
        nowy_kh = self._sfera.o_subiekt.Kontrahenci.Dodaj()
        
        if customer_data.nip:
            # Klient firmowy
            base_name = _normalize_for_symbol(customer_data.name)
            symbol = f"SS-{base_name}"
        else:
            # Klient detaliczny
            # Dzielimy imię i nazwisko, aby złożyć w formacie NazwiskoImie
            name_parts = customer_data.name.split()
            last_name = name_parts[-1] if len(name_parts) > 1 else name_parts[0]
            first_name = name_parts[0] if len(name_parts) > 1 else ""
            
            base_name = _normalize_for_symbol(f"{last_name}{first_name}")
            symbol = f"SS-{base_name}"

        # Finalne zabezpieczenie przed przekroczeniem limitu 20 znaków Subiekta
        nowy_kh.Symbol = symbol[:20]

        # Subiekt GT ma limit 50 znaków dla pola Nazwa i 200 dla NazwaPelna
        nazwa = customer_data.name
        if len(nazwa) > 50:
            logger.warning(f"Nazwa kontrahenta '{nazwa}' przekracza 50 znaków (ma {len(nazwa)}). Zostanie przycięta do 50 znaków.")
            nazwa = nazwa[:50]
        nowy_kh.Nazwa = nazwa
        nowy_kh.NazwaPelna = customer_data.name[:200]
        nowy_kh.NIP = customer_data.nip or ""
        street = customer_data.street or ""
        street_parts = street.rsplit(' ', 1)
        if len(street_parts) > 1:
            ulica = street_parts[0]
            nr_domu = street_parts[1]
            # Heurystyka: jeśli numer domu jest zbyt długi (> 10 znaków) lub nie zawiera żadnej cyfry,
            # to prawdopodobnie cała wartość jest nazwą ulicy (np. "ul Jesionowa27" lub "ul. Zielona").
            if len(nr_domu) > 10 or not any(char.isdigit() for char in nr_domu):
                ulica = street
                nr_domu = ""
        else:
            ulica = street
            nr_domu = ""

        nowy_kh.Ulica = ulica[:60]
        nowy_kh.NrDomu = nr_domu[:10]
        nowy_kh.KodPocztowy = (customer_data.postal_code or "")[:8]
        nowy_kh.Miejscowosc = (customer_data.city or "")[:40]
        nowy_kh.Zapisz()
        kontrahent_id = nowy_kh.Identyfikator
        logger.info(f"Utworzono nowego kontrahenta. Symbol: {nowy_kh.Symbol}, ID: {kontrahent_id}")
        return kontrahent_id

    def _map_line_item_products(self, line_items) -> dict:
        """
        Mapuje symbole produktów i usług z żądania na ich szczegóły (ID i typ) z Subiekta.
        Zwraca słownik: { index_pozycji: {"id": 123, "type": 1} }
        """
        product_map = self._product_repo.get_normalized_map()
        service_map = self._config.mappings.service_mappings
        product_mappings = self._config.mappings.product_mappings
        
        details_map = {}
        missing_items = []
        
        for i, item in enumerate(line_items):
            symbol = item.product_symbol
            details = None
            
            logger.debug(f"Przetwarzanie pozycji {i}: symbol z requestu = '{symbol}'")
            
            # Logika dla usług
            if symbol.startswith('$SERVICE_'):
                final_symbol = None
                if symbol == '$SERVICE_DELIVERY_PREPAID':
                    final_symbol = service_map.delivery_prepaid
                elif symbol == '$SERVICE_DELIVERY_COD':
                    final_symbol = service_map.delivery_cod
                elif symbol.startswith('$SERVICE_ADDITIONAL_'):
                    service_id = symbol.replace('$SERVICE_ADDITIONAL_', '')
                    final_symbol = (service_map.additional_services or {}).get(service_id)
                
                if final_symbol:
                    normalized_service_symbol = normalize_symbol(final_symbol)
                    logger.debug(f" -> Usługa. Szukany znormalizowany symbol: '{normalized_service_symbol}'")
                    details = product_map.get(normalized_service_symbol)
                
                if not details:
                    missing_items.append(f"Usługa '{final_symbol or symbol}'")

            # Logika dla produktów
            else:
                original_symbol = symbol
                
                # Najpierw sprawdzamy jawne mapowania
                if original_symbol in product_mappings:
                    mapped_symbol = product_mappings[original_symbol]
                    logger.debug(f"Użyto jawnego mapowania: '{original_symbol}' -> '{mapped_symbol}'")
                    normalized_input = normalize_symbol(mapped_symbol)
                else:
                    normalized_input = normalize_symbol(original_symbol)
                
                logger.debug(f" -> Produkt. Szukany znormalizowany symbol: '{normalized_input}'")
                details = product_map.get(normalized_input)
                
                if not details: # Fuzzy match
                    found_symbol = next((norm for norm in product_map if norm in normalized_input or normalized_input in norm), None)
                    if found_symbol: details = product_map.get(found_symbol)

                if not details:
                    missing_items.append(original_symbol)

            if details:
                logger.debug(f" -> Znaleziono dopasowanie dla pozycji {i}. Szczegóły: {details}")
                details_map[i] = details

        if missing_items:
            raise InvoiceNotFoundError(f"Nie znaleziono towarów/usług w Subiekcie: {', '.join(missing_items)}")
        
        return details_map
    
    def _handle_payment(self, document_obj, invoice_data):
        """Ustawia płatność na dokumencie Sfery."""
        logger.debug("ETAP 5: Ustawianie formy płatności z mapowań konfiguracyjnych.")
        payment_map = self._config.mappings.payment_type_mappings
        payment_type_key = invoice_data.payment_type.upper()

        # 1. Sprawdź dokładne dopasowanie klucza (np. "CASH_ON_DELIVERY:SUUS")
        if payment_type_key in payment_map:
            payment_type_name = payment_map[payment_type_key].strip()
            logger.debug(f"Forma płatności: dokładne dopasowanie klucza '{payment_type_key}'.")
        # 2. Fallback do ogólnego "CASH_ON_DELIVERY" dla nieznanych kurierów COD
        elif payment_type_key.startswith("CASH_ON_DELIVERY") and "CASH_ON_DELIVERY" in payment_map:
            payment_type_name = payment_map["CASH_ON_DELIVERY"].strip()
            logger.warning(
                f"Brak specyficznego mapowania dla '{payment_type_key}'. "
                f"Używam fallbacku 'CASH_ON_DELIVERY' -> '{payment_type_name}'."
            )
        else:
            raise ValueError(
                f"Brak zdefiniowanego mapowania dla typu płatności '{invoice_data.payment_type}' w pliku config.json. "
                f"Dostępne klucze: {list(payment_map.keys())}"
            )
        
        all_payment_forms = self._get_payment_forms_map()
        payment_form_details = all_payment_forms.get(payment_type_name.upper())
        if not payment_form_details:
            raise ValueError(f"Forma płatności '{payment_type_name}' (zmapowana z '{invoice_data.payment_type}') nie istnieje w Subiekcie GT.")
        
        payment_form_id = payment_form_details["id"]
        payment_form_type = payment_form_details["type"]
        
        # Sprawdzamy czy forma płatności istnieje w słowniku kart płatniczych Subiekta
        is_karta = False
        try:
            is_karta = self._sfera.o_subiekt.Slowniki.FormyPlatnosciKarta.Istnieje(payment_type_name)
        except Exception as e:
            logger.warning(f"Błąd podczas sprawdzania słownika kart płatniczych Subiekta dla '{payment_type_name}': {e}")
            is_karta = (payment_form_type == 1)

        logger.info(f"Używam formy płatności '{payment_type_name}' o ID: {payment_form_id}, Typ: {payment_form_type}, Czy karta/pobranie: {is_karta}.")
        
        document_obj.Przelicz()
        kwota_do_zaplaty = document_obj.KwotaDoZaplaty

        if is_karta:
            document_obj.PlatnoscKartaId = payment_form_id
            document_obj.PlatnoscKartaKwota = kwota_do_zaplaty
        else:
            document_obj.PlatnoscKredytId = payment_form_id
            document_obj.PlatnoscKredytKwota = kwota_do_zaplaty
            document_obj.PlatnoscKredytTermin = pywintypes.Time(datetime.combine(invoice_data.payment_due_date, time(23, 59)))

    def _get_payment_forms_map(self) -> dict:
        """
        Pobiera mapę form płatności.
        TODO: W przyszłości przenieść do dedykowanego PaymentFormRepository i dodać cachowanie.
        """
        logger.info("Odpytuję bazę o formy płatności (metoda SQL)...")
        ado_recordset = None
        try:
            ado_connection = self._sfera.ado_connection
            sql_query = "SELECT fp_Id, fp_Nazwa, fp_Typ FROM sl_FormaPlatnosci"
            ado_recordset, _ = ado_connection.Execute(sql_query)
            
            forms_map = {}
            while not ado_recordset.EOF:
                nazwa = ado_recordset.Fields("fp_Nazwa").Value
                if nazwa:
                    nazwa_stripped = nazwa.strip()
                    forms_map[nazwa_stripped.upper()] = {
                        "id": ado_recordset.Fields("fp_Id").Value,
                        "type": ado_recordset.Fields("fp_Typ").Value
                    }
                    if nazwa_stripped != nazwa:
                        logger.debug(
                            f"Forma platnosci ID={ado_recordset.Fields('fp_Id').Value}: "
                            f"usunieto biale znaki z nazwy: {repr(nazwa)} -> {repr(nazwa_stripped)}"
                        )
                ado_recordset.MoveNext()
            
            logger.info(f"Załadowano {len(forms_map)} form płatności.")
            return forms_map
        except Exception as e:
            logger.error(f"Krytyczny błąd podczas pobierania form płatności przez SQL: {e}")
            return {}
        finally:
            if ado_recordset and ado_recordset.State != 0: ado_recordset.Close()

    def _mark_for_ksef(self, doc_number: str) -> None:
        """
        Oznacza fakturę sprzedaży jako oczekującą na wysyłkę do KSeF
        poprzez ustawienie flagi dok_CzekaNaKSeF = 1 w bazie danych.
        Wykonywane tylko dla faktur B2B (z NIP kontrahenta) gdy ksef_enabled = true.
        """
        ado_recordset = None
        try:
            ado_connection = self._sfera.ado_connection
            # Znajdź ID dokumentu po jego pełnym numerze
            sql_find = f"SELECT dok_Id FROM dok__Dokument WITH (NOLOCK) WHERE dok_NrPelny = '{doc_number}'"
            ado_recordset, _ = ado_connection.Execute(sql_find)

            if ado_recordset.EOF:
                logger.warning(f"Nie znaleziono dokumentu '{doc_number}' w bazie do oznaczenia KSeF.")
                return

            dok_id = ado_recordset.Fields("dok_Id").Value
            ado_recordset.Close()
            ado_recordset = None

            # Ustaw flagę CzekaNaKSeF
            sql_update = f"UPDATE dok__Dokument SET dok_CzekaNaKSeF = 1 WHERE dok_Id = {dok_id}"
            ado_connection.Execute(sql_update)
            logger.info(f"Faktura '{doc_number}' (ID: {dok_id}) została oznaczona do wysyłki do KSeF.")

        except Exception as e:
            logger.error(f"Błąd SQL podczas oznaczania faktury '{doc_number}' do KSeF: {e}")
            raise
        finally:
            if ado_recordset and ado_recordset.State != 0:
                ado_recordset.Close()

    def export_document_to_pdf(self, doc_number: str, file_path: str) -> None:
        """
        Eksportuje dokument o podanym numerze pełnym do pliku PDF za pomocą Sfery.
        """
        logger.info(f"Rozpoczynam eksport dokumentu '{doc_number}' do pliku: {file_path}")
        
        # Jeśli nie odnaleziono KFS bezpośrednio pod wirtualnym numerem (często tworzonym w aplikacji matki z numeru FS)
        if doc_number.upper().startswith("KFS"):
            # Najpierw sprawdźmy czy istnieje w bazie bezpośrednio
            sql_check = f"SELECT dok_Id FROM dok__Dokument WHERE dok_Typ = 6 AND dok_NrPelny = '{doc_number}'"
            try:
                rs_check, _ = self._doc_repo.ado_connection.Execute(sql_check)
                exists = not rs_check.EOF
                rs_check.Close()
            except Exception:
                exists = False
                
            if not exists:
                # Zamieniamy KFS na FS w numerze wirtualnym, np. KFS 18408/MAG/2026 -> FS 18408/MAG/2026
                fs_number = "FS" + doc_number[3:]
                logger.info(f"PDF export: Wirtualny numer KFS '{doc_number}' nie istnieje bezpośrednio. Próbuję odnaleźć rzeczywisty numer KFS dla faktury bazowej '{fs_number}'...")
                
                sql_resolve = f"""
                    SELECT d.dok_NrPelny 
                    FROM dok__Dokument d
                    WHERE d.dok_Typ = 6
                      AND d.dok_DoDokId IN (
                          SELECT fs.dok_Id FROM dok__Dokument fs
                          WHERE fs.dok_Typ = 2 AND fs.dok_NrPelny = '{fs_number}'
                      )
                """
                try:
                    rs_res, _ = self._doc_repo.ado_connection.Execute(sql_resolve)
                    if not rs_res.EOF:
                        actual_kfs_number = rs_res.Fields("dok_NrPelny").Value
                        logger.info(f"PDF export: Zmapowano wirtualny numer '{doc_number}' na rzeczywisty numer Subiekta: '{actual_kfs_number}'")
                        doc_number = actual_kfs_number
                    rs_res.Close()
                except Exception as e:
                    logger.warning(f"Błąd podczas szukania rzeczywistego numeru KFS przez SQL: {e}")

        try:
            mgr = self._sfera.o_subiekt.SuDokumentyManager
            dok = mgr.Wczytaj(doc_number)
        except pywintypes.com_error as e:
            logger.exception(f"Błąd COM podczas wczytywania dokumentu '{doc_number}'")
            raise SferaConnectionError(f"Błąd COM podczas wczytywania dokumentu ze Sfery: {e}")

        if not dok:
            logger.warning(f"Dokument '{doc_number}' nie został odnaleziony w Subiekcie.")
            raise InvoiceNotFoundError(f"Dokument o numerze '{doc_number}' nie istnieje w Subiekcie.")

        try:
            # 0 to wartość gtaTypPlikuPDF w Sferze GT
            dok.DrukujDoPliku(file_path, 0)
            logger.info(f"Pomyślnie zapisano PDF dla dokumentu '{doc_number}' do pliku: {file_path}")
        except pywintypes.com_error as e:
            logger.exception(f"Błąd COM podczas eksportu do PDF dla dokumentu '{doc_number}'")
            raise SferaConnectionError(f"Błąd COM podczas generowania pliku PDF w Sferze: {e}")
        finally:
            try:
                dok.Zamknij()
            except Exception:
                pass