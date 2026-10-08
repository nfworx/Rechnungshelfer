"""Konservative Zuordnung extrahierter PDF-Texte zum bestehenden Invoice-Modell."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from rechnungshelfer.domain.models import DocumentType, Invoice
from .pdf_import_service import PdfImportResult, normalize_ocr_text


BUSINESS_PARTNER_NUMBER_PATH = "business_partner.number"


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
class PdfInvoiceAnalysis:
    extraction: PdfImportResult
    draft: PdfInvoiceDraft


@dataclass(frozen=True)
class PdfInvoiceImport(PdfInvoiceAnalysis):
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
            BUSINESS_PARTNER_NUMBER_PATH,
            re.compile(
                r"^\s*(?:Geschäftspartnernummer|Geschaeftspartnernummer|"
                r"Kundennummer|Kunden-Nr\.?|Lieferantennummer|Lieferanten-Nr\.?)"
                r"\s*:\s*(?P<value>[A-Z0-9][A-Z0-9./_-]{1,39})\s*$",
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
    _GUTSCHRIFT_HEADER_PATTERN = re.compile(
        r"^\s*[^\n]*Gutschrift[^\n]*\n\s*(?:Gutschrifts?)?Nr\.?\s*:\s*"
        r"(?P<number>[A-Z0-9][A-Z0-9./_-]{1,49})\s+vom\s+"
        r"(?P<date>\d{1,2}[.]\d{1,2}[.]\d{2,4})\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    _CREDITOR_PATTERN = re.compile(
        r"(?:Kreditor(?:en)?|Lieferant(?:en)?)[\s-]*(?:Nr\.?|Nummer)\s*:\s*"
        r"(?P<value>[A-Z0-9][A-Z0-9./_-]{1,39})",
        re.IGNORECASE,
    )
    _FUZZY_CREDITOR_PATTERN = re.compile(
        r"^\s*(?:Herr|Frau)?\s*[^\n:]{2,60}[- ]N(?:j|i|r){1,3}\.?\s*:\s*"
        r"(?P<value>\d[A-Z0-9./_-]{1,39})\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    _TAX_NUMBER_PATTERN = re.compile(
        r"(?:Steuer|St[.-]?)[\s-]*(?:Nr\.?|Nummer)\s*:\s*"
        r"(?P<value>\d[\d /-]{4,30}\d)",
        re.IGNORECASE,
    )
    _DELIVERY_NOTE_WITH_DATE_PATTERN = re.compile(
        r"(?:Lieferschein(?:nummer)?|Lieferschein-Nr\.?)\s*:\s*"
        r"(?P<value>[A-Z0-9][A-Z0-9./_-]{1,49})\s+vom\s+"
        r"(?P<date>\d{1,2}[.]\d{1,2}[.]\d{2,4})",
        re.IGNORECASE,
    )

    def parse(self, extraction: PdfImportResult) -> PdfInvoiceDraft:
        document_type = self._detect_document_type(extraction.full_text)
        detected = {}
        uncertain_creditor = False
        tax_number_without_separator = False
        delivery_notes: set[str] = set()

        for page in extraction.pages:
            page_text = self._searchable_page_text(page)
            for path, pattern, confidence, normalizer in self._LABELED_PATTERNS:
                if (
                    document_type is DocumentType.SELF_BILLED_INVOICE
                    and path == "payment.bic"
                ):
                    continue
                match = pattern.search(page_text)
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

            header_match = self._GUTSCHRIFT_HEADER_PATTERN.search(page_text)
            if header_match and document_type is DocumentType.SELF_BILLED_INVOICE:
                detected.setdefault(
                    "info.invoice_number",
                    self._field(
                        "info.invoice_number", header_match.group("number"), 0.94,
                        page.page_number, header_match.group(0),
                    ),
                )
                invoice_date = self._normalize(header_match.group("date"), "date")
                if invoice_date:
                    detected.setdefault(
                        "info.invoice_date",
                        self._field(
                            "info.invoice_date", invoice_date, 0.94,
                            page.page_number, header_match.group(0),
                        ),
                    )

            creditor_match = self._CREDITOR_PATTERN.search(page_text)
            if creditor_match and document_type is DocumentType.SELF_BILLED_INVOICE:
                detected.setdefault(
                    BUSINESS_PARTNER_NUMBER_PATH,
                    self._field(
                        BUSINESS_PARTNER_NUMBER_PATH, creditor_match.group("value"), 0.95,
                        page.page_number, creditor_match.group(0),
                    ),
                )
            elif document_type is DocumentType.SELF_BILLED_INVOICE:
                fuzzy_creditor = self._FUZZY_CREDITOR_PATTERN.search(page_text)
                if fuzzy_creditor:
                    detected.setdefault(
                        BUSINESS_PARTNER_NUMBER_PATH,
                        self._field(
                            BUSINESS_PARTNER_NUMBER_PATH, fuzzy_creditor.group("value"), 0.65,
                            page.page_number, fuzzy_creditor.group(0),
                        ),
                    )
                    uncertain_creditor = True

            tax_search_text = page_text
            if document_type is DocumentType.SELF_BILLED_INVOICE:
                heading = re.search(r"\bGutschrift\b", page_text, re.IGNORECASE)
                tax_search_text = page_text[:heading.start()] if heading else ""
            tax_match = self._TAX_NUMBER_PATTERN.search(tax_search_text)
            if tax_match:
                tax_number = " ".join(tax_match.group("value").split())
                detected.setdefault(
                    "seller.tax_number",
                    self._field(
                        "seller.tax_number", tax_number,
                        0.90 if "/" in tax_number else 0.72,
                        page.page_number, tax_match.group(0),
                    ),
                )
                tax_number_without_separator = "/" not in tax_number

            for delivery_match in self._DELIVERY_NOTE_WITH_DATE_PATTERN.finditer(page_text):
                delivery_notes.add(delivery_match.group("value"))
                detected.setdefault(
                    "info.delivery_note",
                    self._field(
                        "info.delivery_note", delivery_match.group("value"), 0.92,
                        page.page_number, delivery_match.group(0),
                    ),
                )

            iban_match = (
                None
                if document_type is DocumentType.SELF_BILLED_INVOICE
                else self._IBAN_PATTERN.search(page_text)
            )
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
        if uncertain_creditor:
            warnings.append(
                "Die Kreditor-/Lieferantennummer wurde aus einem stark fehlerhaften OCR-Label abgeleitet."
            )
        if tax_number_without_separator:
            warnings.append(
                "Die erkannte Steuernummer enthaelt keine Trennzeichen und muss am Original geprueft werden."
            )
        if len(delivery_notes) > 1:
            warnings.append(
                "Mehrere Lieferscheine erkannt; nur der erste wird in das einzelne Formularfeld uebernommen."
            )
        warnings.append("Positionen werden ohne dokumentierte Layoutvorlage nicht automatisch uebernommen.")

        return PdfInvoiceDraft(
            document_type=document_type,
            fields=tuple(detected.values()),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _field(path, value, confidence, page_number, source):
        return DetectedInvoiceField(
            path=path,
            value=value,
            confidence=confidence,
            page_number=page_number,
            source=" ".join(source.strip().split()),
        )

    @classmethod
    def _searchable_page_text(cls, page) -> str:
        text = normalize_ocr_text(page.text)
        block_text = cls._lines_from_blocks(page.blocks)
        if block_text and block_text not in text:
            text = f"{text}\n{block_text}" if text else block_text
        return text

    @staticmethod
    def _lines_from_blocks(blocks) -> str:
        words = [block for block in blocks if block.text.strip() and "\n" not in block.text]
        if len(words) < 2:
            return ""
        words.sort(key=lambda block: (-(block.top + block.bottom) / 2, block.left))
        lines: list[list] = []
        centers: list[float] = []
        heights: list[float] = []
        for block in words:
            center = (block.top + block.bottom) / 2
            height = max(block.top - block.bottom, 1.0)
            if not lines or abs(center - centers[-1]) > max(3.0, height * 0.65, heights[-1] * 0.65):
                lines.append([block])
                centers.append(center)
                heights.append(height)
            else:
                lines[-1].append(block)
                count = len(lines[-1])
                centers[-1] = ((centers[-1] * (count - 1)) + center) / count
                heights[-1] = max(heights[-1], height)
        return "\n".join(
            " ".join(block.text.strip() for block in sorted(line, key=lambda item: item.left))
            for line in lines
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
            "seller.name",
            "seller.tax_number",
            "payment.iban",
            "payment.bic",
            "payment.payment_terms",
        }
        for field in draft.fields:
            if field.path == BUSINESS_PARTNER_NUMBER_PATH:
                if draft.document_type is DocumentType.SELF_BILLED_INVOICE:
                    invoice.seller.supplier_number = field.value
                else:
                    invoice.buyer.customer_number = field.value
                continue
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
    "BUSINESS_PARTNER_NUMBER_PATH",
    "DetectedInvoiceField",
    "PdfInvoiceAnalysis",
    "PdfInvoiceDraft",
    "PdfInvoiceImport",
    "PdfInvoiceParser",
]
