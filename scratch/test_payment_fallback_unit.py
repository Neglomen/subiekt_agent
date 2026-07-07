# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

"""
Test jednostkowy logiki fallbacku form platnosci w _handle_payment.
Nie wymaga polaczenia ze Sfera / Subiektem GT.

Uruchomienie:
    poetry run python scratch/test_payment_fallback_unit.py
"""

payment_map = {
    "ONLINE": "Allegro Delivery",
    "CASH_ON_DELIVERY": "Pobranie Kurier APACZKA",
    "CASH_ON_DELIVERY:INPOST": "Pobranie kurier InPost",
    "CASH_ON_DELIVERY:SUUS": "Pobranie Kurier SUUS",
    "CASH_ON_DELIVERY:DHL": "Pobranie kurier DHL",
}

def resolve_payment_name(payment_type: str, payment_map: dict) -> str:
    """Odwzorowanie logiki z document_service._handle_payment."""
    payment_type_key = payment_type.upper()

    if payment_type_key in payment_map:
        return payment_map[payment_type_key]
    elif payment_type_key.startswith("CASH_ON_DELIVERY") and "CASH_ON_DELIVERY" in payment_map:
        return payment_map["CASH_ON_DELIVERY"]
    else:
        raise ValueError(
            f"Brak mapowania dla '{payment_type}'. Dostępne klucze: {list(payment_map.keys())}"
        )


test_cases = [
    # (payment_type z backendu,        oczekiwana nazwa formy płatności,    opis)
    ("ONLINE",                          "Allegro Delivery",                  "Płatność online - dokładne dopasowanie"),
    ("CASH_ON_DELIVERY",                "Pobranie Kurier APACZKA",           "Standardowe pobranie - dokładne dopasowanie"),
    ("CASH_ON_DELIVERY:INPOST",         "Pobranie kurier InPost",            "Pobranie InPost - dokładne dopasowanie"),
    ("CASH_ON_DELIVERY:SUUS",           "Pobranie Kurier SUUS",              "Pobranie SUUS - dokładne dopasowanie"),
    ("CASH_ON_DELIVERY:DHL",            "Pobranie kurier DHL",               "Pobranie DHL - dokładne dopasowanie"),
    ("CASH_ON_DELIVERY:DPD",            "Pobranie Kurier APACZKA",           "Pobranie DPD (brak mapowania) - fallback na CASH_ON_DELIVERY"),
    ("CASH_ON_DELIVERY:NOWY_KURIER",    "Pobranie Kurier APACZKA",           "Nieznany kurier COD - fallback na CASH_ON_DELIVERY"),
    ("cash_on_delivery:suus",           "Pobranie Kurier SUUS",              "Małe litery - normalizacja .upper()"),
]

error_cases = [
    ("PRZELEW",      "Nieznany typ - powinien rzucić ValueError"),
    ("GOTOWKA",      "Gotówka - brak w konfiguracji"),
]

RESET  = ""
GREEN  = ""
RED    = ""
YELLOW = ""
BOLD   = ""

print(f"\n{BOLD}=== Testy poprawnych mapowań ==={RESET}")
passed = 0
failed = 0
for payment_type, expected_name, desc in test_cases:
    try:
        result = resolve_payment_name(payment_type, payment_map)
        if result == expected_name:
            print(f"  [PASS]  [{desc}]")
            print(f"         '{payment_type}' -> '{result}'")
            passed += 1
        else:
            print(f"  [FAIL]  [{desc}]")
            print(f"         '{payment_type}' -> '{result}' (oczekiwano: '{expected_name}')")
            failed += 1
    except Exception as e:
        print(f"  [ERROR] [{desc}]: {e}")
        failed += 1

print(f"\n{BOLD}=== Testy błędnych typów (oczekiwane ValueError) ==={RESET}")
for payment_type, desc in error_cases:
    try:
        result = resolve_payment_name(payment_type, payment_map)
        print(f"  [FAIL]  [{desc}] - oczekiwano wyjatku, dostano: '{result}'")
        failed += 1
    except ValueError as e:
        print(f"  [PASS]  [{desc}]")
        print(f"         ValueError: {e}")
        passed += 1
    except Exception as e:
        print(f"  [ERROR] [{desc}] - nieoczekiwany wyjatek: {e}")
        failed += 1

total = passed + failed
status = "OK" if failed == 0 else "BLAD"
print(f"\nWynik [{status}]: {passed}/{total} testow zaliczonych\n")
