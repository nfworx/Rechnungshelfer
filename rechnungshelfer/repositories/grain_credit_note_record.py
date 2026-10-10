"""Stabile JSON-Abbildung strukturierter Getreidegutschriften."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from rechnungshelfer.domain.grain_credit_note import (
    GrainCreditNote,
    GrainCreditNoteBuyer,
    GrainCreditNoteDelivery,
    GrainCreditNoteDetail,
    GrainCreditNotePayment,
    GrainCreditNoteSupplier,
    GrainRuleCheck,
    GrainRuleDeviation,
    GrainSchemeReference,
)


RECORD_VERSION = 2


def grain_credit_note_to_data(note: GrainCreditNote) -> dict:
    return {
        "record_version": RECORD_VERSION,
        "origin": note.origin,
        "credit_note_number": note.credit_note_number,
        "credit_note_date": note.credit_note_date.isoformat(),
        "payment_due_date": (
            note.payment_due_date.isoformat() if note.payment_due_date else None
        ),
        "supplier": _text_fields(note.supplier),
        "payment": _text_fields(note.payment),
        "buyer": _text_fields(note.buyer),
        "deliveries": [
            {
                "ticket_number": delivery.ticket_number,
                "delivery_date": delivery.delivery_date.isoformat(),
                "grain_name": delivery.grain_name,
                "grain_type_code": delivery.grain_type_code,
                "gross_quantity_kg": str(delivery.gross_quantity_kg),
                "base_price_per_tonne": str(delivery.base_price_per_tonne),
                "settlement_quantity_kg": str(delivery.settlement_quantity_kg),
                "settlement_price_per_tonne": str(
                    delivery.settlement_price_per_tonne
                ),
                "net_amount": str(delivery.net_amount),
                "rule_check": _rule_check_to_data(delivery.rule_check),
                "details": [
                    {
                        "label": detail.label,
                        "analysis_value": str(detail.analysis_value),
                        "quantity_change_kg": _optional_decimal(
                            detail.quantity_change_kg
                        ),
                        "price_change_per_tonne": _optional_decimal(
                            detail.price_change_per_tonne
                        ),
                        "amount_change": _optional_decimal(detail.amount_change),
                        "rule_deviation": _deviation_to_data(
                            detail.rule_deviation
                        ),
                    }
                    for detail in delivery.details
                ],
            }
            for delivery in note.deliveries
        ],
        "vat_rate": str(note.vat_rate),
        "net_amount": str(note.net_amount),
        "vat_amount": str(note.vat_amount),
        "total_amount": str(note.total_amount),
        "advance_payment": str(note.advance_payment),
        "credit_amount": str(note.credit_amount),
    }


def grain_credit_note_from_data(data: dict) -> GrainCreditNote:
    version = data.get("record_version")
    if version not in {1, RECORD_VERSION}:
        raise ValueError(
            "Die gespeicherte Getreidegutschrift verwendet eine "
            f"nicht unterstützte Datenversion: {version}."
        )
    supplier = data.get("supplier") or {}
    payment = data.get("payment") or {}
    buyer = data.get("buyer") or {}
    return GrainCreditNote(
        credit_note_number=str(data.get("credit_note_number") or ""),
        credit_note_date=_date(data.get("credit_note_date")),
        payment_due_date=_optional_date(data.get("payment_due_date")),
        supplier=GrainCreditNoteSupplier(
            **_known_fields(GrainCreditNoteSupplier, supplier)
        ),
        payment=GrainCreditNotePayment(
            **_known_fields(GrainCreditNotePayment, payment)
        ),
        buyer=GrainCreditNoteBuyer(
            **_known_fields(GrainCreditNoteBuyer, buyer)
        ),
        deliveries=tuple(
            GrainCreditNoteDelivery(
                ticket_number=str(item.get("ticket_number") or ""),
                delivery_date=_date(item.get("delivery_date")),
                grain_name=str(item.get("grain_name") or ""),
                grain_type_code=str(item.get("grain_type_code") or ""),
                gross_quantity_kg=Decimal(str(item.get("gross_quantity_kg"))),
                base_price_per_tonne=Decimal(
                    str(item.get("base_price_per_tonne"))
                ),
                settlement_quantity_kg=Decimal(
                    str(item.get("settlement_quantity_kg"))
                ),
                settlement_price_per_tonne=Decimal(
                    str(item.get("settlement_price_per_tonne"))
                ),
                net_amount=Decimal(str(item.get("net_amount"))),
                rule_check=_rule_check_from_data(item.get("rule_check")),
                details=tuple(
                    GrainCreditNoteDetail(
                        label=str(detail.get("label") or ""),
                        analysis_value=Decimal(
                            str(detail.get("analysis_value"))
                        ),
                        quantity_change_kg=_decimal_or_none(
                            detail.get("quantity_change_kg")
                        ),
                        price_change_per_tonne=_decimal_or_none(
                            detail.get("price_change_per_tonne")
                        ),
                        amount_change=_decimal_or_none(
                            detail.get("amount_change")
                        ),
                        rule_deviation=_deviation_from_data(
                            detail.get("rule_deviation")
                        ),
                    )
                    for detail in (item.get("details") or [])
                ),
            )
            for item in (data.get("deliveries") or [])
        ),
        vat_rate=Decimal(str(data.get("vat_rate"))),
        net_amount=Decimal(str(data.get("net_amount"))),
        vat_amount=Decimal(str(data.get("vat_amount"))),
        total_amount=Decimal(str(data.get("total_amount"))),
        advance_payment=Decimal(str(data.get("advance_payment"))),
        credit_amount=Decimal(str(data.get("credit_amount"))),
        origin=(
            str(data.get("origin") or "unknown")
            if version == RECORD_VERSION
            else "unknown"
        ),
    )


def _rule_check_to_data(check: GrainRuleCheck) -> dict:
    scheme = check.scheme
    return {
        "status": check.status,
        "note": check.note,
        "scheme": (
            {
                "version_id": scheme.version_id,
                "grain_type_code": scheme.grain_type_code,
                "harvest_year": scheme.harvest_year,
                "revision": scheme.revision,
                "name": scheme.name,
            }
            if scheme is not None
            else None
        ),
    }


def _rule_check_from_data(data) -> GrainRuleCheck:
    if not isinstance(data, dict):
        return GrainRuleCheck()
    scheme_data = data.get("scheme")
    scheme = None
    if isinstance(scheme_data, dict):
        scheme = GrainSchemeReference(
            version_id=int(scheme_data.get("version_id")),
            grain_type_code=str(scheme_data.get("grain_type_code") or ""),
            harvest_year=int(scheme_data.get("harvest_year")),
            revision=int(scheme_data.get("revision")),
            name=str(scheme_data.get("name") or ""),
        )
    return GrainRuleCheck(
        status=str(data.get("status") or "not_requested"),
        scheme=scheme,
        note=str(data.get("note") or ""),
    )


def _deviation_to_data(deviation: GrainRuleDeviation | None):
    if deviation is None:
        return None
    return {
        field: _optional_decimal(getattr(deviation, field))
        for field in deviation.__dataclass_fields__
    }


def _deviation_from_data(data):
    if not isinstance(data, dict):
        return None
    return GrainRuleDeviation(
        **{
            field: _decimal_or_none(data.get(field))
            for field in GrainRuleDeviation.__dataclass_fields__
        }
    )


def _text_fields(value) -> dict[str, str]:
    return {
        field: str(getattr(value, field) or "")
        for field in value.__dataclass_fields__
    }


def _known_fields(model_type, data: dict) -> dict[str, str]:
    return {
        field: str(data.get(field) or "")
        for field in model_type.__dataclass_fields__
        if field in data
    }


def _optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _decimal_or_none(value) -> Decimal | None:
    return None if value is None or value == "" else Decimal(str(value))


def _date(value) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("Gespeichertes Belegdatum ist ungültig.") from exc


def _optional_date(value) -> date | None:
    return None if value in (None, "") else _date(value)


__all__ = ["grain_credit_note_from_data", "grain_credit_note_to_data"]
