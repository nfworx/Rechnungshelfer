"""Anwendungsfälle zum Erstellen, Speichern und Laden von Belegen."""

from rechnungshelfer.application.errors import CustomerDuplicateError
from rechnungshelfer.domain.invoice_factory import InvoiceFactory
from rechnungshelfer.domain.models import (
    DocumentType,
    Invoice,
    Payment,
    Seller,
)
from rechnungshelfer.services.input_validation_service import (
    InputValidationError,
    normalize_invoice_input,
)
from rechnungshelfer.services.pdf_import_service import PdfImportService
from rechnungshelfer.services.pdf_invoice_parser import (
    PdfInvoiceAnalysis,
    PdfInvoiceImport,
    PdfInvoiceParser,
)
from rechnungshelfer.services.settlement_credit_note_parser import (
    SettlementCreditNoteParser,
)
from rechnungshelfer.services.xml_reader import InvoiceParsingError, read_xml_file


class InvoiceApplicationService:
    def __init__(
        self,
        *,
        database,
        invoice_repository,
        business_partner_repository,
        master_data_repository,
        invoice_factory: InvoiceFactory,
        pdf_import_service=None,
        pdf_invoice_parser=None,
        settlement_credit_note_parser=None,
    ):
        self._database = database
        self._invoices = invoice_repository
        self._partners = business_partner_repository
        self._master_data = master_data_repository
        self._factory = invoice_factory
        self._pdf_import = pdf_import_service or PdfImportService()
        self._pdf_parser = pdf_invoice_parser or PdfInvoiceParser()
        self._settlement_parser = (
            settlement_credit_note_parser or SettlementCreditNoteParser()
        )

    def create_empty_invoice(
        self,
        document_type=DocumentType.INVOICE,
    ) -> Invoice:
        document_type = DocumentType.from_value(document_type)
        own_company, own_payment = self._master_data.load_into(
            Seller(),
            Payment(),
        )
        return self._factory.create(
            document_type,
            own_company=own_company,
            own_payment=own_payment,
        )

    def save_invoice(
        self,
        invoice: Invoice,
        *,
        allow_customer_duplicate: bool = False,
    ) -> None:
        try:
            normalize_invoice_input(invoice)
        except InputValidationError as exc:
            raise ValueError(str(exc)) from exc

        invoice.calculate(force=True)
        if not invoice.info.invoice_number:
            raise ValueError("Belegnummer fehlt")

        duplicates = self._different_customer_duplicates(invoice)
        if duplicates and not allow_customer_duplicate:
            raise CustomerDuplicateError(duplicates)

        with self._database.transaction():
            if invoice.is_self_billed and invoice.seller.name:
                self._partners.ensure_supplier(
                    invoice.seller,
                    invoice.payment,
                    commit=False,
                )

            self._invoices.save(invoice, commit=False)

            if (
                not invoice.is_self_billed
                and invoice.buyer.customer_number
                and invoice.buyer.name
            ):
                self._partners.ensure_customer(invoice.buyer, commit=False)

    def _different_customer_duplicates(self, invoice: Invoice):
        if (
            invoice.is_self_billed
            or not invoice.buyer.customer_number
            or not invoice.buyer.name
        ):
            return []

        return [
            duplicate
            for duplicate in self._partners.find_customer_duplicates(invoice.buyer)
            if duplicate.customer_number != invoice.buyer.customer_number
        ]

    def load_latest_invoice(self):
        return self._invoices.load_latest()

    def invoice_exists(self, invoice_number: str) -> bool:
        return bool(invoice_number) and self._invoices.exists(invoice_number)

    def list_invoice_summaries(self):
        return self._invoices.list_invoice_summaries()

    def load_invoice(self, invoice_number: str) -> Invoice:
        invoice = self._invoices.load(invoice_number)
        if invoice is None:
            raise ValueError(f"Rechnung nicht gefunden: {invoice_number}")
        invoice.calculate(force=True)
        return invoice

    def delete_invoice(self, invoice_number: str) -> None:
        if not invoice_number:
            raise ValueError("Keine Rechnungsnummer angegeben")
        self._invoices.delete(invoice_number)

    @staticmethod
    def load_from_xml(filepath) -> Invoice:
        try:
            return read_xml_file(filepath)
        except InvoiceParsingError as exc:
            raise ValueError(f"XML Fehler: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Fehler beim Laden: {exc}") from exc

    def load_from_pdf(self, filepath, *, password=None) -> PdfInvoiceImport:
        """Extrahiert einen Beleg in den Arbeitsspeicher, ohne ihn zu speichern."""

        analysis = self.analyze_pdf(filepath, password=password)
        return self.create_invoice_from_pdf_analysis(analysis)

    def analyze_pdf(self, filepath, *, password=None) -> PdfInvoiceAnalysis:
        """Fuehrt die dateibasierte Analyse ohne Datenbankzugriff aus."""

        extraction = self._pdf_import.extract(filepath, password=password)
        draft = self._pdf_parser.parse(extraction)
        return PdfInvoiceAnalysis(
            extraction=extraction,
            draft=draft,
            settlement_draft=self._settlement_parser.parse(extraction),
        )

    def create_invoice_from_pdf_analysis(
        self,
        analysis: PdfInvoiceAnalysis,
    ) -> PdfInvoiceImport:
        """Erzeugt den Formularbeleg im aufrufenden (GUI-)Thread."""

        if analysis.settlement_draft is not None:
            raise ValueError(
                "Die erkannte Testabrechnung muss vor der Übernahme geprüft werden."
            )

        if analysis.draft.errors:
            raise ValueError(
                "Der PDF-Rückimport wurde wegen widersprüchlicher oder ungültiger "
                "Rechnungsdaten gesperrt:\n- "
                + "\n- ".join(analysis.draft.errors)
            )

        if analysis.draft.embedded_invoice_data is not None:
            invoice = Invoice.from_dict(analysis.draft.embedded_invoice_data)
        else:
            invoice = self.create_empty_invoice(analysis.draft.document_type)
            self._pdf_parser.apply(analysis.draft, invoice)
        return PdfInvoiceImport(
            extraction=analysis.extraction,
            draft=analysis.draft,
            invoice=invoice,
        )

    def copy_invoice(self, invoice: Invoice) -> Invoice:
        return self._factory.copy(invoice)

    @staticmethod
    def recalculate(invoice: Invoice, force: bool = False) -> None:
        invoice.calculate(force=force)
