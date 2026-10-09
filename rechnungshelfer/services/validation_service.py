# rechnungshelfer/services/validation_service.py

import sys
from functools import lru_cache
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from typing import Protocol
from lxml import etree
from .input_validation_service import (
    is_valid_bic,
    is_valid_email,
    is_valid_iban,
    is_valid_phone,
    is_valid_vat_id,
)

from rechnungshelfer.domain.models import Invoice


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


BASE_DIR = get_base_dir()
XSD_PATH = (
    BASE_DIR
    / "external"
    / "kosit"
    / "xrechnung"
    / "resources"
    / "ubl"
    / "2.1"
    / "xsd"
    / "maindoc"
    / "UBL-Invoice-2.1.xsd"
)


def round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_html: str = ""

    def add_error(self, message: str):
        self.valid = False
        self.errors.append(message)

    def add_warning(self, message: str):
        self.warnings.append(message)


class ExternalValidationResult(Protocol):
    valid: bool
    errors: list[str]
    report_html: str


class ExternalInvoiceValidator(Protocol):
    def validate(self, xml_bytes: bytes) -> ExternalValidationResult: ...


def is_required_field(invoice: Invoice, section: str, attr: str, item_pos=None) -> bool:
    """Prueft, ob ein Modellattribut fuer den aktuellen Beleg erforderlich ist."""
    if section == "Item":
        if item_pos is None:
            raise ValueError("Für 'Item' muss item_pos angegeben werden")
        item = next((item for item in invoice.items if item.pos == item_pos), None)
        return bool(item and attr in item.required_fields)

    objects = {
        "Seller": invoice.seller,
        "Buyer": invoice.buyer,
        "Delivery": invoice.delivery,
        "Invoice": invoice.info,
        "Payment": invoice.payment,
    }
    obj = objects.get(section)
    return bool(obj and attr in getattr(obj, "required_fields", []))


def get_missing_required_fields(invoice: Invoice, for_xml: bool = True) -> list[tuple]:
    """Liefert fehlende oder ungueltige Felder fuer PDF- oder XML-Export."""
    missing = []

    def check(section_name, obj, fields):
        for field_name in fields:
            value = getattr(obj, field_name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append((section_name, obj, field_name))

    if invoice.is_self_billed:
        seller_required = ["name", "street", "postcode", "city", "country", "email"]
        buyer_required = ["name", "street", "postcode", "city", "country"]
        if for_xml:
            buyer_required.extend(["email", "leitweg_id"])
        payment_required = ["iban", "bic", "account_holder", "payment_means_code"]

        check("Lieferant", invoice.seller, seller_required)
        check("Eigener Betrieb", invoice.buyer, buyer_required)
        check("Auszahlung", invoice.payment, payment_required)

        if not (invoice.seller.vat or invoice.seller.tax_number):
            missing.append(("Lieferant", invoice.seller, "vat_or_tax_number"))

        sections = [("Invoice", invoice.info)]
    else:
        sections = [
            ("Seller", invoice.seller),
            ("Buyer", invoice.buyer),
            ("Invoice", invoice.info),
            ("Payment", invoice.payment),
        ]

    if not invoice.buyer.use_invoice_address_as_delivery:
        sections.append(("Delivery", invoice.delivery))

    for section_name, obj in sections:
        fields = list(getattr(obj, "required_fields", []))
        if for_xml and obj is invoice.buyer and "leitweg_id" not in fields:
            fields.append("leitweg_id")
        check(section_name, obj, fields)

    for item in invoice.items:
        section_name = f"Position {item.pos or 'unbekannt'}"
        check(section_name, item, getattr(item, "required_fields", []))
        if item.qty is None or item.qty <= 0:
            missing.append((section_name, item, "qty"))

    if for_xml:
        _add_xml_format_issues(invoice, missing)

    return missing


def _add_xml_format_issues(invoice: Invoice, missing: list[tuple]) -> None:
    parties = [
        ("Lieferant" if invoice.is_self_billed else "Verkäufer", invoice.seller),
        ("Eigener Betrieb" if invoice.is_self_billed else "Kunde", invoice.buyer),
    ]
    for section, party in parties:
        if party.email and not is_valid_email(party.email):
            missing.append((section, party, "email_invalid"))
        if party.vat and not is_valid_vat_id(party.vat, party.country):
            missing.append((section, party, "vat_invalid"))

    seller_section = "Lieferant" if invoice.is_self_billed else "Verkäufer"
    if not invoice.seller.phone:
        missing.append((seller_section, invoice.seller, "phone"))
    elif not is_valid_phone(invoice.seller.phone):
        missing.append((seller_section, invoice.seller, "phone_invalid"))

    payment_section = "Auszahlung" if invoice.is_self_billed else "Zahlung"
    if invoice.payment.iban and not is_valid_iban(invoice.payment.iban):
        missing.append((payment_section, invoice.payment, "iban_invalid"))
    if invoice.payment.bic and not is_valid_bic(invoice.payment.bic):
        missing.append((payment_section, invoice.payment, "bic_invalid"))

    if not any(
        (
            invoice.seller.supplier_number,
            invoice.seller.registry_number,
            invoice.seller.vat,
        )
    ):
        missing.append((seller_section, invoice.seller, "seller_identifier"))


def format_missing_fields(missing: list[tuple], export_name: str) -> str:
    labels = {
        "vat_or_tax_number": "Steuernummer oder USt-ID",
        "leitweg_id": "Käuferreferenz (BT-10)",
        "email_invalid": "E-Mail-Adresse ist ungültig",
        "phone_invalid": "Telefonnummer muss mindestens drei Ziffern enthalten",
        "vat_invalid": "USt-ID benötigt ein Länderpräfix, z. B. DE123456789",
        "iban_invalid": "IBAN ist ungültig",
        "bic_invalid": "BIC ist ungültig",
        "seller_identifier": "Lieferantennummer, Handelsregisternummer oder USt-ID",
    }
    lines = []
    for section, obj, field_name in missing:
        label = labels.get(field_name)
        if label is None:
            label = obj.get_label(field_name) if hasattr(obj, "get_label") else field_name
        line = f"- {section}: {label}"
        if line not in lines:
            lines.append(line)
    return (
        f"{export_name}-Export nicht möglich. Angaben fehlen oder sind ungültig:\n\n"
        + "\n".join(lines)
    )


@lru_cache(maxsize=4)
def _load_xsd_schema(xsd_path: str, modified_ns: int) -> etree.XMLSchema:
    del modified_ns  # Bestandteil des Cache-Schlüssels, damit Schema-Updates neu geladen werden.
    schema_doc = etree.parse(xsd_path)
    return etree.XMLSchema(schema_doc)


def validate_xsd(xml_bytes: bytes, xsd_path: Path = XSD_PATH) -> ValidationResult:
    result = ValidationResult()

    try:
        xml_parser = etree.XMLParser(recover=False, remove_blank_text=True)
        xml_doc = etree.fromstring(xml_bytes, xml_parser)
    except Exception as e:
        result.add_error(f"XML konnte nicht geparst werden: {e}")
        return result

    try:
        resolved_path = xsd_path.resolve()
        schema = _load_xsd_schema(
            str(resolved_path),
            resolved_path.stat().st_mtime_ns,
        )
    except Exception as e:
        result.add_error(f"Fehler beim Laden des XSD: {e}")
        return result

    if not schema.validate(xml_doc):
        for err in schema.error_log:
            result.add_error(
                f"XSD Fehler - Zeile {err.line}, Spalte {err.column}: {err.message}"
            )

    return result


def validate_totals(invoice: Invoice) -> ValidationResult:
    result = ValidationResult()

    net_calc = round2(sum(item.net for item in invoice.items))

    xml_net = round2(invoice.monetarytotal.line_extension_amount)

    if net_calc != xml_net:
        result.add_warning(
            f"Nettosumme inkonsistent: berechnet={net_calc}, XML={xml_net}"
        )

    tax_by_group_calc: dict[tuple[Decimal, str], Decimal] = {}

    for item in invoice.items:
        tax = item.net * item.vat / Decimal("100")
        group = (item.vat, item.tax_category)
        tax_by_group_calc[group] = tax_by_group_calc.get(group, Decimal("0.00")) + tax

    for tax in getattr(invoice, "taxtotal", []):
        group = (tax.percent, tax.tax_category)
        expected = round2(tax_by_group_calc.get(group, Decimal("0.00")))
        actual = round2(tax.amount)

        if actual != expected:
            result.add_warning(
                f"Steuer falsch für {tax.percent}%: XML={actual}, berechnet={expected}"
            )

    tax_total_calc = round2(sum(t.amount for t in getattr(invoice, "taxtotal", [])))
    gross_calc = round2(net_calc + tax_total_calc)

    xml_gross = round2(invoice.monetarytotal.tax_inclusive_amount)
    prepaid_amount = round2(invoice.monetarytotal.prepaid_amount)
    xml_payable = round2(invoice.monetarytotal.payable_amount)

    if gross_calc != xml_gross:
        result.add_warning(
            f"Bruttobetrag inkonsistent: berechnet={gross_calc}, XML={xml_gross}"
        )

    payable_calc = round2(gross_calc - prepaid_amount)
    if payable_calc != xml_payable:
        result.add_warning(
            f"Zahlbetrag inkonsistent: berechnet={payable_calc}, XML={xml_payable}"
        )

    return result


def validate_document(invoice: Invoice) -> ValidationResult:
    result = ValidationResult()
    expected_code = "389" if invoice.is_self_billed else "380"

    if str(invoice.info.invoice_type_code) != expected_code:
        result.add_error(
            f"Belegtyp und InvoiceTypeCode widersprechen sich: erwartet {expected_code}."
        )

    if invoice.is_self_billed:
        if not (invoice.seller.vat or invoice.seller.tax_number):
            result.add_error(
                "Für den Lieferanten ist eine Steuernummer oder USt-ID erforderlich."
            )
        if not invoice.payment.iban:
            result.add_error("Für die Auszahlung fehlt die IBAN des Lieferanten.")

    for item in invoice.items:
        if item.qty <= 0 or item.net < 0 or item.price < 0:
            result.add_error(
                f"Position {item.pos}: Mengen und Beträge müssen positiv sein."
            )

        if item.vat == 0 and item.tax_category != "Z":
            result.add_error(
                f"Position {item.pos}: Für 0 % MwSt muss die Steuerkategorie Z verwendet werden."
            )

    return result


def validate_invoice(
    xml_bytes: bytes,
    invoice: Invoice,
    use_kosit: bool = False,
    external_validator: ExternalInvoiceValidator | None = None,
) -> ValidationResult:
    final = ValidationResult()

    xsd_result = validate_xsd(xml_bytes)
    totals_result = validate_totals(invoice)
    document_result = validate_document(invoice)

    final.errors.extend(xsd_result.errors)
    final.warnings.extend(xsd_result.warnings)
    final.warnings.extend(totals_result.warnings)
    final.errors.extend(document_result.errors)
    final.warnings.extend(document_result.warnings)

    if xsd_result.errors or document_result.errors:
        final.valid = False

    if use_kosit or external_validator is not None:
        if external_validator is None:
            from .kosit_validation_service import KositValidator

            external_validator = KositValidator()
        kosit_result = external_validator.validate(xml_bytes)

        final.report_html = kosit_result.report_html

        if not kosit_result.valid:
            final.valid = False
            final.errors.extend(kosit_result.errors)

    return final

