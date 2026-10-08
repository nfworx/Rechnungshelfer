"""Konservative Zuordnung extrahierter PDF-Texte zum bestehenden Invoice-Modell."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from rechnungshelfer.domain.models import DocumentType, Invoice, InvoiceItem
from .pdf_import_service import PdfImportResult, normalize_ocr_text
from .pdf_invoice_metadata import decode_invoice_metadata


BUSINESS_PARTNER_NUMBER_PATH = "business_partner.number"


@dataclass(frozen=True)
class DetectedInvoiceField:
    path: str
    value: str
    confidence: float
    page_number: int
    source: str


@dataclass(frozen=True)
class DetectedInvoiceItem:
    pos: int
    name: str
    description: str
    qty: str
    unit: str
    price_without_discount: str
    discount: str
    vat: str
    tax_category: str

    def to_invoice_item(self) -> InvoiceItem:
        return InvoiceItem(**asdict(self))


@dataclass(frozen=True)
class PdfInvoiceDraft:
    document_type: DocumentType
    fields: tuple[DetectedInvoiceField, ...]
    items: tuple[DetectedInvoiceItem, ...] = ()
    embedded_invoice_data: dict | None = None
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
                r"^\s*(?:Lieferdatum|Leistungsdatum|Liefer-/Leistungsdatum)\s*:?\s*"
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
        (
            "buyer.leitweg_id",
            re.compile(
                r"^\s*Leitweg-ID\s*:\s*(?P<value>[^\r\n]{2,100})$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.98,
            "text",
        ),
        (
            "info.delivery_instruction",
            re.compile(
                r"^\s*Lieferhinweis\s*:\s*(?P<value>[^\r\n]{2,200})$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.95,
            "text",
        ),
        (
            "payment.account_holder",
            re.compile(
                r"^\s*Kontoinhaber\s*:\s*(?P<value>[^\r\n]{2,100})$",
                re.IGNORECASE | re.MULTILINE,
            ),
            0.95,
            "text",
        ),
    )
    _IBAN_PATTERN = re.compile(
        r"(?:IBAN\s*:?\s*)?(?P<value>[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30})\b",
        re.IGNORECASE,
    )
    _APP_HEADER_PATTERN = re.compile(
        r"^\s*(?:Rechnung|Gutschrift)\s+Nr\.\s*"
        r"(?P<number>[A-Z0-9][A-Z0-9./_-]{1,49})\s+vom\s+"
        r"(?P<date>\d{1,2}[.]\d{1,2}[.]\d{2,4})\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    _APP_ITEM_PATTERN = re.compile(
        r"^(?P<pos>\d+)\s+(?P<name>.+?)\s+"
        r"(?P<qty>-?[\d.]+,\d{2})\s+"
        r"(?P<unit>Std|Stk|kg|g|t|l|m³|m²|m|Min|Tag|Woche|Monat|Jahr|Leistung)\s+"
        r"(?P<price>-?[\d.]+,\d{2})\s+"
        r"(?P<vat>[\d.]+(?:,\d+)?)%\s+"
        r"(?P<net>-?[\d.]+,\d{2})\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    _UNIT_CODES = {
        "std": "HUR", "stk": "C62", "kg": "KGM", "g": "GRM",
        "t": "TNE", "l": "LTR", "m³": "MTQ", "m²": "MTK",
        "m": "MTR", "min": "MIN", "tag": "DAY", "woche": "WEE",
        "monat": "MON", "jahr": "ANN", "leistung": "LS",
    }
    def parse(self, extraction: PdfImportResult) -> PdfInvoiceDraft:
        document_type = self._detect_document_type(extraction.full_text)
        detected = {}
        detected_items: dict[int, DetectedInvoiceItem] = {}

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

            self._parse_app_header(page_text, page.page_number, detected)
            self._parse_app_parties(
                page_text,
                page.page_number,
                detected,
                document_type,
            )
            for item in self._parse_app_items(page_text):
                detected_items.setdefault(item.pos, item)

        warnings = []
        embedded_invoice_data = None
        subject = next(
            (
                value
                for key, value in extraction.metadata.items()
                if key.casefold() == "subject"
            ),
            None,
        )
        try:
            embedded_invoice_data = decode_invoice_metadata(subject)
        except ValueError as exc:
            warnings.append(str(exc))

        if (
            "info.invoice_number" not in detected
            and embedded_invoice_data is None
        ):
            warnings.append("Keine eindeutig beschriftete Belegnummer erkannt.")
        if (
            document_type is DocumentType.SELF_BILLED_INVOICE
            and embedded_invoice_data is None
        ):
            warnings.append("Belegtyp Gutschrift wurde aus dem Dokumenttext abgeleitet und muss geprueft werden.")
        if embedded_invoice_data is not None:
            warnings.append(
                "Vollstaendige Rechnungsdaten wurden aus einem Rechnungshelfer-PDF erkannt."
            )
        elif not detected_items:
            warnings.append(
                "Positionen werden nur aus Rechnungshelfer-PDFs vollstaendig uebernommen."
            )

        return PdfInvoiceDraft(
            document_type=document_type,
            fields=tuple(detected.values()),
            items=tuple(detected_items.values()),
            embedded_invoice_data=embedded_invoice_data,
            warnings=tuple(warnings),
        )

    @classmethod
    def _parse_app_header(cls, text, page_number, detected):
        match = cls._APP_HEADER_PATTERN.search(text)
        if not match:
            return
        detected.setdefault(
            "info.invoice_number",
            cls._field(
                "info.invoice_number", match.group("number"), 0.99,
                page_number, match.group(0),
            ),
        )
        invoice_date = cls._normalize(match.group("date"), "date")
        if invoice_date:
            detected.setdefault(
                "info.invoice_date",
                cls._field(
                    "info.invoice_date", invoice_date, 0.99,
                    page_number, match.group(0),
                ),
            )

    @classmethod
    def _parse_app_parties(cls, text, page_number, detected, document_type):
        header = cls._APP_HEADER_PATTERN.search(text)
        if not header:
            return

        lines = [line.strip() for line in text[:header.start()].splitlines() if line.strip()]
        city_index = next(
            (
                index for index in range(len(lines) - 1, -1, -1)
                if re.match(r"^\d{5}\s+\S", lines[index])
            ),
            None,
        )
        if city_index is not None and city_index >= 2:
            start = next(
                (
                    index + 1 for index in range(city_index - 2, -1, -1)
                    if re.search(r",\s*\d{5}\s+", lines[index])
                ),
                max(0, city_index - 3),
            )
            recipient = lines[start:city_index + 1]
            if len(recipient) >= 3:
                postcode, city = recipient[-1].split(maxsplit=1)
                party_path = (
                    "seller"
                    if document_type is DocumentType.SELF_BILLED_INVOICE
                    else "buyer"
                )
                values = {
                    f"{party_path}.name": recipient[0],
                    f"{party_path}.street": recipient[-2],
                    f"{party_path}.postcode": postcode,
                    f"{party_path}.city": city,
                }
                if len(recipient) > 3:
                    values[f"{party_path}.contact_name"] = " ".join(
                        recipient[1:-2]
                    )
                for path, value in values.items():
                    detected.setdefault(
                        path,
                        cls._field(path, value, 0.94, page_number, "\n".join(recipient)),
                    )

        delivery_match = re.search(
            r"^Leistungsempf[^:\n]*:\s*(?P<first>[^\n]*)\n"
            r"(?P<rest>.*?)(?=^Lieferhinweis:|^Pos\s+Bezeichnung)",
            text,
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        if delivery_match:
            delivery_lines = [delivery_match.group("first").strip()]
            delivery_lines.extend(
                line.strip()
                for line in delivery_match.group("rest").splitlines()
                if line.strip()
            )
            if len(delivery_lines) >= 3 and re.match(r"^\d{5}\s+\S", delivery_lines[-1]):
                postcode, city = delivery_lines[-1].split(maxsplit=1)
                values = {
                    "delivery.name": " ".join(delivery_lines[:-2]),
                    "delivery.street": delivery_lines[-2],
                    "delivery.postcode": postcode,
                    "delivery.city": city,
                    "delivery.country": "DE",
                }
                for path, value in values.items():
                    detected.setdefault(
                        path,
                        cls._field(path, value, 0.94, page_number, delivery_match.group(0)),
                    )

    @classmethod
    def _parse_app_items(cls, text):
        matches = list(cls._APP_ITEM_PATTERN.finditer(text))
        items = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            details = text[match.end():end]
            totals = re.search(r"^Nettosumme:", details, re.IGNORECASE | re.MULTILINE)
            if totals:
                details = details[:totals.start()]
            detail_lines = [line.strip() for line in details.splitlines() if line.strip()]
            discount = "0.00"
            original_price = match.group("price")
            descriptions = []
            for line in detail_lines:
                discount_match = re.match(r"^Rabatt\s+-?(?P<value>[\d.]+,\d{2})$", line, re.IGNORECASE)
                original_match = re.match(
                    r"^Einzelpreis ohne Rabatt\s+(?P<value>[\d.]+,\d{2})$",
                    line,
                    re.IGNORECASE,
                )
                if discount_match:
                    discount = cls._decimal_value(discount_match.group("value"))
                elif original_match:
                    original_price = original_match.group("value")
                else:
                    descriptions.append(line)
            vat = cls._decimal_value(match.group("vat"))
            items.append(
                DetectedInvoiceItem(
                    pos=int(match.group("pos")),
                    name=match.group("name").strip(),
                    description=" ".join(descriptions),
                    qty=cls._decimal_value(match.group("qty")),
                    unit=cls._UNIT_CODES[match.group("unit").casefold()],
                    price_without_discount=cls._decimal_value(original_price),
                    discount=discount,
                    vat=vat,
                    tax_category="Z" if Decimal(vat) == 0 else "S",
                )
            )
        return items

    @staticmethod
    def _decimal_value(value):
        try:
            return format(Decimal(value.replace(".", "").replace(",", ".")), "f")
        except (InvalidOperation, AttributeError):
            return "0"

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
            "info.delivery_instruction",
            "buyer.name",
            "buyer.contact_name",
            "buyer.street",
            "buyer.postcode",
            "buyer.city",
            "buyer.leitweg_id",
            "seller.name",
            "seller.contact_name",
            "seller.street",
            "seller.postcode",
            "seller.city",
            "delivery.name",
            "delivery.street",
            "delivery.postcode",
            "delivery.city",
            "delivery.country",
            "payment.iban",
            "payment.bic",
            "payment.account_holder",
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
        if draft.items:
            invoice.items = [item.to_invoice_item() for item in draft.items]
        invoice.delivery.update_required_fields(invoice.buyer)
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
    "DetectedInvoiceItem",
    "PdfInvoiceAnalysis",
    "PdfInvoiceDraft",
    "PdfInvoiceImport",
    "PdfInvoiceParser",
]
