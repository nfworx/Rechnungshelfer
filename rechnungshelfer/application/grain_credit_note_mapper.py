"""Erzeugt denselben Getreidegutschrift-Endbeleg aus Import oder Berechnung."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from rechnungshelfer.domain.grain_credit_note import (
    GrainCreditNote,
    GrainCreditNoteBuyer,
    GrainCreditNoteDelivery,
    GrainCreditNoteDetail,
    GrainCreditNotePayment,
    GrainCreditNoteSupplier,
)
from rechnungshelfer.services.format_service import parse_de


_CENT = Decimal("0.01")
_GRAIN_TYPE_LABELS = {
    "wheat": "Weizen",
    "barley": "Gerste (Futtergerste)",
    "malting_barley": "Braugerste",
    "oats": "Hafer",
    "rye": "Roggen",
    "maize": "Mais",
    "rapeseed": "Raps",
}


def grain_credit_note_from_review(review) -> GrainCreditNote:
    return GrainCreditNote(
        credit_note_number=review.credit_note_number.value.strip(),
        credit_note_date=_date(review.credit_note_date.value),
        deliveries=tuple(
            GrainCreditNoteDelivery(
                ticket_number=delivery.ticket_number.value.strip(),
                delivery_date=_date(delivery.delivery_date.value),
                grain_name=delivery.grain_name.value.strip(),
                gross_quantity_kg=parse_de(delivery.gross_quantity_kg.value),
                base_price_per_tonne=parse_de(
                    delivery.base_price_per_tonne.value
                ),
                settlement_quantity_kg=parse_de(
                    delivery.settlement_quantity_kg.value
                ),
                settlement_price_per_tonne=parse_de(
                    delivery.settlement_price_per_tonne.value
                ),
                net_amount=parse_de(delivery.net_amount.value),
                details=tuple(
                    GrainCreditNoteDetail(
                        label=detail.label.value.strip(),
                        analysis_value=parse_de(detail.analysis_value.value),
                        quantity_change_kg=_optional_decimal(
                            detail.quantity_change_kg.value
                        ),
                        price_change_per_tonne=_optional_decimal(
                            detail.price_change_per_tonne.value
                        ),
                        amount_change=_optional_decimal(
                            detail.amount_change.value
                        ),
                    )
                    for detail in delivery.details
                ),
                grain_type_code=delivery.grain_type_code,
            )
            for delivery in review.deliveries
        ),
        vat_rate=parse_de(review.vat_rate.value),
        net_amount=parse_de(review.net_amount.value),
        vat_amount=parse_de(review.vat_amount.value),
        total_amount=parse_de(review.total_amount.value),
        advance_payment=parse_de(review.advance_payment.value),
        credit_amount=parse_de(review.credit_amount.value),
        supplier=GrainCreditNoteSupplier(
            supplier_number=review.supplier_number.value.strip(),
            name=review.supplier_name.value.strip(),
            street=review.supplier_street.value.strip(),
            postcode=review.supplier_postcode.value.strip(),
            city=review.supplier_city.value.strip(),
            country=review.supplier_country.value.strip(),
            phone=review.supplier_phone.value.strip(),
            email=review.supplier_email.value.strip(),
            vat=review.supplier_vat.value.strip(),
            tax_number=review.supplier_tax_number.value.strip(),
            registry_number=review.supplier_registry_number.value.strip(),
            contact_name=review.supplier_contact_name.value.strip(),
            buyer_reference=review.supplier_buyer_reference.value.strip(),
        ),
        payment=GrainCreditNotePayment(
            iban=review.iban.value.strip(),
            bic=review.bic.value.strip(),
            account_holder=review.account_holder.value.strip(),
            payment_means_code="58",
            payment_terms=review.payment_terms.value.strip(),
        ),
        buyer=review.buyer,
        payment_due_date=_optional_date(review.payment_due_date.value),
    )


def grain_credit_note_from_calculation(
    document,
    deliveries,
    settlement,
    vat_rate,
    scheme=None,
) -> GrainCreditNote:
    deliveries_by_id = {delivery.id: delivery for delivery in deliveries}
    result_deliveries = []
    for result in settlement.delivery_results:
        delivery = deliveries_by_id[result.delivery_id]
        measurement_values = {
            measurement.feature_code: measurement.effective_value
            for measurement in delivery.measurements
        }
        feature_labels = {
            feature.code: feature.label
            for feature in (scheme.quality_features if scheme is not None else ())
        }
        details = [
            GrainCreditNoteDetail(
                label=feature_labels.get(
                    measurement.feature_code,
                    measurement.feature_code,
                ),
                analysis_value=measurement.effective_value,
            )
            for measurement in delivery.measurements
        ]
        for deduction in result.quantity_deductions:
            details.append(
                GrainCreditNoteDetail(
                    label=deduction.label,
                    analysis_value=(
                        deduction.measurement_value
                        if deduction.measurement_value is not None
                        else Decimal("0")
                    ),
                    quantity_change_kg=-deduction.deducted_quantity_kg,
                )
            )
        for adjustment in result.monetary_adjustments:
            details.append(
                GrainCreditNoteDetail(
                    label=adjustment.label,
                    analysis_value=(
                        adjustment.measurement_value
                        if adjustment.measurement_value is not None
                        else measurement_values.get(
                            adjustment.measurement_code,
                            Decimal("0"),
                        )
                    ),
                    price_change_per_tonne=adjustment.price_delta_per_tonne,
                    amount_change=(
                        adjustment.amount_delta
                        if adjustment.price_delta_per_tonne is None
                        else None
                    ),
                )
            )
        result_deliveries.append(
            GrainCreditNoteDelivery(
                ticket_number=delivery.ticket_number,
                delivery_date=delivery.delivery_date,
                grain_name=_GRAIN_TYPE_LABELS.get(
                    delivery.grain_type_code,
                    delivery.grain_type_code,
                ),
                grain_type_code=delivery.grain_type_code,
                gross_quantity_kg=result.gross_quantity_kg,
                base_price_per_tonne=result.base_price_per_tonne,
                settlement_quantity_kg=result.settlement_quantity_kg,
                settlement_price_per_tonne=result.settlement_price_per_tonne,
                net_amount=result.net_amount,
                details=tuple(details),
            )
        )
    rate = Decimal(str(vat_rate))
    net = _money(settlement.net_amount)
    vat = _money(net * rate / Decimal("100"))
    total = net + vat
    return GrainCreditNote(
        credit_note_number=document.info.invoice_number.strip(),
        credit_note_date=_date(document.info.invoice_date),
        supplier=_supplier_from_document(document),
        payment=_payment_from_document(document),
        buyer=_buyer_from_document(document),
        payment_due_date=_optional_date(document.info.payment_due_date),
        deliveries=tuple(result_deliveries),
        vat_rate=rate,
        net_amount=net,
        vat_amount=vat,
        total_amount=total,
        advance_payment=Decimal("0"),
        credit_amount=total,
    )


def _date(value: str):
    return datetime.strptime(str(value).strip(), "%d.%m.%Y").date()


def _optional_decimal(value: str):
    return parse_de(value) if str(value or "").strip() else None


def _optional_date(value):
    return _date(value) if str(value or "").strip() else None


def _money(value):
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def _supplier_from_document(document):
    seller = document.seller
    return GrainCreditNoteSupplier(
        supplier_number=seller.supplier_number.strip(),
        name=seller.name.strip(),
        street=seller.street.strip(),
        postcode=seller.postcode.strip(),
        city=seller.city.strip(),
        country=seller.country.strip(),
        phone=seller.phone.strip(),
        email=seller.email.strip(),
        vat=seller.vat.strip(),
        tax_number=seller.tax_number.strip(),
        registry_number=seller.registry_number.strip(),
        contact_name=seller.contact_name.strip(),
        buyer_reference=seller.buyer_reference.strip(),
    )


def _payment_from_document(document):
    payment = document.payment
    return GrainCreditNotePayment(
        iban=payment.iban.strip(),
        bic=payment.bic.strip(),
        account_holder=payment.account_holder.strip(),
        payment_means_code=payment.payment_means_code.strip(),
        payment_terms=payment.payment_terms.strip(),
    )


def _buyer_from_document(document):
    buyer = document.buyer
    return GrainCreditNoteBuyer(
        name=buyer.name.strip(),
        street=buyer.street.strip(),
        postcode=buyer.postcode.strip(),
        city=buyer.city.strip(),
        country=buyer.country.strip(),
        leitweg_id=buyer.leitweg_id.strip(),
        email=buyer.email.strip(),
        contact_name=buyer.contact_name.strip(),
        customer_number=buyer.customer_number.strip(),
        phone=buyer.phone.strip(),
        vat=buyer.vat.strip(),
        tax_number=buyer.tax_number.strip(),
        registry_number=buyer.registry_number.strip(),
    )


def grain_credit_note_creation_issues(document, deliveries, result, vat_value):
    """Liefert konkrete, GUI-unabhaengige Gruende fuer eine gesperrte Erstellung."""

    issues = []
    if not document.info.invoice_number.strip():
        issues.append("Gutschriftnummer fehlt.")
    try:
        _date(document.info.invoice_date)
    except ValueError:
        issues.append("Ausstellungsdatum fehlt oder ist ungueltig.")

    required_fields = (
        (document.seller, "supplier_number", "Lieferantennummer"),
        (document.seller, "name", "Lieferantenname"),
        (document.seller, "street", "Strasse"),
        (document.seller, "postcode", "PLZ"),
        (document.seller, "city", "Ort"),
        (document.seller, "country", "Land"),
        (document.seller, "email", "E-Mail"),
        (document.payment, "iban", "IBAN"),
        (document.payment, "bic", "BIC"),
        (document.payment, "account_holder", "Kontoinhaber"),
        (document.payment, "payment_terms", "Zahlungsbedingungen"),
    )
    for model, field, label in required_fields:
        if not str(getattr(model, field, "") or "").strip():
            issues.append(f"{label} fehlt.")

    if not deliveries:
        issues.append("Mindestens eine Lieferung fehlt.")
    elif result is None or len(result.delivery_results) != len(deliveries):
        issues.append("Die Lieferungen sind noch nicht erfolgreich berechnet.")

    raw_vat = str(vat_value or "").strip().replace("%", "").strip()
    try:
        if not raw_vat or "ausw" in raw_vat.casefold() or "—" in raw_vat:
            raise ValueError
        parse_de(raw_vat)
    except ValueError:
        issues.append("Steuersatz fehlt oder ist ungueltig.")
    return tuple(issues)


__all__ = [
    "grain_credit_note_creation_issues",
    "grain_credit_note_from_calculation",
    "grain_credit_note_from_review",
]
