# Plik: subiekt_agent/app/pricing.py
"""
Arytmetyka cen dla dokumentów sprzedaży.

Moduł jest celowo czysty — bez COM, bez Sfery i bez konfiguracji — żeby dało się go
przetestować bez Subiekta i bez Windows.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple

GROSZ = Decimal("0.01")

# Pozycja dokumentu: (ilość, cena jednostkowa brutto)
FiscalLine = Tuple[Decimal, Decimal]


def to_grosze(amount) -> int:
    """Zamienia kwotę na liczbę groszy (int), zaokrąglając w górę od połowy."""
    return int((Decimal(str(amount)) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def split_gross_into_fiscal_lines(total_gross, quantity) -> List[FiscalLine]:
    """
    Rozbija wartość brutto pozycji na pozycje (ilość, cena jednostkowa) tak, żeby:

    * każda cena jednostkowa miała najwyżej 2 miejsca po przecinku,
    * suma `ilość × cena` była DOKŁADNIE równa wartości wejściowej.

    Po co to jest
    -------------
    Drukarka fiskalna nie dostaje wartości pozycji — liczy ją sama, z ceny jednostkowej
    podanej w groszach. Cena z czterema miejscami po przecinku (np. 8,3317, jaka wychodzi
    przy dzieleniu kompletu na składniki) jest przez nią zaokrąglana do 8,33, a wtedy
    6 × 8,33 = 49,98 zamiast 49,99. Faktura przestaje się zgadzać o grosz i fiskalizacja
    nie przechodzi. Problem pojawia się tylko wtedy, gdy cena nie dzieli się równo przez
    ilość — dlatego bywa nieregularny.

    Gdy wartość nie dzieli się równo, zwracane są DWIE pozycje różniące się o grosz:

        >>> split_gross_into_fiscal_lines("49.99", 6)
        [(Decimal('5'), Decimal('8.33')), (Decimal('1'), Decimal('8.34'))]

    a gdy dzieli się równo — jedna, więc typowa faktura nie zmienia wyglądu:

        >>> split_gross_into_fiscal_lines("59.94", 6)
        [(Decimal('6'), Decimal('9.99'))]

    Ilości niecałkowite
    -------------------
    Dla ilości ułamkowych (np. 1,5 kg) podziału w groszach wykonać się nie da — zwracana
    jest jedna pozycja z ceną zaokrągloną do 2 miejsc. Wywołujący powinien wtedy sprawdzić
    sumę przez `lines_total`, bo może się różnić od wartości docelowej.
    """
    total = Decimal(str(total_gross)).quantize(GROSZ, rounding=ROUND_HALF_UP)
    qty = Decimal(str(quantity))

    if qty <= 0:
        return []

    if qty != qty.to_integral_value():
        unit = (total / qty).quantize(GROSZ, rounding=ROUND_HALF_UP)
        return [(qty, unit)]

    q = int(qty)
    total_gr = to_grosze(total)
    sign = -1 if total_gr < 0 else 1
    base, rem = divmod(abs(total_gr), q)

    if rem == 0:
        return [(Decimal(q), (Decimal(sign * base) / 100).quantize(GROSZ))]

    # `rem` sztuk droższych o grosz dokłada dokładnie brakującą resztę:
    # (q - rem) * base + rem * (base + 1) == q * base + rem == total_gr
    return [
        (Decimal(q - rem), (Decimal(sign * base) / 100).quantize(GROSZ)),
        (Decimal(rem), (Decimal(sign * (base + 1)) / 100).quantize(GROSZ)),
    ]


def lines_total(lines: List[FiscalLine]) -> Decimal:
    """Suma `ilość × cena` dla listy pozycji, zaokrąglona do grosza."""
    return sum(
        (qty * price for qty, price in lines),
        Decimal("0"),
    ).quantize(GROSZ, rounding=ROUND_HALF_UP)
