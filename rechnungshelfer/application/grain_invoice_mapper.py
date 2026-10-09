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
from rechnungshelfer.domain.models import (
    Buyer,
    Delivery,
    DocumentType,
    Invoice,
    InvoiceInfo,
    InvoiceItem,
    InvoiceItemProperty,
    InvoiceLineAdjustment,
    Payment,
    Seller,
)


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


def create_invoice_from_grain_credit_note(note) -> Invoice:
    """Projiziert einen bestätigten Endbeleg verlustfrei in das Exportmodell."""

    _validate_credit_note_for_export(note)
    buyer = Buyer(
        **{
            field: getattr(note.buyer, field)
            for field in note.buyer.__dataclass_fields__
        },
        use_invoice_address_as_delivery=True,
    )
    invoice = Invoice(
        seller=Seller(
            **{
                field: getattr(note.supplier, field)
                for field in note.supplier.__dataclass_fields__
            }
        ),
        buyer=buyer,
        delivery=Delivery(
            name=buyer.name,
            street=buyer.street,
            postcode=buyer.postcode,
            city=buyer.city,
            country=buyer.country,
        ),
        info=InvoiceInfo(
            invoice_number=note.credit_note_number,
            invoice_date=_date_de(note.credit_note_date),
            delivery_date=_date_de(
                max(delivery.delivery_date for delivery in note.deliveries)
            ),
            payment_due_date=_date_de(note.payment_due_date),
            invoice_type_code="389",
        ),
        payment=Payment(
            **{
                field: getattr(note.payment, field)
                for field in note.payment.__dataclass_fields__
            }
        ),
        items=[
            _credit_note_item(index, delivery, note.vat_rate)
            for index, delivery in enumerate(note.deliveries, start=1)
        ],
        document_type=DocumentType.SELF_BILLED_INVOICE,
    )
    invoice.monetarytotal.prepaid_amount = _money(note.advance_payment)
    invoice.calculate(force=True)
    if invoice.monetarytotal.tax_exclusive_amount != _money(note.net_amount):
        raise GrainValidationError(
            "Export-Nettosumme stimmt nicht mit der Getreidegutschrift überein."
        )
    if sum(tax.amount for tax in invoice.taxtotal) != _money(note.vat_amount):
        raise GrainValidationError(
            "Export-Umsatzsteuer stimmt nicht mit der Getreidegutschrift überein."
        )
    if invoice.monetarytotal.payable_amount != _money(note.credit_amount):
        raise GrainValidationError(
            "Export-Auszahlungsbetrag stimmt nicht mit der Getreidegutschrift überein."
        )
    return invoice


def _credit_note_item(position, delivery, vat_rate):
    adjustments = tuple(
        InvoiceLineAdjustment(
            amount=abs(detail.amount_change),
            is_charge=detail.amount_change > 0,
            reason=detail.label,
        )
        for detail in delivery.details
        if detail.amount_change not in (None, Decimal("0"))
    )
    properties = [
        InvoiceItemProperty("Lieferscheinnummer", delivery.ticket_number),
        InvoiceItemProperty("Lieferdatum", _date_de(delivery.delivery_date)),
        InvoiceItemProperty(
            "Ursprungsmenge (kg)",
            _plain_number(delivery.gross_quantity_kg),
        ),
        InvoiceItemProperty(
            "Basispreis (EUR/t)",
            _plain_number(delivery.base_price_per_tonne),
        ),
    ]
    for detail in delivery.details:
        properties.append(
            InvoiceItemProperty(
                f"Analyse – {detail.label}",
                _plain_number(detail.analysis_value),
            )
        )
        for value, suffix in (
            (detail.quantity_change_kg, "Mengenänderung (kg)"),
            (detail.price_change_per_tonne, "Preisänderung (EUR/t)"),
            (detail.amount_change, "Betragsänderung (EUR)"),
        ):
            if value is not None:
                properties.append(
                    InvoiceItemProperty(
                        f"{suffix} – {detail.label}",
                        _plain_number(value),
                    )
                )
    item = InvoiceItem(
        pos=str(position),
        name=f"Getreideabrechnung {delivery.grain_name}",
        description=_credit_note_description(delivery),
        qty=delivery.settlement_quantity_kg,
        unit="KGM",
        price_without_discount=delivery.settlement_price_per_tonne,
        price_base_quantity=Decimal("1000"),
        price_base_unit="KGM",
        item_properties=tuple(properties),
        line_adjustments=adjustments,
        discount=Decimal("0"),
        vat=vat_rate,
    )
    item.set_vat(vat_rate)
    if item.net != _money(delivery.net_amount):
        raise GrainValidationError(
            f"Lieferbetrag für Lieferschein {delivery.ticket_number} ist "
            "mit Menge, Preis und Zu-/Abschlägen nicht konsistent."
        )
    return item


def _credit_note_description(delivery):
    lines = [
        f"Lieferschein: {delivery.ticket_number}",
        f"Lieferdatum: {_date_de(delivery.delivery_date)}",
        f"Ursprungsmenge: {_number(delivery.gross_quantity_kg, 3)} kg",
        f"Abrechnungsmenge: {_number(delivery.settlement_quantity_kg, 3)} kg",
        f"Basispreis: {_number(delivery.base_price_per_tonne, 2)} EUR/t",
        f"Abrechnungspreis: {_number(delivery.settlement_price_per_tonne, 2)} EUR/t",
    ]
    lines.extend(
        f"{detail.label}: {_plain_number(detail.analysis_value)}"
        for detail in delivery.details
    )
    return "\n".join(lines)


def _validate_credit_note_for_export(note):
    if note.payment_due_date is None:
        raise GrainValidationError("Auszahlungsdatum fehlt.")
    rate = Decimal(str(note.vat_rate))
    if rate not in _SUPPORTED_VAT_RATES:
        raise GrainValidationError("Der gewählte Steuersatz wird nicht unterstützt.")
    required = (
        (note.supplier.supplier_number, "Lieferantennummer"),
        (note.supplier.name, "Lieferantenname"),
        (note.supplier.street, "Lieferantenstraße"),
        (note.supplier.postcode, "Lieferanten-PLZ"),
        (note.supplier.city, "Lieferantenort"),
        (note.supplier.country, "Lieferantenland"),
        (note.supplier.email, "Lieferanten-E-Mail"),
        (note.buyer.name, "Name des eigenen Betriebs"),
        (note.buyer.street, "Straße des eigenen Betriebs"),
        (note.buyer.postcode, "PLZ des eigenen Betriebs"),
        (note.buyer.city, "Ort des eigenen Betriebs"),
        (note.buyer.country, "Land des eigenen Betriebs"),
        (note.buyer.email, "E-Mail des eigenen Betriebs"),
        (note.buyer.leitweg_id, "Käuferreferenz des eigenen Betriebs"),
        (note.payment.iban, "IBAN"),
        (note.payment.bic, "BIC"),
        (note.payment.account_holder, "Kontoinhaber"),
        (note.payment.payment_means_code, "Zahlungsart"),
    )
    missing = [label for value, label in required if not str(value or "").strip()]
    if missing:
        raise GrainValidationError("Für den Export fehlt: " + ", ".join(missing))
    net = _money(sum((delivery.net_amount for delivery in note.deliveries), Decimal("0")))
    vat = _money(net * rate / Decimal("100"))
    total = _money(net + vat)
    credit = _money(total - note.advance_payment)
    if (
        net != _money(note.net_amount)
        or vat != _money(note.vat_amount)
        or total != _money(note.total_amount)
        or credit != _money(note.credit_amount)
    ):
        raise GrainValidationError("Summen der Getreidegutschrift sind nicht konsistent.")


def _plain_number(value):
    return format(Decimal(value), "f")


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
