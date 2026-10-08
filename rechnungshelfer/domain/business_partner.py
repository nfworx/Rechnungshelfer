"""Gemeinsame Fachbegriffe und Validierung fuer Geschaeftspartner."""

from __future__ import annotations

import re
from enum import Enum


class BusinessPartnerRole(str, Enum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"


_PARTNER_NUMBER_PATTERN = re.compile(r"[0-9]+")


def normalize_partner_number(value: object) -> str:
    """Liefert eine rein numerische, anzeigbare Geschaeftspartnernummer."""

    number = str(value or "").strip()
    if not number:
        raise ValueError("Geschaeftspartnernummer fehlt.")
    if _PARTNER_NUMBER_PATTERN.fullmatch(number) is None:
        raise ValueError("Geschaeftspartnernummer darf nur aus Ziffern bestehen.")
    return number

