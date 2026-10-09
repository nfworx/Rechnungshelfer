"""Deterministische, synthetische Testabrechnung.

Der Generator bildet nur die fuer den spaeteren Import relevante Struktur einer
Sammel-Final-Gutschrift nach. Die PDF besteht aus einem Rasterbild und hat
bewusst keine auslesbare Textschicht, damit Integrationstests den OCR-Pfad
durchlaufen.
"""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import os
from pathlib import Path
import sys
import tempfile
import threading

from PIL import Image, ImageDraw, ImageFont


_CENT = Decimal("0.01")
_TEMP_PREFIX = "rechnungshelfer-testabrechnung-"
_temporary_files: set[Path] = set()
_temporary_files_lock = threading.Lock()


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
    supplier_number: str
    supplier_name: str
    supplier_street: str
    supplier_postcode: str
    supplier_city: str
    supplier_country: str
    supplier_phone: str
    supplier_email: str
    supplier_vat: str
    supplier_tax_number: str
    supplier_registry_number: str
    supplier_contact_name: str
    supplier_buyer_reference: str
    iban: str
    bic: str
    account_holder: str
    payment_terms: str
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
    supplier_number="1001",
    supplier_name="Musterhof Testlieferant",
    supplier_street="Feldweg 12",
    supplier_postcode="54321",
    supplier_city="Musterdorf",
    supplier_country="DE",
    supplier_phone="+49 9876 543210",
    supplier_email="musterlieferant@example.de",
    supplier_vat="DE987654321",
    supplier_tax_number="12/345/67890",
    supplier_registry_number="HRA 12345",
    supplier_contact_name="Erika Muster",
    supplier_buyer_reference="1001",
    iban="DE89370400440532013000",
    bic="TESTDEFFXXX",
    account_holder="Musterhof Testlieferant",
    payment_terms="Auszahlung innerhalb von 14 Tagen.",
    deliveries=_DELIVERIES,
    vat_rate=_VAT_RATE,
    net_amount=_NET_AMOUNT,
    vat_amount=_VAT_AMOUNT,
    advance_payment=Decimal("0.00"),
    credit_amount=_NET_AMOUNT + _VAT_AMOUNT,
)


def _font(size: int, *, bold: bool = False):
    root = (
        Path(sys._MEIPASS)
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[2]
    )
    filename = "LMRoman10-Bold.ttf" if bold else "LMRoman10-Regular.ttf"
    font_path = root / "assets" / "fonts" / filename
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

    draw.text(
        (left, 275),
        "SYNTHETISCHE TESTDATEN - NICHT PRODUKTIV VERWENDEN",
        font=small_font,
        fill="black",
    )
    supplier_lines = (
        f"Lieferantennummer: {document.supplier_number}",
        f"Lieferant: {document.supplier_name}",
        f"Strasse: {document.supplier_street}",
        f"PLZ Ort: {document.supplier_postcode} {document.supplier_city}",
        f"Land: {document.supplier_country}",
        f"Telefon: {document.supplier_phone}",
        f"E-Mail: {document.supplier_email}",
        f"USt-IdNr.: {document.supplier_vat}",
        f"Steuernummer: {document.supplier_tax_number}",
        f"Handelsregister: {document.supplier_registry_number}",
        f"Kontaktperson: {document.supplier_contact_name}",
        f"Kaeuferreferenz: {document.supplier_buyer_reference}",
    )
    payment_lines = (
        f"IBAN: {document.iban}",
        f"BIC: {document.bic}",
        f"Kontoinhaber: {document.account_holder}",
        f"Zahlungsbedingungen: {document.payment_terms}",
    )
    for index, text in enumerate(supplier_lines):
        draw.text(
            (left, 335 + index * 43),
            text,
            font=small_font,
            fill="black",
        )
    for index, text in enumerate(payment_lines):
        draw.text((left, 870 + index * 43), text, font=small_font, fill="black")

    table_y = 1080
    draw.text((170, table_y), "Analyse-", font=small_font, fill="black")
    draw.text((170, table_y + 37), "werte", font=small_font, fill="black")
    draw.text((470, table_y), "Bezeichnung", font=header_font, fill="black")
    _right(draw, quantity_x, table_y, "Menge", header_font)
    _right(draw, price_x, table_y, "Preis", header_font)
    _right(draw, price_x, table_y + 37, "EUR je t", small_font)
    _right(draw, amount_x, table_y, "Betrag", header_font)
    _right(draw, amount_x, table_y + 37, "EUR", small_font)
    draw.text((category_x, table_y), "M", font=small_font, fill="black")
    draw.text((category_x, table_y + 37), "S", font=small_font, fill="black")
    draw.line((left, table_y + 95, right, table_y + 95), fill="black", width=3)

    y = table_y + 155
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


def create_temporary_test_settlement_pdf() -> Path:
    """Erzeugt eine registrierte Testabrechnung im System-Temp-Verzeichnis."""

    descriptor, filename = tempfile.mkstemp(prefix=_TEMP_PREFIX, suffix=".pdf")
    os.close(descriptor)
    path = Path(filename).resolve()
    try:
        create_test_settlement_pdf(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    with _temporary_files_lock:
        _temporary_files.add(path)
    return path


def remove_temporary_test_settlement_pdf(path: str | Path) -> bool:
    """Entfernt ausschließlich eine in dieser Sitzung registrierte Test-PDF."""

    candidate = Path(path).resolve()
    with _temporary_files_lock:
        if candidate not in _temporary_files:
            return False
        _temporary_files.remove(candidate)
    try:
        candidate.unlink(missing_ok=True)
    except OSError:
        with _temporary_files_lock:
            _temporary_files.add(candidate)
        return False
    return True


def cleanup_temporary_test_settlement_pdfs() -> int:
    """Bereinigt noch registrierte Test-PDFs beim normalen Programmende."""

    with _temporary_files_lock:
        paths = tuple(_temporary_files)
    return sum(remove_temporary_test_settlement_pdf(path) for path in paths)


atexit.register(cleanup_temporary_test_settlement_pdfs)


__all__ = [
    "EXPECTED_TEST_SETTLEMENT",
    "TestSettlementDelivery",
    "TestSettlementDocument",
    "cleanup_temporary_test_settlement_pdfs",
    "create_test_settlement_pdf",
    "create_temporary_test_settlement_pdf",
    "remove_temporary_test_settlement_pdf",
]
