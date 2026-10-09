"""Konservative Erkennung tabellarischer Sammel-Final-Gutschriften."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Generic, TypeVar

from .pdf_import_service import ExtractionMethod, PdfImportResult


T = TypeVar("T")
Bounds = tuple[float, float, float, float]


@dataclass(frozen=True)
class DetectedValue(Generic[T]):
    value: T
    raw_text: str
    page_number: int
    confidence: float
    bounds: Bounds | None = None


@dataclass(frozen=True)
class SettlementDetailRowDraft:
    label: DetectedValue[str]
    analysis_value: DetectedValue[Decimal] | None = None
    quantity_change_kg: DetectedValue[Decimal] | None = None
    price_change_per_tonne: DetectedValue[Decimal] | None = None


@dataclass(frozen=True)
class SettlementDeliveryDraft:
    ticket_number: DetectedValue[str]
    delivery_date: DetectedValue[date]
    grain_name: DetectedValue[str] | None = None
    gross_quantity_kg: DetectedValue[Decimal] | None = None
    base_price_per_tonne: DetectedValue[Decimal] | None = None
    settlement_quantity_kg: DetectedValue[Decimal] | None = None
    settlement_price_per_tonne: DetectedValue[Decimal] | None = None
    net_amount: DetectedValue[Decimal] | None = None
    details: tuple[SettlementDetailRowDraft, ...] = ()


@dataclass(frozen=True)
class SettlementCreditNoteDraft:
    format_confidence: float
    credit_note_number: DetectedValue[str] | None
    credit_note_date: DetectedValue[date] | None
    deliveries: tuple[SettlementDeliveryDraft, ...]
    supplier_number: DetectedValue[str] | None = None
    supplier_name: DetectedValue[str] | None = None
    supplier_street: DetectedValue[str] | None = None
    supplier_postcode: DetectedValue[str] | None = None
    supplier_city: DetectedValue[str] | None = None
    supplier_country: DetectedValue[str] | None = None
    supplier_phone: DetectedValue[str] | None = None
    supplier_email: DetectedValue[str] | None = None
    supplier_vat: DetectedValue[str] | None = None
    supplier_tax_number: DetectedValue[str] | None = None
    supplier_registry_number: DetectedValue[str] | None = None
    supplier_contact_name: DetectedValue[str] | None = None
    supplier_buyer_reference: DetectedValue[str] | None = None
    iban: DetectedValue[str] | None = None
    bic: DetectedValue[str] | None = None
    account_holder: DetectedValue[str] | None = None
    payment_terms: DetectedValue[str] | None = None
    vat_rate: DetectedValue[Decimal] | None = None
    net_amount: DetectedValue[Decimal] | None = None
    vat_amount: DetectedValue[Decimal] | None = None
    total_amount: DetectedValue[Decimal] | None = None
    advance_payment: DetectedValue[Decimal] | None = None
    credit_amount: DetectedValue[Decimal] | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SourceLine:
    text: str
    page_number: int
    confidence: float
    bounds: Bounds | None = None


@dataclass
class _DeliveryBuilder:
    ticket_number: DetectedValue[str]
    delivery_date: DetectedValue[date]
    product_rows: list[tuple[
        DetectedValue[str],
        DetectedValue[Decimal],
        DetectedValue[Decimal],
        DetectedValue[Decimal] | None,
    ]]
    details: list[SettlementDetailRowDraft]


class SettlementCreditNoteParser:
    """Liest beobachtete Werte, ohne Abrechnungsregeln erneut anzuwenden."""

    _TITLE_PATTERN = re.compile(
        r"\bSAMMEL\s*[-–—]?\s*FINAL\s*[-–—]?\s*GUTSCHRIFT\b",
        re.IGNORECASE,
    )
    _HEADER_PATTERN = re.compile(
        r"\bNr\.?\s*:?\s*(?P<number>[A-Z0-9][A-Z0-9./_-]{1,49})"
        r"\s+vom\s+(?P<date>\d{1,2}[.]\d{1,2}[.]\d{2,4})\b",
        re.IGNORECASE,
    )
    _DELIVERY_PATTERN = re.compile(
        r"^Lieferschein\s*-?\s*Nr\.?\s*:?\s*"
        r"(?P<number>[A-Z0-9][A-Z0-9./_-]{1,49})\s+vom\s+"
        r"(?P<date>\d{1,2}[.]\d{1,2}[.]\d{2,4})\s*$",
        re.IGNORECASE,
    )
    _NUMBER = r"-?(?:\d{1,3}(?:[.]\d{3})+|\d+)(?:,\d+)?"
    _PRODUCT_PATTERN = re.compile(
        rf"^(?P<name>.*?\D)\s+(?P<quantity>{_NUMBER})\s+"
        rf"(?P<price>{_NUMBER})(?:\s+(?P<amount>{_NUMBER}))?"
        r"(?:\s+\d)?\s*$",
        re.IGNORECASE,
    )
    _DETAIL_PATTERN = re.compile(
        rf"^(?P<analysis>{_NUMBER})\s*%\s*(?P<label>.+?)\s+"
        rf"(?P<change>{_NUMBER})\s*$",
        re.IGNORECASE,
    )
    _VAT_PATTERN = re.compile(
        rf"(?P<rate>{_NUMBER})\s*%\s*Mehrwertsteuer(?:\s+EUR)?\s+"
        rf"(?P<amount>{_NUMBER})\s*$",
        re.IGNORECASE,
    )
    _TOTAL_PATTERN = re.compile(
        rf"^Gesamtbetrag\s*:?[ ]*(?P<amount>{_NUMBER})\s*$",
        re.IGNORECASE,
    )
    _ADVANCE_PATTERN = re.compile(
        rf"^Abschlagszahlung\s*:?[ ]*(?P<amount>{_NUMBER})\s*$",
        re.IGNORECASE,
    )
    _CREDIT_PATTERN = re.compile(
        rf"^Gutschrift(?:s)?betrag(?:\s+in\s+EUR)?\s*:?[ ]*"
        rf"(?P<amount>{_NUMBER})\s*$",
        re.IGNORECASE,
    )
    _MONEY_ONLY_PATTERN = re.compile(rf"^(?P<amount>{_NUMBER})$")
    _LABELED_FIELDS = {
        "supplier_number": re.compile(r"^Lieferant(?:en)?nummer\s*:\s*(.+)$", re.I),
        "supplier_name": re.compile(r"^Lieferant\s*:\s*(.+)$", re.I),
        "supplier_street": re.compile(r"^Stra(?:ss|ß)e\s*:\s*(.+)$", re.I),
        "supplier_country": re.compile(r"^Land\s*:\s*(.+)$", re.I),
        "supplier_phone": re.compile(r"^Telefon\s*:\s*(.+)$", re.I),
        "supplier_email": re.compile(r"^E-?Mail\s*:\s*(.+)$", re.I),
        "supplier_vat": re.compile(r"^USt-?IdNr\.?\s*:\s*(.+)$", re.I),
        "supplier_tax_number": re.compile(r"^Steuernummer\s*:\s*(.+)$", re.I),
        "supplier_registry_number": re.compile(r"^Handelsregister\s*:\s*(.+)$", re.I),
        "supplier_contact_name": re.compile(r"^Kontaktperson\s*:\s*(.+)$", re.I),
        "supplier_buyer_reference": re.compile(r"^K(?:ae|ä)uferreferenz\s*:\s*(.+)$", re.I),
        "iban": re.compile(r"^IBAN\s*:\s*(.+)$", re.I),
        "bic": re.compile(r"^BIC\s*:\s*(.+)$", re.I),
        "account_holder": re.compile(r"^Kontoinhaber\s*:\s*(.+)$", re.I),
        "payment_terms": re.compile(r"^Zahlungsbedingungen\s*:\s*(.+)$", re.I),
    }
    _POSTCODE_CITY_PATTERN = re.compile(
        r"^PLZ\s+Ort\s*:\s*(?P<postcode>\d{5})\s+(?P<city>.+)$",
        re.I,
    )

    def parse(
        self,
        extraction: PdfImportResult,
    ) -> SettlementCreditNoteDraft | None:
        lines = self._source_lines(extraction)
        title_line = next(
            (line for line in lines if self._TITLE_PATTERN.search(line.text)),
            None,
        )
        header_entry = next(
            (
                (line, match)
                for line in lines
                if (match := self._HEADER_PATTERN.search(line.text))
            ),
            None,
        )
        column_hits = {
            label
            for line in lines[:10]
            for label in ("bezeichnung", "menge", "preis", "betrag")
            if label in line.text.casefold()
        }
        if title_line is None or (header_entry is None and len(column_hits) < 3):
            return None

        warnings: list[str] = []
        number = None
        credit_date = None
        if header_entry is not None:
            header_line, header_match = header_entry
            number = self._detected(header_line, header_match.group("number"))
            parsed_date = self._date_value(header_match.group("date"))
            if parsed_date is not None:
                credit_date = self._detected(header_line, parsed_date)
            else:
                warnings.append("Das erkannte Gutschriftsdatum ist ungültig.")
        else:
            warnings.append("Keine Gutschriftnummer mit Ausstellungsdatum erkannt.")

        deliveries = self._parse_deliveries(lines, warnings)
        totals = self._parse_totals(lines, warnings)
        party = self._parse_party_and_payment(lines)
        evidence = [title_line]
        if header_entry is not None:
            evidence.append(header_entry[0])
        format_confidence = sum(line.confidence for line in evidence) / len(evidence)
        if len(column_hits) < 3:
            format_confidence *= 0.9

        return SettlementCreditNoteDraft(
            format_confidence=max(0.0, min(format_confidence, 1.0)),
            credit_note_number=number,
            credit_note_date=credit_date,
            deliveries=tuple(deliveries),
            **party,
            vat_rate=totals["vat_rate"],
            net_amount=totals["net_amount"],
            vat_amount=totals["vat_amount"],
            total_amount=totals["total_amount"],
            advance_payment=totals["advance_payment"],
            credit_amount=totals["credit_amount"],
            warnings=tuple(warnings),
        )

    def _parse_party_and_payment(self, lines: list[_SourceLine]):
        values = {name: None for name in self._LABELED_FIELDS}
        values.update({"supplier_postcode": None, "supplier_city": None})
        for line in lines:
            if match := self._POSTCODE_CITY_PATTERN.match(line.text):
                values["supplier_postcode"] = self._detected(
                    line, match.group("postcode").strip()
                )
                values["supplier_city"] = self._detected(
                    line, match.group("city").strip()
                )
                continue
            for name, pattern in self._LABELED_FIELDS.items():
                if match := pattern.match(line.text):
                    value = match.group(1).strip()
                    if name in {"iban", "bic"}:
                        value = re.sub(r"\s+", "", value)
                    values[name] = self._detected(line, value)
                    break
        return values

    def _parse_deliveries(
        self,
        lines: list[_SourceLine],
        warnings: list[str],
    ) -> list[SettlementDeliveryDraft]:
        builders: list[_DeliveryBuilder] = []
        current: _DeliveryBuilder | None = None

        for line in lines:
            header = self._DELIVERY_PATTERN.match(line.text)
            if header:
                parsed_date = self._date_value(header.group("date"))
                if parsed_date is None:
                    continue
                current = _DeliveryBuilder(
                    ticket_number=self._detected(line, header.group("number")),
                    delivery_date=self._detected(line, parsed_date),
                    product_rows=[],
                    details=[],
                )
                builders.append(current)
                continue
            if current is None or self._is_totals_line(line.text):
                continue

            detail = self._parse_detail(line)
            if detail is not None:
                current.details.append(detail)
                continue
            product = self._parse_product(line)
            if product is not None:
                current.product_rows.append(product)

        if not builders:
            warnings.append("Keine Lieferscheinblöcke erkannt.")
            return []

        deliveries = []
        for builder in builders:
            first = builder.product_rows[0] if builder.product_rows else None
            final = next(
                (row for row in reversed(builder.product_rows) if row[3] is not None),
                None,
            )
            if first is None:
                warnings.append(
                    f"Lieferschein {builder.ticket_number.value}: keine Produktzeile erkannt."
                )
            if final is None:
                warnings.append(
                    f"Lieferschein {builder.ticket_number.value}: kein Endbetrag erkannt."
                )
            deliveries.append(
                SettlementDeliveryDraft(
                    ticket_number=builder.ticket_number,
                    delivery_date=builder.delivery_date,
                    grain_name=(final or first)[0] if (final or first) else None,
                    gross_quantity_kg=first[1] if first else None,
                    base_price_per_tonne=first[2] if first else None,
                    settlement_quantity_kg=final[1] if final else None,
                    settlement_price_per_tonne=final[2] if final else None,
                    net_amount=final[3] if final else None,
                    details=tuple(builder.details),
                )
            )
        return deliveries

    def _parse_product(self, line: _SourceLine):
        match = self._PRODUCT_PATTERN.match(line.text)
        if not match:
            return None
        try:
            name = self._detected(line, match.group("name").strip())
            quantity = self._detected(
                line,
                self._decimal_value(match.group("quantity"), grouped_integer=True),
            )
            price = self._detected(
                line,
                self._decimal_value(match.group("price")),
            )
            amount = (
                self._detected(line, self._decimal_value(match.group("amount")))
                if match.group("amount") is not None
                else None
            )
            return name, quantity, price, amount
        except InvalidOperation:
            return None

    def _parse_detail(self, line: _SourceLine) -> SettlementDetailRowDraft | None:
        match = self._DETAIL_PATTERN.match(line.text)
        if not match:
            return None
        try:
            label_text = match.group("label").strip()
            analysis = self._detected(
                line,
                self._decimal_value(match.group("analysis")),
            )
            change = self._detected(
                line,
                self._decimal_value(match.group("change"), grouped_integer=True),
            )
        except InvalidOperation:
            return None

        is_price_change = bool(
            re.search(r"(?:HL|Hektoliter).*Gewicht", label_text, re.IGNORECASE)
        )
        return SettlementDetailRowDraft(
            label=self._detected(line, label_text),
            analysis_value=analysis,
            quantity_change_kg=None if is_price_change else change,
            price_change_per_tonne=change if is_price_change else None,
        )

    def _parse_totals(self, lines: list[_SourceLine], warnings: list[str]):
        totals = {
            "vat_rate": None,
            "net_amount": None,
            "vat_amount": None,
            "total_amount": None,
            "advance_payment": None,
            "credit_amount": None,
        }
        for index, line in enumerate(lines):
            if match := self._VAT_PATTERN.search(line.text):
                totals["vat_rate"] = self._number_from(line, match.group("rate"))
                totals["vat_amount"] = self._number_from(line, match.group("amount"))
                for previous in reversed(lines[max(0, index - 3):index]):
                    money = self._MONEY_ONLY_PATTERN.match(previous.text)
                    if money and "," in money.group("amount"):
                        totals["net_amount"] = self._number_from(
                            previous,
                            money.group("amount"),
                        )
                        break
            elif match := self._TOTAL_PATTERN.match(line.text):
                totals["total_amount"] = self._number_from(line, match.group("amount"))
            elif match := self._ADVANCE_PATTERN.match(line.text):
                totals["advance_payment"] = self._number_from(line, match.group("amount"))
            elif match := self._CREDIT_PATTERN.match(line.text):
                totals["credit_amount"] = self._number_from(line, match.group("amount"))

        labels = {
            "vat_rate": "Steuersatz",
            "net_amount": "Nettosumme",
            "vat_amount": "Umsatzsteuerbetrag",
            "total_amount": "Gesamtbetrag",
            "credit_amount": "Gutschriftbetrag",
        }
        for key, label in labels.items():
            if totals[key] is None:
                warnings.append(f"{label} wurde nicht erkannt.")
        return totals

    def _number_from(self, line: _SourceLine, raw_value: str):
        try:
            return self._detected(line, self._decimal_value(raw_value))
        except InvalidOperation:
            return None

    @classmethod
    def _is_totals_line(cls, text: str) -> bool:
        return bool(
            cls._VAT_PATTERN.search(text)
            or cls._TOTAL_PATTERN.match(text)
            or cls._ADVANCE_PATTERN.match(text)
            or cls._CREDIT_PATTERN.match(text)
        )

    @staticmethod
    def _detected(line: _SourceLine, value: T) -> DetectedValue[T]:
        return DetectedValue(
            value=value,
            raw_text=line.text,
            page_number=line.page_number,
            confidence=line.confidence,
            bounds=line.bounds,
        )

    @staticmethod
    def _date_value(value: str) -> date | None:
        for date_format in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _decimal_value(value: str, *, grouped_integer: bool = False) -> Decimal:
        normalized = value.strip().replace(" ", "")
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        elif grouped_integer and re.fullmatch(r"-?\d{1,3}(?:[.]\d{3})+", normalized):
            normalized = normalized.replace(".", "")
        return Decimal(normalized)

    @classmethod
    def _source_lines(cls, extraction: PdfImportResult) -> list[_SourceLine]:
        lines: list[_SourceLine] = []
        for page in extraction.pages:
            block_lines = cls._group_blocks(page.blocks, page.page_number)
            if block_lines:
                lines.extend(block_lines)
                continue
            fallback_confidence = (
                1.0 if page.method is ExtractionMethod.DIGITAL else 0.5
            )
            lines.extend(
                _SourceLine(
                    text=" ".join(text.split()),
                    page_number=page.page_number,
                    confidence=fallback_confidence,
                )
                for text in page.text.splitlines()
                if text.strip()
            )
        return lines

    @staticmethod
    def _group_blocks(blocks, page_number: int) -> list[_SourceLine]:
        words = [
            block
            for block in blocks
            if block.text.strip() and "\n" not in block.text
        ]
        if not words:
            return []
        words.sort(key=lambda block: (-(block.top + block.bottom) / 2, block.left))
        groups: list[list] = []
        centers: list[float] = []
        heights: list[float] = []
        for block in words:
            center = (block.top + block.bottom) / 2
            height = max(block.top - block.bottom, 1.0)
            if (
                not groups
                or abs(center - centers[-1])
                > max(3.0, height * 0.65, heights[-1] * 0.65)
            ):
                groups.append([block])
                centers.append(center)
                heights.append(height)
            else:
                groups[-1].append(block)
                count = len(groups[-1])
                centers[-1] = ((centers[-1] * (count - 1)) + center) / count
                heights[-1] = max(heights[-1], height)

        source_lines = []
        for group in groups:
            ordered = sorted(group, key=lambda item: item.left)
            confidences = [
                block.confidence
                for block in ordered
                if block.confidence is not None
            ]
            confidence = (
                sum(confidences) / len(confidences)
                if confidences
                else 1.0
            )
            source_lines.append(
                _SourceLine(
                    text=" ".join(block.text.strip() for block in ordered),
                    page_number=page_number,
                    confidence=confidence,
                    bounds=(
                        min(block.left for block in ordered),
                        min(block.bottom for block in ordered),
                        max(block.right for block in ordered),
                        max(block.top for block in ordered),
                    ),
                )
            )
        return source_lines


__all__ = [
    "DetectedValue",
    "SettlementCreditNoteDraft",
    "SettlementCreditNoteParser",
    "SettlementDeliveryDraft",
    "SettlementDetailRowDraft",
]
