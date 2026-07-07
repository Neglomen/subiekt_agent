import logging
import pywintypes
from datetime import datetime, time
from decimal import Decimal

from app.config import AppConfig
from app.exceptions import InvoiceNotFoundError, OutOfStockValidationError, SferaConnectionError
from app.repositories.document_repository import DocumentRepository
from app.repositories.product_repository import ProductRepository, normalize_symbol
from app.schemas import SalesInvoiceCreateRequest, InvoiceCreateRequest, InvoiceCheckRequest
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
                
                if not details:  # Fuzzy match
                    found_symbol = next(
                        (norm for norm in product_map if norm in normalized_input or normalized_input in norm), None
                    )
                    if found_symbol:
                        details = product_map.get(found_symbol)

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
            if doc_type == "KFZ" and invoice_data.corrected_invoice_number:
                matches = self._doc_repo.find_by_original_number(invoice_data.corrected_invoice_number)
                if matches:
                    base_fz_id = matches[0]['doc_id']
                    logger.info(f"Znaleziono fakturę bazową w bazie: {matches[0]['doc_number']} (ID: {base_fz_id}). Tworzę korektę powiązaną.")

            # Tworzymy odpowiedni typ dokumentu w Sferze
            if doc_type == "KFZ":
                if base_fz_id:
                    nowy_dok = self._sfera.o_subiekt.SuDokumentyManager.DodajKFZ()
                    nowy_dok.NaPodstawie(base_fz_id)
                else:
                    nowy_dok = self._sfera.o_subiekt.SuDokumentyManager.DodajKFZn()
                    logger.info("Tworzenie dokumentu jako KFZn (korekta do nieistniejącego).")
                    nowy_dok.DoDokumentuNumerPelny = invoice_data.corrected_invoice_number or "Brak"
                
                issue_datetime = datetime.combine(invoice_data.issue_date, time(12, 0))
                if not base_fz_id:
                    nowy_dok.DoDokumentuDataWystawienia = pywintypes.Time(issue_datetime)
            else:
                nowy_dok = self._sfera.o_subiekt.SuDokumentyManager.DodajFZ()
                issue_datetime = datetime.combine(invoice_data.issue_date, time(12, 0))
            
            nowy_dok.KontrahentId = kontrahent.Identyfikator
            nowy_dok.NumerOryginalny = safe_original_number
            nowy_dok.DataWystawienia = pywintypes.Time(issue_datetime)
            nowy_dok.DataOtrzymania = pywintypes.Time(issue_datetime)
            nowy_dok.LiczonyOdCenNetto = True
            
            for i, (item, adjusted_price) in enumerate(adjusted_goods):
                if float(item.quantity) == 0:
                    logger.debug(f"Pominięto pozycję o zerowej ilości w dokumencie: {item.product_symbol}")
                    continue
                
                details = product_details_map[i]
                
                if doc_type == "KFZ" and base_fz_id:
                    # Szukamy pozycji na istniejącej korekcie (stworzonej przez NaPodstawie)
                    target_pos = None
                    for p in nowy_dok.Pozycje:
                        if p.TowarId == details["id"]:
                            target_pos = p
                            break
                    
                    if target_pos:
                        # Skoryguj ilość: stan przed - ilość zwracana
                        target_pos.IloscJmPoKorekcie = float(target_pos.IloscJm) - float(item.quantity)
                        target_pos.CenaNettoPrzedRabatemPoKorekcie = float(adjusted_price)
                    else:
                        # Jeśli pozycji nie było na oryginale, dodajemy ją jako nową na korekcie
                        pozycja = nowy_dok.Pozycje.Dodaj(details["id"])
                        pozycja.IloscJm = 0.0
                        pozycja.IloscJmPoKorekcie = float(item.quantity)
                        pozycja.CenaNettoPrzedRabatem = float(adjusted_price)
                        pozycja.CenaNettoPrzedRabatemPoKorekcie = float(adjusted_price)
                else:
                    # Standardowa ścieżka (KFZn lub FZ)
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
        # Bezpieczne przycięcie do 30 znaków
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
            
            if invoice_data.original_order_number:
                nowa_fs.Uwagi = str(invoice_data.original_order_number)
            
            nowa_fs.LiczonyOdCenBrutto = True
            logger.debug(" -> Ustawiono dane nagłówka (Kontrahent, Numery, Daty, Liczenie od brutto).")

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
                        
                        comp_unit_price = round(item_gross_value / comp_qty, 4) if comp_qty > 0 else 0.0

                        pozycja = nowa_fs.Pozycje.Dodaj(comp["id"])
                        pozycja.IloscJm = comp_qty
                        pozycja.CenaBruttoPrzedRabatem = comp_unit_price
                        logger.debug(
                            f"    -> Składnik: {comp['symbol']} (ID: {comp['id']}), "
                            f"Ilość: {comp_qty}, Cena bazowa: {get_base_price(comp, price_level):.2f}, "
                            f"Cena jednostkowa FS: {comp_unit_price:.4f}, Wartość brutto: {item_gross_value:.2f}"
                        )
                else:
                    pozycja = nowa_fs.Pozycje.Dodaj(details["id"])
                    pozycja.IloscJm = float(item.quantity)
                    # Używamy ceny PRZED rabatem, aby dać Subiektowi kontrolę
                    pozycja.CenaBruttoPrzedRabatem = float(item.gross_price)
                    logger.debug(f" -> Dodano pozycję {i} (ID: {details['id']}, Typ: {details['type']}, Cena Brutto: {item.gross_price})")

            self._handle_payment(nowa_fs, invoice_data)

            logger.debug("ETAP 6: Zapisywanie dokumentu...")
            nowa_fs.Zapisz()
            
            try:
                doc_id = nowa_fs.Id
                # Wymuszamy odczyt z bazy danych, ponieważ obiekt COM czasem zwraca domyślną nazwę dokumentu po zapisie
                sql = f"SELECT dok_NrPelny FROM dok__Dokument WHERE dok_Id = {doc_id}"
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
        street_parts = customer_data.street.rsplit(' ', 1)
        nowy_kh.Ulica = street_parts[0]
        nowy_kh.NrDomu = street_parts[1] if len(street_parts) > 1 else ''
        nowy_kh.KodPocztowy = customer_data.postal_code
        nowy_kh.Miejscowosc = customer_data.city
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
            sql_find = f"SELECT dok_Id FROM dok__Dokument WHERE dok_NrPelny = '{doc_number}'"
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