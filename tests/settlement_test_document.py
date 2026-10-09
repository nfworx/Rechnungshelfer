"""Deterministische, synthetische Testabrechnung.

Der Generator bildet nur die fuer den spaeteren Import relevante Struktur einer
Sammel-Final-Gutschrift nach. Die PDF besteht aus einem Rasterbild und hat
bewusst keine auslesbare Textschicht, damit Integrationstests den OCR-Pfad
durchlaufen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


_CENT = Decimal("0.01")
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FONT_REGULAR = _PROJECT_ROOT / "assets" / "fonts" / "LMRoman10-Regular.ttf"
_FONT_BOLD = _PROJECT_ROOT / "assets" / "fonts" / "LMRoman10-Bold.ttf"


@dataclass(frozen=True)
class TestSettlementDelivery:
    ticket_number: str
    delivery_date: date
    grain_name: str
    gross_quantity_kg: Decimal
    dockage_percent: Decimal
    quantity_deduction_kg: Decimal
    hectolitre_weight: Decimal
    price_deduction_per_tonne: Decimal
    settlement_quantity_kg: Decimal
    base_price_per_tonne: Decimal
    settlement_price_per_tonne: Decimal
    net_amount: Decimal


@dataclass(frozen=True)
class TestSettlementDocument:
    credit_note_number: str
    credit_note_date: date
    deliveries: tuple[TestSettlementDelivery, ...]
    vat_rate: Decimal
    net_amount: Decimal
    vat_amount: Decimal
    advance_payment: Decimal
    credit_amount: Decimal


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def _delivery(
    ticket_number: str,
    delivery_date: date,
    gross_quantity_kg: str,
    quantity_deduction_kg: str,
    hectolitre_weight: str,
    price_deduction_per_tonne: str,
) -> TestSettlementDelivery:
    gross = Decimal(gross_quantity_kg)
    quantity_deduction = Decimal(quantity_deduction_kg)
    base_price = Decimal("160.00")
    price_deduction = Decimal(price_deduction_per_tonne)
    settlement_quantity = gross - quantity_deduction
    settlement_price = base_price - price_deduction
    net_amount = _money(settlement_quantity * settlement_price / Decimal("1000"))
    return TestSettlementDelivery(
        ticket_number=ticket_number,
        delivery_date=delivery_date,
        grain_name="Hafer lose",
        gross_quantity_kg=gross,
        dockage_percent=Decimal("1.00"),
        quantity_deduction_kg=quantity_deduction,
        hectolitre_weight=Decimal(hectolitre_weight),
        price_deduction_per_tonne=price_deduction,
        settlement_quantity_kg=settlement_quantity,
        base_price_per_tonne=base_price,
        settlement_price_per_tonne=settlement_price,
        net_amount=net_amount,
    )


_DELIVERIES = (
    _delivery("T1001", date(2025, 8, 9), "2815", "28", "40.00", "15.50"),
    _delivery("T1002", date(2025, 8, 10), "3765", "37", "41.00", "15.50"),
    _delivery("T1003", date(2025, 8, 14), "6352", "63", "41.00", "15.50"),
    _delivery("T1004", date(2025, 8, 15), "1645", "16", "42.70", "14.30"),
)
_NET_AMOUNT = sum((delivery.net_amount for delivery in _DELIVERIES), Decimal("0"))
_VAT_RATE = Decimal("7.8")
_VAT_AMOUNT = _money(_NET_AMOUNT * _VAT_RATE / Decimal("100"))

EXPECTED_TEST_SETTLEMENT = TestSettlementDocument(
    credit_note_number="91001",
    credit_note_date=date(2025, 11, 30),
    deliveries=_DELIVERIES,
    vat_rate=_VAT_RATE,
    net_amount=_NET_AMOUNT,
    vat_amount=_VAT_AMOUNT,
    advance_payment=Decimal("0.00"),
    credit_amount=_NET_AMOUNT + _VAT_AMOUNT,
)


def _font(size: int, *, bold: bool = False):
    font_path = _FONT_BOLD if bold else _FONT_REGULAR
    return ImageFont.truetype(str(font_path), size=size)


def _number(value: Decimal, decimal_places: int) -> str:
    rendered = f"{value:,.{decimal_places}f}"
    return rendered.replace(",", "_").replace(".", ",").replace("_", ".")


def _date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _right(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font) -> None:
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (right - left), y), text, font=font, fill="black")


def create_test_settlement_pdf(
    output_path: str | Path,
    document: TestSettlementDocument = EXPECTED_TEST_SETTLEMENT,
) -> Path:
    """Erzeugt eine einseitige, bildbasierte Testabrechnung als PDF."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (2480, 3508), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(43, bold=True)
    header_font = _font(32, bold=True)
    body_font = _font(34)
    body_bold = _font(34, bold=True)
    small_font = _font(30)

    left = 125
    right = 2350
    quantity_x = 1430
    price_x = 1770
    amount_x = 2160
    category_x = 2290

    draw.text((left, 105), "SAMMEL - FINAL - GUTSCHRIFT", font=title_font, fill="black")
    draw.text(
        (left, 170),
        f"Nr.: {document.credit_note_number} vom {_date(document.credit_note_date)}",
        font=header_font,
        fill="black",
    )
    draw.line((left, 245, right, 245), fill="black", width=4)

    draw.text((170, 275), "Analyse-", font=small_font, fill="black")
    draw.text((170, 312), "werte", font=small_font, fill="black")
    draw.text((470, 275), "Bezeichnung", font=header_font, fill="black")
    _right(draw, quantity_x, 275, "Menge", header_font)
    _right(draw, price_x, 275, "Preis", header_font)
    _right(draw, price_x, 312, "EUR je t", small_font)
    _right(draw, amount_x, 275, "Betrag", header_font)
    _right(draw, amount_x, 312, "EUR", small_font)
    draw.text((category_x, 275), "M", font=small_font, fill="black")
    draw.text((category_x, 312), "S", font=small_font, fill="black")
    draw.line((left, 370, right, 370), fill="black", width=3)

    y = 430
    for delivery in document.deliveries:
        draw.text(
            (330, y),
            f"Lieferschein-Nr.: {delivery.ticket_number} vom {_date(delivery.delivery_date)}",
            font=body_bold,
            fill="black",
        )
        y += 55
        draw.text((470, y), delivery.grain_name, font=body_font, fill="black")
        _right(draw, quantity_x, y, _number(delivery.gross_quantity_kg, 0), body_font)
        _right(draw, price_x, y, _number(delivery.base_price_per_tonne, 2), body_font)
        draw.text((category_x, y), "2", font=body_font, fill="black")
        y += 48
        draw.text(
            (470, y),
            f"{_number(delivery.dockage_percent, 2)} % Besatz",
            font=body_font,
            fill="black",
        )
        _right(draw, quantity_x, y, f"-{_number(delivery.quantity_deduction_kg, 0)}", body_font)
        y += 48
        draw.text(
            (470, y),
            f"{_number(delivery.hectolitre_weight, 2)} % HL-Gewicht",
            font=body_font,
            fill="black",
        )
        _right(
            draw,
            price_x,
            y,
            f"-{_number(delivery.price_deduction_per_tonne, 2)}",
            body_font,
        )
        y += 48
        draw.text((470, y), delivery.grain_name, font=body_font, fill="black")
        _right(draw, quantity_x, y, _number(delivery.settlement_quantity_kg, 0), body_font)
        _right(draw, price_x, y, _number(delivery.settlement_price_per_tonne, 2), body_font)
        _right(draw, amount_x, y, _number(delivery.net_amount, 2), body_bold)
        draw.text((category_x, y), "2", font=body_font, fill="black")
        y += 82

    draw.line((left, y, right, y), fill="black", width=3)
    y += 42
    draw.text(
        (770, y),
        f"{_number(document.vat_rate, 1)} % Mehrwertsteuer EUR",
        font=body_bold,
        fill="black",
    )
    _right(draw, amount_x, y - 44, _number(document.net_amount, 2), body_bold)
    _right(draw, amount_x, y, _number(document.vat_amount, 2), body_bold)
    y += 80
    draw.line((700, y, right, y), fill="black", width=3)
    y += 25
    draw.text((700, y), "Gesamtbetrag", font=body_bold, fill="black")
    _right(draw, amount_x, y, _number(document.net_amount + document.vat_amount, 2), body_bold)
    y += 52
    draw.text((700, y), "Abschlagszahlung", font=body_font, fill="black")
    _right(draw, amount_x, y, _number(document.advance_payment, 2), body_font)
    y += 70
    draw.line((700, y, right, y), fill="black", width=3)
    y += 25
    draw.text((700, y), "Gutschriftbetrag in EUR", font=body_bold, fill="black")
    _right(draw, amount_x, y, _number(document.credit_amount, 2), body_bold)
    y += 58
    draw.line((700, y, right, y), fill="black", width=5)
    draw.line((700, y + 10, right, y + 10), fill="black", width=2)

    image.save(path, format="PDF", resolution=300.0)
    return path


__all__ = [
    "EXPECTED_TEST_SETTLEMENT",
    "TestSettlementDelivery",
    "TestSettlementDocument",
    "create_test_settlement_pdf",
]
