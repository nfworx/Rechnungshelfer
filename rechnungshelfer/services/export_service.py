"""Anwendungsservice für validierte PDF- und XML-Exporte."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from rechnungshelfer.domain.models import Invoice
from rechnungshelfer.services.input_validation_service import (
    InputValidationError,
    normalize_invoice_input,
)
from rechnungshelfer.services.pdf_service import create_pdf
from rechnungshelfer.services.validation_service import (
    ExternalInvoiceValidator,
    ValidationResult,
    format_missing_fields,
    get_missing_required_fields,
    validate_invoice,
)
from rechnungshelfer.services.xml_service import create_xml


@dataclass(frozen=True)
class XmlExportResult:
    xml_bytes: bytes
    validation_result: ValidationResult


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


class InvoiceExportService:
    """Orchestriert Eingabeprüfung, Erzeugung, Validierung und Speicherung."""

    def __init__(
        self,
        *,
        external_validator: ExternalInvoiceValidator | None = None,
        supplier_number_provider: Callable[[], str] | None = None,
        pdf_renderer: Callable = create_pdf,
        xml_renderer: Callable = create_xml,
    ):
        self._external_validator = external_validator
        self._supplier_number_provider = supplier_number_provider
        self._pdf_renderer = pdf_renderer
        self._xml_renderer = xml_renderer

    def export_pdf(self, invoice: Invoice, filepath: str | Path) -> None:
        self._normalize(invoice)
        missing = get_missing_required_fields(invoice, for_xml=False)
        if missing:
            raise ValueError(format_missing_fields(missing, "PDF"))

        invoice.calculate(force=True)
        self._pdf_renderer(invoice, filepath)

    def export_xml(
        self,
        invoice: Invoice,
        filepath: str | Path,
    ) -> XmlExportResult:
        self._normalize(invoice)
        self._ensure_self_billed_supplier_number(invoice)

        missing = get_missing_required_fields(invoice, for_xml=True)
        if missing:
            raise ValueError(format_missing_fields(missing, "XML"))

        xml_bytes = self._xml_renderer(
            invoice,
            output_filename=None,
            include_extensions=False,
        )
        validation_result = validate_invoice(
            xml_bytes,
            invoice,
            external_validator=self._external_validator,
        )

        if validation_result.errors or validation_result.warnings:
            raise ExportValidationError(
                "XML-Export wurde abgebrochen.\n\n"
                "Die Validierung ist fehlgeschlagen.",
                details=self._format_validation_issues(validation_result),
                report_html=validation_result.report_html,
            )

        Path(filepath).write_bytes(xml_bytes)
        return XmlExportResult(
            xml_bytes=xml_bytes,
            validation_result=validation_result,
        )

    @staticmethod
    def _normalize(invoice: Invoice) -> None:
        try:
            normalize_invoice_input(invoice)
        except InputValidationError as exc:
            raise ValueError(str(exc)) from exc

    def _ensure_self_billed_supplier_number(self, invoice: Invoice) -> None:
        if not invoice.is_self_billed or invoice.seller.supplier_number:
            return
        if self._supplier_number_provider is None:
            raise ValueError("Lieferantennummer fehlt.")
        invoice.seller.supplier_number = self._supplier_number_provider()

    @staticmethod
    def _format_validation_issues(result: ValidationResult) -> str:
        messages = []
        if result.errors:
            messages.append("Validierungsfehler:")
            messages.extend(f"- {error}" for error in result.errors)
        if result.warnings:
            if messages:
                messages.append("")
            messages.append("Validierungswarnungen:")
            messages.extend(f"- {warning}" for warning in result.warnings)
        return "\n".join(messages)
