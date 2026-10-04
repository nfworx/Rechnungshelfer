# input_validation_service.py
from datetime import datetime
import re
from rechnungshelfer.domain.models import Invoice

class InputValidationError(Exception):
    pass


def is_valid_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", str(value or "").strip()))


def is_valid_phone(value: str) -> bool:
    return len(re.findall(r"\d", str(value or ""))) >= 3


def is_valid_vat_id(value: str, country: str = "") -> bool:
    normalized = re.sub(r"[\s.-]", "", str(value or "").upper())
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{2,13}", normalized):
        return False
    expected_prefix = str(country or "").strip().upper()
    if expected_prefix == "GR":
        expected_prefix = "EL"
    return not expected_prefix or normalized.startswith(expected_prefix)


def is_valid_bic(value: str) -> bool:
    normalized = re.sub(r"\s", "", str(value or "").upper())
    return bool(re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?", normalized))


def is_valid_iban(value: str) -> bool:
    normalized = re.sub(r"\s", "", str(value or "").upper())
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", normalized):
        return False
    rearranged = normalized[4:] + normalized[:4]
    numeric = "".join(
        str(ord(char) - 55) if char.isalpha() else char
        for char in rearranged
    )
    return int(numeric) % 97 == 1

def normalize_date_de(value: str, field_name="Datum", required=True) -> str:
    value = str(value or "").strip()

    if not value:
        if required:
            raise InputValidationError(f"{field_name} fehlt")
        return ""

    formats = [
        "%d.%m.%Y",
        "%d.%m.%y",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%d.%m.%Y")
        except ValueError:
            continue

    raise InputValidationError(f"{field_name} ist ungültig: {value}")

def normalize_invoice_input(invoice: Invoice) -> Invoice:
    invoice.set_document_type(invoice.document_type)
    invoice.info.invoice_date = normalize_date_de(
        invoice.info.invoice_date,
        "Ausstellungsdatum" if invoice.is_self_billed else "Rechnungsdatum"
    )

    invoice.info.payment_due_date = normalize_date_de(
        invoice.info.payment_due_date,
        "Auszahlungsdatum" if invoice.is_self_billed else "Zahlungsziel"
    )

    invoice.info.delivery_date = normalize_date_de(
        invoice.info.delivery_date,
        "Lieferdatum",
        required=False
    )

    return invoice
