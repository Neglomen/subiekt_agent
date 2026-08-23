"""
Testy arytmetyki cen przy rozkładzie kompletu na składniki.

`app.pricing` jest czysty (bez COM i bez Sfery), więc tę logikę da się sprawdzić
bez Subiekta i bez Windows — a to właśnie ona odpowiadała za rozjazdy o grosze
i nieudane fiskalizacje.
"""
import random
from decimal import Decimal

import pytest

from app.pricing import lines_total, split_gross_into_fiscal_lines, to_grosze


def test_dzieli_sie_rowno_to_jedna_pozycja():
    """Typowy przypadek nie może zmieniać wyglądu faktury — ma zostać jeden wiersz."""
    assert split_gross_into_fiscal_lines("59.94", 6) == [(Decimal("6"), Decimal("9.99"))]


def test_zestaw_szesciu_workow_rozbity_na_dwie_ceny():
    """
    Regresja zgłoszonego przypadku: 49,99 zł na 6 sztuk.

    Wcześniej wychodziła cena 8,3317, którą drukarka fiskalna zaokrąglała do 8,33
    i liczyła 6 × 8,33 = 49,98 — brakowało grosza i fiskalizacja nie przechodziła.
    """
    lines = split_gross_into_fiscal_lines("49.99", 6)

    assert lines == [(Decimal("5"), Decimal("8.33")), (Decimal("1"), Decimal("8.34"))]
    assert lines_total(lines) == Decimal("49.99")


@pytest.mark.parametrize(
    "total, qty",
    [("49.99", 6), ("100.00", 6), ("29.90", 6), ("19.99", 3), ("0.05", 6), ("7.77", 7)],
)
def test_suma_pozycji_jest_dokladnie_rowna_wartosci(total, qty):
    lines = split_gross_into_fiscal_lines(total, qty)

    assert lines_total(lines) == Decimal(total)


@pytest.mark.parametrize(
    "total, qty",
    [("49.99", 6), ("100.00", 6), ("29.90", 6), ("0.05", 6), ("1234.56", 37)],
)
def test_kazda_cena_ma_najwyzej_dwa_miejsca_po_przecinku(total, qty):
    """Sedno poprawki: cena z 4 miejscami jest niefiskalizowalna."""
    for _, price in split_gross_into_fiscal_lines(total, qty):
        assert -price.as_tuple().exponent <= 2, f"cena {price} ma za dużo miejsc po przecinku"


def test_ilosci_sumuja_sie_do_wejsciowej():
    """Podział nie może zgubić ani dołożyć sztuk."""
    for qty in range(1, 40):
        lines = split_gross_into_fiscal_lines("49.99", qty)
        assert sum(q for q, _ in lines) == Decimal(qty)


def test_losowe_kwoty_i_ilosci_zawsze_sie_zgadzaja():
    """Wyczerpujące sprawdzenie niezmiennika na losowej próbce."""
    rnd = random.Random(20260823)  # ustalony seed — test ma być powtarzalny
    for _ in range(5000):
        total = (Decimal(rnd.randint(1, 500_000)) / 100).quantize(Decimal("0.01"))
        qty = rnd.randint(1, 60)

        lines = split_gross_into_fiscal_lines(total, qty)

        assert lines_total(lines) == total
        assert sum(q for q, _ in lines) == Decimal(qty)
        assert all(-p.as_tuple().exponent <= 2 for _, p in lines)


def test_ilosc_ulamkowa_zwraca_jedna_pozycje():
    """Kilogramów nie da się rozbić na grosze — wtedy jedna pozycja i zaokrąglenie."""
    lines = split_gross_into_fiscal_lines("19.99", "1.5")

    assert lines == [(Decimal("1.5"), Decimal("13.33"))]


def test_zerowa_ilosc_nie_tworzy_pozycji():
    assert split_gross_into_fiscal_lines("10.00", 0) == []


def test_wartosc_ujemna_zachowuje_znak():
    """Korekty mogą mieć wartości ujemne — podział nie może gubić znaku."""
    lines = split_gross_into_fiscal_lines("-49.99", 6)

    assert lines_total(lines) == Decimal("-49.99")


def test_to_grosze_zaokragla_polowke_w_gore():
    assert to_grosze("0.005") == 1
    assert to_grosze("8.3317") == 833
    assert to_grosze("49.99") == 4999
