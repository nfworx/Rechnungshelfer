import unittest
from pathlib import Path
from unittest.mock import Mock

from rechnungshelfer.application.invoice_service import InvoiceApplicationService
from rechnungshelfer.domain.invoice_factory import InvoiceFactory
from rechnungshelfer.domain.models import DocumentType, Payment, Seller
from rechnungshelfer.services.pdf_import_service import (
    ExtractionMethod,
    PdfImportResult,
    PdfPageResult,
    PdfTextBlock,
)
from rechnungshelfer.services.pdf_invoice_parser import (
    BUSINESS_PARTNER_NUMBER_PATH,
    PdfInvoiceParser,
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
    def test_uses_word_coordinates_to_join_label_and_value(self):
        blocks = (
            PdfTextBlock("Kreditor-Nr.:", 40, 700, 130, 715, ExtractionMethod.OCR),
            PdfTextBlock("51285", 145, 700, 190, 715, ExtractionMethod.OCR),
        )
        extraction = PdfImportResult(
            source_file=Path("gutschrift.pdf"),
            page_count=1,
            pages=(PdfPageResult(
                page_number=1,
                text="Gutschrift",
                method=ExtractionMethod.OCR,
                blocks=blocks,
            ),),
        )

        draft = PdfInvoiceParser().parse(extraction)

        self.assertEqual(draft.get(BUSINESS_PARTNER_NUMBER_PATH).value, "51285")
        self.assertEqual(draft.get(BUSINESS_PARTNER_NUMBER_PATH).confidence, 0.95)

    def test_recovers_fields_from_noisy_self_billed_ocr(self):
        draft = PdfInvoiceParser().parse(
            extraction_with(
                """MUSTERFIRMA
Herr Kuulitse-Njr: 51285
Luisa Lieferantin Steuer-Nr : 123123123123123
SAMMEL - FINAL - GUTSCHRIFT
Nr.:40130 vom 30.11.2025
Lieferschein-Nr.: 3076/RW vom 14.08.2025
Lieferschein-Nr.: 3078/RW vom 15.08.2025
BIC: GENODESISHA
"""
            )
        )

        self.assertEqual(draft.document_type, DocumentType.SELF_BILLED_INVOICE)
        self.assertEqual(draft.get("info.invoice_number").value, "40130")
        self.assertEqual(draft.get("info.invoice_date").value, "30.11.2025")
        self.assertEqual(draft.get(BUSINESS_PARTNER_NUMBER_PATH).value, "51285")
        self.assertLess(draft.get(BUSINESS_PARTNER_NUMBER_PATH).confidence, 0.80)
        self.assertEqual(draft.get("seller.tax_number").value, "123123123123123")
        self.assertEqual(draft.get("info.delivery_note").value, "3076/RW")
        self.assertIsNone(draft.get("payment.bic"))
        self.assertTrue(any("stark fehlerhaften" in warning for warning in draft.warnings))
        self.assertTrue(any("Mehrere Lieferscheine" in warning for warning in draft.warnings))

        invoice = InvoiceFactory().create(DocumentType.SELF_BILLED_INVOICE)
        PdfInvoiceParser.apply(draft, invoice)
        self.assertEqual(invoice.seller.supplier_number, "51285")
        self.assertEqual(invoice.seller.tax_number, "123123123123123")

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
        customers = Mock()
        suppliers = Mock()
        master_data = Mock()
        master_data.load_into.return_value = (
            Seller(name="Eigener Betrieb"),
            Payment(account_holder="Eigener Betrieb"),
        )
        service = InvoiceApplicationService(
            database=database,
            invoice_repository=invoices,
            customer_repository=customers,
            supplier_repository=suppliers,
            master_data_repository=master_data,
            invoice_factory=InvoiceFactory(),
            pdf_import_service=pdf_import,
            pdf_invoice_parser=PdfInvoiceParser(),
        )
        return service, database, invoices, customers, suppliers, master_data

    def test_background_analysis_does_not_access_repositories_or_master_data(self):
        extraction = extraction_with(
            "Gutschrift\nGutschriftsnummer: GS-2026-1\nLieferant: Beispielhof"
        )
        service, database, invoices, customers, suppliers, master_data = self._service(
            extraction
        )

        analysis = service.analyze_pdf("gutschrift.pdf")

        self.assertEqual(analysis.draft.document_type, DocumentType.SELF_BILLED_INVOICE)
        master_data.load_into.assert_not_called()
        suppliers.next_supplier_number.assert_not_called()
        invoices.save.assert_not_called()
        customers.save.assert_not_called()
        suppliers.save.assert_not_called()
        database.transaction.assert_not_called()

    def test_pdf_import_creates_in_memory_invoice_without_repository_writes(self):
        extraction = extraction_with(
            "Rechnungsnummer: PDF-101\nRechnungsdatum: 08.10.2026\n"
            "Kundenname: Importkunde GmbH"
        )
        service, database, invoices, customers, suppliers, _master_data = self._service(
            extraction
        )

        imported = service.load_from_pdf("rechnung.pdf")

        self.assertIs(imported.extraction, extraction)
        self.assertEqual(imported.invoice.info.invoice_number, "PDF-101")
        self.assertEqual(imported.invoice.buyer.name, "Importkunde GmbH")
        self.assertEqual(imported.invoice.seller.name, "Eigener Betrieb")
        invoices.save.assert_not_called()
        customers.save.assert_not_called()
        suppliers.save.assert_not_called()
        database.transaction.assert_not_called()


if __name__ == "__main__":
    unittest.main()
