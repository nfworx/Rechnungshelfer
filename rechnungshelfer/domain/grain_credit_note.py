"""Strukturierte Getreidegutschrift als fachlicher Endbeleg."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .grain_models import GrainValidationError, decimal_value


@dataclass(frozen=True)
class GrainCreditNoteDetail:
    label: str
    analysis_value: Decimal
    quantity_change_kg: Decimal | None = None
    price_change_per_tonne: Decimal | None = None
    amount_change: Decimal | None = None

    def __post_init__(self):
        if not self.label.strip():
            raise GrainValidationError("Analysezeile benötigt eine Bezeichnung.")
        object.__setattr__(self, "analysis_value", decimal_value(self.analysis_value))
        for name in (
            "quantity_change_kg",
            "price_change_per_tonne",
            "amount_change",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, decimal_value(value))


@dataclass(frozen=True)
class GrainCreditNoteDelivery:
    ticket_number: str
    delivery_date: date
    grain_name: str
    gross_quantity_kg: Decimal
    base_price_per_tonne: Decimal
    settlement_quantity_kg: Decimal
    settlement_price_per_tonne: Decimal
    net_amount: Decimal
    details: tuple[GrainCreditNoteDetail, ...] = ()
    grain_type_code: str = ""

    def __post_init__(self):
        for name, label in (
            ("ticket_number", "Lieferscheinnummer"),
            ("grain_name", "Getreidebezeichnung"),
        ):
            if not str(getattr(self, name)).strip():
                raise GrainValidationError(f"{label} fehlt.")
        if not isinstance(self.delivery_date, date):
            raise GrainValidationError("Lieferdatum ist ungültig.")
        for name in (
            "gross_quantity_kg",
            "base_price_per_tonne",
            "settlement_quantity_kg",
            "settlement_price_per_tonne",
            "net_amount",
        ):
            object.__setattr__(self, name, decimal_value(getattr(self, name)))
        object.__setattr__(self, "details", tuple(self.details))


@dataclass(frozen=True)
class GrainCreditNoteSupplier:
    supplier_number: str = ""
    name: str = ""
    street: str = ""
    postcode: str = ""
    city: str = ""
    country: str = "DE"
    phone: str = ""
    email: str = ""
    vat: str = ""
    tax_number: str = ""
    registry_number: str = ""
    contact_name: str = ""
    buyer_reference: str = ""


@dataclass(frozen=True)
class GrainCreditNotePayment:
    iban: str = ""
    bic: str = ""
    account_holder: str = ""
    payment_means_code: str = "58"
    payment_terms: str = ""


@dataclass(frozen=True)
class GrainCreditNoteBuyer:
    name: str = ""
    street: str = ""
    postcode: str = ""
    city: str = ""
    country: str = "DE"
    leitweg_id: str = ""
    email: str = ""
    contact_name: str = ""
    customer_number: str = ""
    phone: str = ""
    vat: str = ""
    tax_number: str = ""
    registry_number: str = ""


@dataclass(frozen=True)
class GrainCreditNote:
    credit_note_number: str
    credit_note_date: date
    deliveries: tuple[GrainCreditNoteDelivery, ...]
    vat_rate: Decimal
    net_amount: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    advance_payment: Decimal
    credit_amount: Decimal
    supplier: GrainCreditNoteSupplier = GrainCreditNoteSupplier()
    payment: GrainCreditNotePayment = GrainCreditNotePayment()
    buyer: GrainCreditNoteBuyer = GrainCreditNoteBuyer()

    @property
    def supplier_number(self) -> str:
        """Kompatibler Kurzweg fuer bestehende Anzeige- und Testlogik."""

        return self.supplier.supplier_number

    def __post_init__(self):
        if not self.credit_note_number.strip():
            raise GrainValidationError("Gutschriftnummer fehlt.")
        if not isinstance(self.credit_note_date, date):
            raise GrainValidationError("Ausstellungsdatum ist ungültig.")
        object.__setattr__(self, "deliveries", tuple(self.deliveries))
        if not self.deliveries:
            raise GrainValidationError("Mindestens eine Lieferung fehlt.")
        for name in (
            "vat_rate",
            "net_amount",
            "vat_amount",
            "total_amount",
            "advance_payment",
            "credit_amount",
        ):
            object.__setattr__(self, name, decimal_value(getattr(self, name)))


__all__ = [
    "GrainCreditNote",
    "GrainCreditNoteDelivery",
    "GrainCreditNoteDetail",
    "GrainCreditNoteBuyer",
    "GrainCreditNotePayment",
    "GrainCreditNoteSupplier",
]
