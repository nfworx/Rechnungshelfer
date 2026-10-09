"""Abbildung einer berechneten Getreideabrechnung auf eine Gutschrift."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from rechnungshelfer.domain.grain_models import (
    GrainDelivery,
    GrainValidationError,
    RuleDirection,
    SettlementBatchResult,
    SettlementResult,
    SettlementStatus,
)
from rechnungshelfer.domain.models import DocumentType, Invoice, InvoiceItem


_CENT = Decimal("0.01")
_SUPPORTED_VAT_RATES = {Decimal("0"), Decimal("7"), Decimal("7.8"), Decimal("19")}
_GRAIN_TYPE_LABELS = {
    "wheat": "Weizen",
    "barley": "Gerste (Futtergerste)",
    "malting_barley": "Braugerste",
    "oats": "Hafer",
    "rye": "Roggen",
    "maize": "Mais",
    "rapeseed": "Raps",
}


def create_grain_settlement_invoice(
    template: Invoice,
    deliveries: tuple[GrainDelivery, ...],
    settlement: SettlementBatchResult,
    vat_rate: Decimal,
) -> Invoice:
    """Erzeugt eine centgenaue Gutschrift, ohne die Vorlage zu verändern.

    Jede Lieferung wird als eine Position mit Menge eins und ihrem bereits
    berechneten Netto-Endbetrag abgebildet. Die fachlichen Mengen und
    Rechenschritte bleiben dadurch in der Beschreibung nachvollziehbar, ohne
    in der Rechnungsberechnung ein zweites Mal angewendet zu werden.
    """

    rate = Decimal(str(vat_rate))
    _validate_mapping_input(template, deliveries, settlement, rate)

    results_by_id = {
        delivery_result.delivery_id: delivery_result
        for delivery_result in settlement.delivery_results
    }
    invoice = deepcopy(template)
    invoice.items = [
        _invoice_item(
            position=index,
            delivery=delivery,
            result=results_by_id[delivery.id],
            vat_rate=rate,
        )
        for index, delivery in enumerate(deliveries, start=1)
    ]
    invoice.calculate(force=True)

    expected_net = _money(settlement.net_amount)
    if invoice.monetarytotal.tax_exclusive_amount != expected_net:
        raise GrainValidationError(
            "Die Gutschrift stimmt nicht mit dem Netto-Abrechnungsbetrag überein."
        )
    return invoice


def _validate_mapping_input(
    template: Invoice,
    deliveries: tuple[GrainDelivery, ...],
    settlement: SettlementBatchResult,
    vat_rate: Decimal,
) -> None:
    if template.document_type is not DocumentType.SELF_BILLED_INVOICE:
        raise GrainValidationError(
            "Eine Getreideabrechnung kann nur als Gutschrift erzeugt werden."
        )
    if vat_rate not in _SUPPORTED_VAT_RATES:
        raise GrainValidationError("Der gewählte Steuersatz wird nicht unterstützt.")
    if not deliveries:
        raise GrainValidationError("Die Abrechnung benötigt mindestens eine Lieferung.")
    if settlement.status is not SettlementStatus.CALCULATED or any(
        result.status is not SettlementStatus.CALCULATED
        for result in settlement.delivery_results
    ):
        raise GrainValidationError(
            "Nur vollständig berechnete Lieferungen können übernommen werden."
        )

    delivery_ids = [delivery.id for delivery in deliveries]
    result_ids = [result.delivery_id for result in settlement.delivery_results]
    if (
        len(delivery_ids) != len(set(delivery_ids))
        or len(result_ids) != len(set(result_ids))
        or set(delivery_ids) != set(result_ids)
    ):
        raise GrainValidationError(
            "Lieferungen und Berechnungsergebnisse passen nicht zusammen."
        )

    supplier_numbers = {delivery.supplier_number for delivery in deliveries}
    if supplier_numbers != {settlement.supplier_number}:
        raise GrainValidationError(
            "Lieferant der Lieferungen und Berechnungsergebnis stimmen nicht überein."
        )
    if template.seller.supplier_number != settlement.supplier_number:
        raise GrainValidationError(
            "Lieferant der Gutschrift und Getreideabrechnung stimmen nicht überein."
        )

    results_by_id = {result.delivery_id: result for result in settlement.delivery_results}
    for delivery in deliveries:
        result = results_by_id[delivery.id]
        if (
            result.scheme_version_id != settlement.scheme_version_id
            or result.gross_quantity_kg != delivery.gross_quantity_kg
        ):
            raise GrainValidationError(
                f"Berechnungsergebnis für Wiegeschein {delivery.ticket_number} ist veraltet."
            )

    calculated_net = _money(
        sum((result.net_amount for result in settlement.delivery_results), Decimal("0"))
    )
    if calculated_net != _money(settlement.net_amount):
        raise GrainValidationError(
            "Summe der Lieferungen und Netto-Abrechnungsbetrag stimmen nicht überein."
        )


def _invoice_item(
    *,
    position: int,
    delivery: GrainDelivery,
    result: SettlementResult,
    vat_rate: Decimal,
) -> InvoiceItem:
    grain_label = _GRAIN_TYPE_LABELS.get(
        delivery.grain_type_code,
        delivery.grain_type_code,
    )
    item = InvoiceItem(
        pos=str(position),
        name=f"Getreideabrechnung {grain_label} – {delivery.ticket_number}",
        description=_description(delivery, result, grain_label),
        qty=Decimal("1"),
        unit="C62",
        price_without_discount=_money(result.net_amount),
        discount=Decimal("0"),
        vat=vat_rate,
    )
    item.set_vat(vat_rate)
    return item


def _description(
    delivery: GrainDelivery,
    result: SettlementResult,
    grain_label: str,
) -> str:
    lines = [
        f"Lieferdatum: {_date_de(delivery.delivery_date)}",
        f"Wiegeschein: {delivery.ticket_number}",
        f"Getreideart: {grain_label}",
        f"Ursprungsmenge: {_number(result.gross_quantity_kg, 3)} kg",
    ]
    if delivery.measurements:
        measurements = "; ".join(
            f"{measurement.feature_code}: {_number(measurement.effective_value, 2)}"
            for measurement in delivery.measurements
        )
        lines.append(f"Analysewerte: {measurements}")

    lines.extend(
        f"Mengenabzug – {deduction.label}: "
        f"-{_number(deduction.deducted_quantity_kg, 3)} kg"
        for deduction in result.quantity_deductions
        if deduction.deducted_quantity_kg != 0
    )
    lines.extend(
        (
            f"{_adjustment_label(adjustment.direction)} – {adjustment.label}: "
            f"{_signed_money(adjustment.amount_delta)} EUR"
        )
        for adjustment in result.monetary_adjustments
        if adjustment.amount_delta != 0
    )
    lines.extend(
        (
            f"Abrechnungsmenge: {_number(result.settlement_quantity_kg, 3)} kg",
            f"Basispreis: {_number(result.base_price_per_tonne, 2)} EUR/t",
            f"Ausgangswarenwert: {_number(result.base_amount, 2)} EUR",
            f"Abrechnungsbetrag: {_number(result.net_amount, 2)} EUR",
        )
    )
    return "\n".join(lines)


def _adjustment_label(direction: RuleDirection) -> str:
    return "Zuschlag" if direction is RuleDirection.SURCHARGE else "Preis-/Kostenabzug"


def _signed_money(value: Decimal) -> str:
    prefix = "+" if value > 0 else ""
    return prefix + _number(value, 2)


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def _number(value: Decimal, decimal_places: int) -> str:
    quantizer = Decimal("1").scaleb(-decimal_places)
    rendered = f"{Decimal(value).quantize(quantizer, rounding=ROUND_HALF_UP):,.{decimal_places}f}"
    return rendered.replace(",", "_").replace(".", ",").replace("_", ".")


def _date_de(value: date) -> str:
    return value.strftime("%d.%m.%Y")
