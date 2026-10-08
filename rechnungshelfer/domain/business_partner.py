"""Gemeinsame Fachbegriffe und Validierung fuer Geschaeftspartner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from rechnungshelfer.domain.models import Buyer, Payment, Seller


COMMON_PARTY_FIELDS = (
    "name",
    "street",
    "postcode",
    "city",
    "country",
    "phone",
    "email",
    "vat",
    "tax_number",
    "registry_number",
    "contact_name",
)
CUSTOMER_ROLE_FIELDS = ("leitweg_id", "use_invoice_address_as_delivery")
SUPPLIER_ROLE_FIELDS = ("buyer_reference",)


class BusinessPartnerRole(str, Enum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"


@dataclass
class BusinessPartnerProfile:
    """Bearbeitbare Gesamtsicht auf Stammdaten und Rollen eines Partners."""

    buyer: Buyer
    seller: Seller
    payment: Payment
    roles: frozenset[BusinessPartnerRole]
    partner_id: int | None = None

    @property
    def partner_number(self) -> str:
        return self.buyer.customer_number or self.seller.supplier_number

    @property
    def name(self) -> str:
        return self.buyer.name or self.seller.name

    def has_role(self, role: BusinessPartnerRole) -> bool:
        return role in self.roles


_PARTNER_NUMBER_PATTERN = re.compile(r"[0-9]+")


def normalize_partner_number(value: object) -> str:
    """Liefert eine rein numerische, anzeigbare Geschaeftspartnernummer."""

    number = str(value or "").strip()
    if not number:
        raise ValueError("Geschaeftspartnernummer fehlt.")
    if _PARTNER_NUMBER_PATTERN.fullmatch(number) is None:
        raise ValueError("Geschaeftspartnernummer darf nur aus Ziffern bestehen.")
    return number
