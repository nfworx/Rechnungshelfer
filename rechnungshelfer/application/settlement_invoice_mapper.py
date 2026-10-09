"""Abbildung einer geprüften PDF-Abrechnung auf eine editierbare Gutschrift."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP

from rechnungshelfer.domain.models import DocumentType, Invoice, InvoiceItem
from rechnungshelfer.services.format_service import parse_de


_CENT = Decimal("0.01")
_SUPPORTED_VAT_RATES = {Decimal("0"), Decimal("7"), Decimal("7.8"), Decimal("19")}


def create_settlement_invoice(template: Invoice, review) -> Invoice:
    """Erzeugt ohne Neuberechnung der fachlichen Abrechnung eine Gutschrift."""

    if template.document_type is not DocumentType.SELF_BILLED_INVOICE:
        raise ValueError("Die Abrechnung kann nur in eine Gutschrift übernommen werden.")

    advance_payment = parse_de(review.advance_payment.value)
    if advance_payment != 0:
        raise ValueError(
            "Abrechnungen mit Abschlagszahlungen können noch nicht in das "
            "Gutschriftformular übernommen werden."
        )

    vat_rate = parse_de(review.vat_rate.value)
    if vat_rate not in _SUPPORTED_VAT_RATES:
        raise ValueError(
            f"Der erkannte Steuersatz {review.vat_rate.value} % wird nicht unterstützt."
        )

    invoice = deepcopy(template)
    invoice.info.invoice_number = review.credit_note_number.value.strip()
    invoice.info.invoice_date = review.credit_note_date.value.strip()
    invoice.info.delivery_date = ""
    invoice.info.payment_due_date = ""
    invoice.info.delivery_note = ""
    invoice.items = [
        _invoice_item(index, delivery, vat_rate)
        for index, delivery in enumerate(review.deliveries, start=1)
    ]
    invoice.calculate(force=True)

    expected_net = _money(parse_de(review.net_amount.value))
    expected_vat = _money(parse_de(review.vat_amount.value))
    expected_total = _money(parse_de(review.credit_amount.value))
    actual_vat = _money(sum((tax.amount for tax in invoice.taxtotal), Decimal("0")))
    if invoice.monetarytotal.tax_exclusive_amount != expected_net:
        raise ValueError("Die Positionssumme stimmt nicht mit der Nettosumme überein.")
    if actual_vat != expected_vat:
        raise ValueError("Die berechnete Umsatzsteuer stimmt nicht mit der Abrechnung überein.")
    if invoice.monetarytotal.payable_amount != expected_total:
        raise ValueError("Der Auszahlungsbetrag stimmt nicht mit der Abrechnung überein.")
    return invoice


def _invoice_item(position: int, delivery, vat_rate: Decimal) -> InvoiceItem:
    amount = _money(parse_de(delivery.net_amount.value))
    item = InvoiceItem(
        pos=str(position),
        name=(
            f"Getreideabrechnung {delivery.grain_name.value.strip()} – "
            f"{delivery.ticket_number.value.strip()}"
        ),
        description=_description(delivery),
        qty=Decimal("1"),
        unit="C62",
        price_without_discount=amount,
        discount=Decimal("0"),
        vat=vat_rate,
    )
    item.set_vat(vat_rate)
    return item


def _description(delivery) -> str:
    lines = [
        f"Lieferschein: {delivery.ticket_number.value.strip()}",
        f"Lieferdatum: {delivery.delivery_date.value.strip()}",
        f"Bezeichnung: {delivery.grain_name.value.strip()}",
        f"Ursprungsmenge: {delivery.gross_quantity_kg.value.strip()} kg",
    ]
    for detail in delivery.details:
        parts = [
            f"{detail.label.value.strip()}: {detail.analysis_value.value.strip()}"
        ]
        if detail.quantity_change_kg.value.strip():
            parts.append(f"Mengenänderung {detail.quantity_change_kg.value.strip()} kg")
        if detail.price_change_per_tonne.value.strip():
            parts.append(
                f"Preisänderung {detail.price_change_per_tonne.value.strip()} EUR/t"
            )
        lines.append("; ".join(parts))
    lines.extend(
        (
            f"Abrechnungsmenge: {delivery.settlement_quantity_kg.value.strip()} kg",
            f"Basispreis: {delivery.base_price_per_tonne.value.strip()} EUR/t",
            "Abrechnungspreis: "
            f"{delivery.settlement_price_per_tonne.value.strip()} EUR/t",
            f"Abrechnungsbetrag: {delivery.net_amount.value.strip()} EUR",
        )
    )
    return "\n".join(lines)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


__all__ = ["create_settlement_invoice"]
