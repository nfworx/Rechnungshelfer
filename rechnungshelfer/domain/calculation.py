"""Reine Berechnungsregeln fuer Rechnungspositionen und Belegsummen."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


CENT = Decimal("0.01")
HUNDRED = Decimal("100")
ZERO = Decimal("0.00")


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def round_money(value: object) -> Decimal:
    """Rundet einen Wert kaufmaennisch auf zwei Nachkommastellen."""
    return _decimal(value).quantize(CENT, ROUND_HALF_UP)


@dataclass(frozen=True)
class LineCalculation:
    price: Decimal
    net: Decimal


@dataclass(frozen=True)
class TaxLine:
    net: Decimal
    vat_percent: Decimal
    tax_category: str


@dataclass(frozen=True)
class TaxGroupCalculation:
    amount: Decimal
    taxable_amount: Decimal
    tax_category: str
    percent: Decimal


@dataclass(frozen=True)
class InvoiceCalculation:
    tax_categories: tuple[str, ...]
    tax_groups: tuple[TaxGroupCalculation, ...]
    line_extension_amount: Decimal
    tax_exclusive_amount: Decimal
    tax_inclusive_amount: Decimal
    payable_amount: Decimal


def calculate_line(
    price_without_discount: object,
    discount: object,
    quantity: object,
    *,
    price_base_quantity: object = 1,
    adjustment_total: object = 0,
) -> LineCalculation:
    """Berechnet rabattierten Einzelpreis und Netto-Positionssumme."""
    price = _decimal(price_without_discount) - _decimal(discount)
    if price < 0:
        price = ZERO
    base_quantity = _decimal(price_base_quantity)
    if base_quantity <= 0:
        raise ValueError("Preisbasismenge muss größer als null sein.")

    rounded_price = round_money(price)
    net = round_money(
        rounded_price * _decimal(quantity) / base_quantity
        + _decimal(adjustment_total)
    )
    return LineCalculation(price=rounded_price, net=net)


def calculate_invoice(lines: Iterable[TaxLine]) -> InvoiceCalculation:
    """Berechnet Steuergruppen und Belegsummen aus fertigen Positionen."""
    line_values = tuple(lines)
    sum_net = round_money(sum(line.net for line in line_values))
    vat_by_group: dict[tuple[Decimal, str], Decimal] = {}
    taxable_by_group: dict[tuple[Decimal, str], Decimal] = {}
    tax_categories: list[str] = []

    for line in line_values:
        rate = line.vat_percent
        category = "Z" if rate == 0 else (line.tax_category or "S")
        tax_categories.append(category)
        key = (rate, category)
        vat_by_group[key] = vat_by_group.get(key, ZERO) + line.net * rate / HUNDRED
        taxable_by_group[key] = taxable_by_group.get(key, ZERO) + line.net

    tax_groups = tuple(
        TaxGroupCalculation(
            amount=round_money(amount),
            taxable_amount=round_money(taxable_by_group[(rate, category)]),
            tax_category=category,
            percent=rate,
        )
        for (rate, category), amount in vat_by_group.items()
    )
    total_vat = round_money(sum(group.amount for group in tax_groups))
    gross = round_money(sum_net + total_vat)

    return InvoiceCalculation(
        tax_categories=tuple(tax_categories),
        tax_groups=tax_groups,
        line_extension_amount=sum_net,
        tax_exclusive_amount=sum_net,
        tax_inclusive_amount=gross,
        payable_amount=gross,
    )
