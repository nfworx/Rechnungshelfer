"""Konservative Zuordnung extrahierter PDF-Texte zum bestehenden Invoice-Modell."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from rechnungshelfer.domain.models import DocumentType, Invoice
from .pdf_import_service import PdfImportResult


@dataclass(frozen=True)
class DetectedInvoiceField:
    path: str
    value: str
    confidence: float
    page_number: int
    source: str


@dataclass(frozen=True)
class PdfInvoiceDraft:
    document_type: DocumentType
    fields: tuple[DetectedInvoiceField, ...]
    warnings: tuple[str, ...] = ()

    def get(self, path: str) -> DetectedInvoiceField | None:
        return next((field for field in self.fields if field.path == path), None)


@dataclass(frozen=True)
class PdfInvoiceImport:
    extraction: PdfImportResult
    draft: PdfInvoiceDraft
    invoice: Invoice


class PdfInvoiceParser:
    """Uebernimmt nur eindeutig beschriftete Werte; keine Layout-Vermutungen."""

    _LABELED_PATTERNS = (
        (
            "info.invoice_number",
            re.compile(
                r"^\s*(?:Rechnungs(?:nummer|nr\.?|\s*Nr\.?)|Belegnummer|"
                r"Gutschrifts(?:nummer|nr\.?))\s*[:#]?\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9./_-]{1,49})\s*$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.98,
            None,
        ),
        (
            "info.invoice_date",
            re.compile(
                r"^\s*(?:Rechnungsdatum|Ausstellungsdatum|Belegdatum|"
                r"Gutschriftsdatum)\s*:?\s*(?P<value>\d{1,2}[.]\d{1,2}[.]\d{2,4}|"
                r"\d{4}-\d{1,2}-\d{1,2})\s*$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.98,
            "date",
        ),
        (
            "info.payment_due_date",
            re.compile(
                r"^\s*(?:Faellig(?:keitsdatum)?|Fällig(?:keitsdatum)?|Zahlbar bis|"
                r"Zahlungsziel)\s*:?\s*(?P<value>\d{1,2}[.]\d{1,2}[.]\d{2,4}|"
                r"\d{4}-\d{1,2}-\d{1,2})\s*$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.95,
            "date",
        ),
        (
            "info.delivery_date",
            re.compile(
                r"^\s*(?:Lieferdatum|Leistungsdatum)\s*:?\s*"
                r"(?P<value>\d{1,2}[.]\d{1,2}[.]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})\s*$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.95,
            "date",
        ),
        (
            "buyer.name",
            re.compile(
                r"^\s*(?:Kundenname|Rechnungsempfaenger|Rechnungsempfänger|Kaeufer|Käufer)"
                r"\s*:\s*(?P<value>[^\r\n]{2,100})$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.90,
            "text",
        ),
        (
            "buyer.customer_number",
            re.compile(
                r"^\s*(?:Kundennummer|Kunden-Nr\.?)\s*:\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9./_-]{1,39})\s*$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.95,
            None,
        ),
        (
            "seller.name",
            re.compile(
                r"^\s*(?:Lieferant|Verkaeufer|Verkäufer|Rechnungssteller)"
                r"\s*:\s*(?P<value>[^\r\n]{2,100})$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.90,
            "text",
        ),
        (
            "seller.supplier_number",
            re.compile(
                r"^\s*(?:Lieferantennummer|Lieferanten-Nr\.?)\s*:\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9./_-]{1,39})\s*$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.95,
            None,
        ),
        (
            "payment.bic",
            re.compile(
                r"^\s*(?:BIC|SWIFT)\s*:?\s*"
                r"(?P<value>[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\s*$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.98,
            "upper",
        ),
        (
            "payment.payment_terms",
            re.compile(
                r"^\s*(?:Zahlungsbedingungen|Zahlungsbedingung)\s*:\s*"
                r"(?P<value>[^\r\n]{3,200})$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.90,
            "text",
        ),
        (
            "info.delivery_note",
            re.compile(
                r"^\s*(?:Lieferschein|Lieferscheinnummer|Lieferschein-Nr\.?)\s*:\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9./_-]{1,49})\s*$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.92,
            None,
        ),
    )
    _IBAN_PATTERN = re.compile(
        r"(?:IBAN\s*:?\s*)?(?P<value>[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30})\b",
        re.IGNORECASE,
    )

    def parse(self, extraction: PdfImportResult) -> PdfInvoiceDraft:
        document_type = self._detect_document_type(extraction.full_text)
        detected = {}

        for page in extraction.pages:
            for path, pattern, confidence, normalizer in self._LABELED_PATTERNS:
                match = pattern.search(page.text)
                if not match:
                    continue
                value = self._normalize(match.group("value"), normalizer)
                if value:
                    detected.setdefault(
                        path,
                        DetectedInvoiceField(
                            path=path,
                            value=value,
                            confidence=confidence,
                            page_number=page.page_number,
                            source=match.group(0).strip(),
                        ),
                    )

            iban_match = self._IBAN_PATTERN.search(page.text)
            if iban_match:
                iban = re.sub(r"\s+", "", iban_match.group("value")).upper()
                if self._valid_iban(iban):
                    detected.setdefault(
                        "payment.iban",
                        DetectedInvoiceField(
                            path="payment.iban",
                            value=iban,
                            confidence=0.98,
                            page_number=page.page_number,
                            source=iban_match.group(0).strip(),
                        ),
                    )

        warnings = []
        if "info.invoice_number" not in detected:
            warnings.append("Keine eindeutig beschriftete Belegnummer erkannt.")
        if document_type is DocumentType.SELF_BILLED_INVOICE:
            warnings.append("Belegtyp Gutschrift wurde aus dem Dokumenttext abgeleitet und muss geprueft werden.")
        warnings.append("Positionen werden ohne dokumentierte Layoutvorlage nicht automatisch uebernommen.")

        return PdfInvoiceDraft(
            document_type=document_type,
            fields=tuple(detected.values()),
            warnings=tuple(warnings),
        )

    @staticmethod
    def apply(draft: PdfInvoiceDraft, invoice: Invoice) -> Invoice:
        allowed_paths = {
            "info.invoice_number",
            "info.invoice_date",
            "info.payment_due_date",
            "info.delivery_date",
            "info.delivery_note",
            "buyer.name",
            "buyer.customer_number",
            "seller.name",
            "seller.supplier_number",
            "payment.iban",
            "payment.bic",
            "payment.payment_terms",
        }
        for field in draft.fields:
            if field.path not in allowed_paths:
                continue
            section, attribute = field.path.split(".", 1)
            setattr(getattr(invoice, section), attribute, field.value)
        invoice.calculate(force=True)
        return invoice

    @staticmethod
    def _detect_document_type(text: str) -> DocumentType:
        if re.search(
            r"\b(?:Gutschrift|Abrechnung\s+durch\s+(?:den\s+)?K[aä]ufer|Self[- ]Billing)\b",
            text,
            re.IGNORECASE,
        ):
            return DocumentType.SELF_BILLED_INVOICE
        return DocumentType.INVOICE

    @staticmethod
    def _normalize(value: str, normalizer: str | None) -> str:
        value = " ".join(value.strip().split())
        if normalizer == "upper":
            return value.upper()
        if normalizer == "text":
            return value.strip(" ;,")
        if normalizer == "date":
            for date_format in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, date_format).strftime("%d.%m.%Y")
                except ValueError:
                    pass
            return ""
        return value

    @staticmethod
    def _valid_iban(value: str) -> bool:
        if not 15 <= len(value) <= 34 or not value[:2].isalpha() or not value[2:4].isdigit():
            return False
        rearranged = value[4:] + value[:4]
        numeric = "".join(
            character if character.isdigit() else str(ord(character) - 55)
            for character in rearranged
        )
        return int(numeric) % 97 == 1


__all__ = [
    "DetectedInvoiceField",
    "PdfInvoiceDraft",
    "PdfInvoiceImport",
    "PdfInvoiceParser",
]
