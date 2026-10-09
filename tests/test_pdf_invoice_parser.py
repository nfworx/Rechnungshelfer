import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from rechnungshelfer.application.invoice_service import InvoiceApplicationService
from rechnungshelfer.domain.invoice_factory import InvoiceFactory
from rechnungshelfer.domain.models import DocumentType, Payment, Seller
from rechnungshelfer.services.pdf_import_service import (
    ExtractionMethod,
    PdfImportResult,
    PdfImportService,
    PdfPageResult,
)
from rechnungshelfer.services.pdf_service import create_pdf
from rechnungshelfer.services.pdf_invoice_parser import (
    BUSINESS_PARTNER_NUMBER_PATH,
    PdfInvoiceParser,
)
from rechnungshelfer.services.sample_document_service import (
    create_sample_invoice,
    create_sample_self_billed_invoice,
)


def extraction_with(*page_texts):
    pages = tuple(
        PdfPageResult(
            page_number=index,
            text=text,
            method=ExtractionMethod.DIGITAL,
        )
        for index, text in enumerate(page_texts, start=1)
    )
    return PdfImportResult(
        source_file=Path("beispiel.pdf"),
        page_count=len(pages),
        pages=pages,
    )


class PdfInvoiceParserTests(unittest.TestCase):
    def test_imports_visible_layout_from_existing_program_pdf(self):
        original = create_sample_invoice()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alte-testrechnung.pdf"
            create_pdf(original, path)
            extraction = PdfImportService().extract(path)
        extraction = replace(extraction, metadata={})

        parser = PdfInvoiceParser()
        draft = parser.parse(extraction)
        imported = InvoiceFactory().create(DocumentType.INVOICE)
        parser.apply(draft, imported)

        self.assertEqual(imported.info.invoice_number, original.info.invoice_number)
        self.assertEqual(imported.info.invoice_date, original.info.invoice_date)
        self.assertEqual(imported.info.delivery_date, original.info.delivery_date)
        self.assertEqual(imported.buyer.name, original.buyer.name)
        self.assertEqual(imported.buyer.street, original.buyer.street)
        self.assertEqual(imported.buyer.postcode, original.buyer.postcode)
        self.assertEqual(imported.buyer.city, original.buyer.city)
        self.assertEqual(imported.delivery.name, original.delivery.name)
        self.assertEqual(imported.delivery.street, original.delivery.street)
        self.assertEqual(imported.info.delivery_instruction, original.info.delivery_instruction)
        self.assertEqual(imported.buyer.customer_number, original.buyer.customer_number)
        self.assertEqual(len(imported.items), 4)
        self.assertEqual(
            [vars(item) for item in imported.items],
            [vars(item) for item in original.items],
        )

    def test_detects_only_explicitly_labeled_invoice_fields(self):
        extraction = extraction_with(
            """Rechnung
Rechnungsnummer: RE-2026-4711
Rechnungsdatum: 2026-10-08
Zahlbar bis: 22.10.2026
Lieferdatum: 07.10.2026
Kundenname: Beispielkunde GmbH
Kundennummer: K-100
IBAN: DE89 3704 0044 0532 0130 00
BIC: COBADEFFXXX
Zahlungsbedingungen: Zahlbar innerhalb von 14 Tagen netto
Lieferschein: LS-88
"""
        )

        draft = PdfInvoiceParser().parse(extraction)

        self.assertEqual(draft.document_type, DocumentType.INVOICE)
        self.assertEqual(draft.get("info.invoice_number").value, "RE-2026-4711")
        self.assertEqual(draft.get("info.invoice_date").value, "08.10.2026")
        self.assertEqual(draft.get("info.payment_due_date").value, "22.10.2026")
        self.assertEqual(draft.get("buyer.name").value, "Beispielkunde GmbH")
        self.assertEqual(draft.get(BUSINESS_PARTNER_NUMBER_PATH).value, "K-100")
        self.assertEqual(draft.get("payment.iban").value, "DE89370400440532013000")
        self.assertEqual(draft.get("payment.bic").value, "COBADEFFXXX")
        self.assertEqual(draft.get("info.delivery_note").value, "LS-88")
        self.assertEqual(draft.get("info.invoice_number").page_number, 1)

    def test_detects_self_billed_invoice_but_requires_review(self):
        draft = PdfInvoiceParser().parse(
            extraction_with(
                "Gutschrift\nGutschriftsnummer: GS-55\nLieferant: Hof Beispiel"
            )
        )

        self.assertEqual(draft.document_type, DocumentType.SELF_BILLED_INVOICE)
        self.assertEqual(draft.get("seller.name").value, "Hof Beispiel")
        self.assertTrue(any("muss geprueft" in warning for warning in draft.warnings))

    def test_visible_self_billed_layout_maps_recipient_to_seller(self):
        original = create_sample_self_billed_invoice()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "alte-testgutschrift.pdf"
            create_pdf(original, path)
            extraction = replace(PdfImportService().extract(path), metadata={})

        draft = PdfInvoiceParser().parse(extraction)

        self.assertIsNone(draft.get("buyer.name"))
        self.assertEqual(draft.get("seller.name").value, original.seller.name)
        self.assertEqual(draft.get("seller.street").value, original.seller.street)
        self.assertEqual(draft.get("seller.postcode").value, original.seller.postcode)
        self.assertEqual(draft.get("seller.city").value, original.seller.city)

    def test_applies_business_partner_number_by_document_role(self):
        parser = PdfInvoiceParser()
        invoice_draft = parser.parse(
            extraction_with("Rechnung\nGeschäftspartnernummer: GP-100")
        )
        credit_note_draft = parser.parse(
            extraction_with("Gutschrift\nGeschäftspartnernummer: GP-100")
        )
        invoice = InvoiceFactory().create(DocumentType.INVOICE)
        credit_note = InvoiceFactory().create(DocumentType.SELF_BILLED_INVOICE)

        parser.apply(invoice_draft, invoice)
        parser.apply(credit_note_draft, credit_note)

        self.assertEqual(invoice.buyer.customer_number, "GP-100")
        self.assertEqual(invoice.seller.supplier_number, "")
        self.assertEqual(credit_note.seller.supplier_number, "GP-100")
        self.assertEqual(credit_note.buyer.customer_number, "")

    def test_does_not_accept_invalid_iban_or_unlabeled_party_names(self):
        draft = PdfInvoiceParser().parse(
            extraction_with(
                "Unbekannte Firma GmbH\nIBAN: DE00 0000 0000 0000 0000 00"
            )
        )

        self.assertIsNone(draft.get("payment.iban"))
        self.assertIsNone(draft.get("buyer.name"))
        self.assertIsNone(draft.get("seller.name"))

    def test_apply_preserves_unrecognized_or_default_data(self):
        invoice = InvoiceFactory().create(DocumentType.INVOICE)
        original_seller_name = invoice.seller.name
        parser = PdfInvoiceParser()
        draft = parser.parse(
            extraction_with(
                "Rechnungsnummer: R-9\nKundenname: Neuer Kunde\nRechnungsdatum: 08.10.2026"
            )
        )

        parser.apply(draft, invoice)

        self.assertEqual(invoice.info.invoice_number, "R-9")
        self.assertEqual(invoice.buyer.name, "Neuer Kunde")
        self.assertEqual(invoice.seller.name, original_seller_name)
        self.assertEqual(len(invoice.items), 1)


class PdfInvoiceApplicationServiceTests(unittest.TestCase):
    def _service(self, extraction):
        pdf_import = Mock()
        pdf_import.extract.return_value = extraction
        database = Mock()
        invoices = Mock()
        partners = Mock()
        master_data = Mock()
        master_data.load_into.return_value = (
            Seller(name="Eigener Betrieb"),
            Payment(account_holder="Eigener Betrieb"),
        )
        service = InvoiceApplicationService(
            database=database,
            invoice_repository=invoices,
            business_partner_repository=partners,
            master_data_repository=master_data,
            invoice_factory=InvoiceFactory(),
            pdf_import_service=pdf_import,
            pdf_invoice_parser=PdfInvoiceParser(),
        )
        return service, database, invoices, partners, master_data

    def test_background_analysis_does_not_access_repositories_or_master_data(self):
        extraction = extraction_with(
            "Gutschrift\nGutschriftsnummer: GS-2026-1\nLieferant: Beispielhof"
        )
        service, database, invoices, partners, master_data = self._service(
            extraction
        )

        analysis = service.analyze_pdf("gutschrift.pdf")

        self.assertEqual(analysis.draft.document_type, DocumentType.SELF_BILLED_INVOICE)
        master_data.load_into.assert_not_called()
        invoices.save.assert_not_called()
        partners.save_customer.assert_not_called()
        partners.save_supplier.assert_not_called()
        database.transaction.assert_not_called()

    def test_background_analysis_includes_structured_settlement_draft(self):
        extraction = extraction_with(
            """SAMMEL - FINAL - GUTSCHRIFT
Nr.: 91001 vom 30.11.2025
Analysewerte Bezeichnung Menge Preis Betrag
Lieferschein-Nr.: T1001 vom 09.08.2025
Hafer lose 2.815 160,00
Hafer lose 2.787 144,50 402,72
402,72
7,8 % Mehrwertsteuer EUR 31,41
Gesamtbetrag 434,13
Gutschriftbetrag in EUR 434,13
"""
        )
        service, database, invoices, partners, master_data = self._service(
            extraction
        )

        analysis = service.analyze_pdf("testabrechnung.pdf")

        self.assertIsNotNone(analysis.settlement_draft)
        self.assertEqual(analysis.settlement_draft.credit_note_number.value, "91001")
        self.assertEqual(len(analysis.settlement_draft.deliveries), 1)
        master_data.load_into.assert_not_called()
        invoices.save.assert_not_called()
        partners.save_customer.assert_not_called()
        partners.save_supplier.assert_not_called()
        database.transaction.assert_not_called()

    def test_pdf_import_creates_in_memory_invoice_without_repository_writes(self):
        extraction = extraction_with(
            "Rechnungsnummer: PDF-101\nRechnungsdatum: 08.10.2026\n"
            "Kundenname: Importkunde GmbH"
        )
        service, database, invoices, partners, _master_data = self._service(
            extraction
        )

        imported = service.load_from_pdf("rechnung.pdf")

        self.assertIs(imported.extraction, extraction)
        self.assertEqual(imported.invoice.info.invoice_number, "PDF-101")
        self.assertEqual(imported.invoice.buyer.name, "Importkunde GmbH")
        self.assertEqual(imported.invoice.seller.name, "Eigener Betrieb")
        invoices.save.assert_not_called()
        partners.save_customer.assert_not_called()
        partners.save_supplier.assert_not_called()
        database.transaction.assert_not_called()

    def test_roundtrips_program_sample_invoice_from_pdf_without_database_writes(self):
        original = create_sample_invoice()
        database = Mock()
        invoices = Mock()
        partners = Mock()
        master_data = Mock()
        service = InvoiceApplicationService(
            database=database,
            invoice_repository=invoices,
            business_partner_repository=partners,
            master_data_repository=master_data,
            invoice_factory=InvoiceFactory(),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "testrechnung.pdf"
            create_pdf(original, path)
            imported = service.load_from_pdf(path)

        self.assertEqual(imported.invoice.to_dict(), original.to_dict())
        self.assertEqual(len(imported.invoice.items), 4)
        self.assertIsNotNone(imported.draft.embedded_invoice_data)
        master_data.load_into.assert_not_called()
        invoices.save.assert_not_called()
        partners.save_customer.assert_not_called()
        partners.save_supplier.assert_not_called()
        database.transaction.assert_not_called()

if __name__ == "__main__":
    unittest.main()
