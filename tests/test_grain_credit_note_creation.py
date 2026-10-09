import unittest
from types import SimpleNamespace

from rechnungshelfer.application.grain_credit_note_mapper import (
    grain_credit_note_creation_issues,
)
from rechnungshelfer.domain.invoice_factory import InvoiceFactory
from rechnungshelfer.domain.models import DocumentType


class GrainCreditNoteCreationIssueTests(unittest.TestCase):
    def setUp(self):
        self.document = InvoiceFactory().create(DocumentType.SELF_BILLED_INVOICE)
        self.document.info.invoice_number = "91001"
        seller_values = {
            "supplier_number": "1001",
            "name": "Musterhof Testlieferant",
            "street": "Feldweg 12",
            "postcode": "54321",
            "city": "Musterdorf",
            "country": "DE",
            "phone": "+49 9876 543210",
            "email": "musterlieferant@example.de",
            "vat": "DE987654321",
            "tax_number": "12/345/67890",
            "registry_number": "HRA 12345",
            "contact_name": "Erika Muster",
            "buyer_reference": "1001",
        }
        for field, value in seller_values.items():
            setattr(self.document.seller, field, value)
        self.document.payment.iban = "DE89370400440532013000"
        self.document.payment.bic = "TESTDEFFXXX"
        self.document.payment.account_holder = "Musterhof Testlieferant"
        self.document.payment.payment_terms = "Auszahlung innerhalb von 14 Tagen."
        self.deliveries = (object(),)
        self.result = SimpleNamespace(delivery_results=(object(),))

    def test_complete_document_can_be_created(self):
        issues = grain_credit_note_creation_issues(
            self.document,
            self.deliveries,
            self.result,
            "7,8 %",
        )

        self.assertEqual(issues, ())

    def test_reports_concrete_missing_fields_and_calculation(self):
        self.document.seller.name = ""
        self.document.payment.iban = ""

        issues = grain_credit_note_creation_issues(
            self.document,
            self.deliveries,
            None,
            "— auswählen —",
        )

        self.assertIn("Name fehlt.", issues)
        self.assertIn("IBAN fehlt.", issues)
        self.assertIn("Die Lieferungen sind noch nicht erfolgreich berechnet.", issues)
        self.assertIn("Steuersatz fehlt oder ist ungueltig.", issues)


if __name__ == "__main__":
    unittest.main()
