# services/validation_service.py

import sys
from functools import lru_cache
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from lxml import etree
from services.kosit_validation_service import validate_with_kosit

from models import Invoice


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
XSD_DIR = BASE_DIR / "external" / "ubl"
XSD_PATH = XSD_DIR / "UBL-Invoice-2.1.xsd"


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


class LocalResolver(etree.Resolver):
    def resolve(self, url, pubid, context):
        local_path = XSD_DIR / url

        if not local_path.exists():
            local_path = XSD_DIR / Path(url).name

        if local_path.exists():
            return self.resolve_filename(str(local_path), context)

        return None
    
class ExportValidationError(Exception):
    def __init__(
        self,
        message: str,
        details: str = "",
        report_html: str = "",
    ):
        super().__init__(message)
        self.details = details
        self.report_html = report_html


@lru_cache(maxsize=4)
def _load_xsd_schema(xsd_path: str, modified_ns: int) -> etree.XMLSchema:
    del modified_ns  # Bestandteil des Cache-Schlüssels, damit Schema-Updates neu geladen werden.
    xsd_parser = etree.XMLParser()
    xsd_parser.resolvers.add(LocalResolver())
    schema_doc = etree.parse(xsd_path, xsd_parser)
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

    xml_payable = round2(invoice.monetarytotal.payable_amount)

    if gross_calc != xml_payable:
        result.add_warning(
            f"Bruttobetrag inkonsistent: berechnet={gross_calc}, XML={xml_payable}"
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

    if use_kosit:
        kosit_result = validate_with_kosit(xml_bytes,open_report=False)

        final.report_html = kosit_result.report_html

        if not kosit_result.valid:
            final.valid = False
            final.errors.extend(kosit_result.errors)

    return final

