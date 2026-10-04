import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

from rechnungshelfer.domain.models import (
    Buyer,
    Delivery,
    DocumentType,
    Invoice,
    InvoiceInfo,
    InvoiceItem,
    Payment,
    Seller,
)
from rechnungshelfer.repositories.invoice_repository import InvoiceRepository
from rechnungshelfer.repositories.supplier_repository import SupplierRepository
from rechnungshelfer.services.pdf_service import (
    _pdf_detail_layout,
    _pdf_invoice_details,
    _pdf_parties,
    create_pdf,
)
from rechnungshelfer.services.validation_service import validate_totals, validate_xsd
from rechnungshelfer.services.xml_reader import read_xml_file
from rechnungshelfer.services.xml_service import create_xml


class SelfBilledInvoiceTests(unittest.TestCase):
    def create_invoice(self):
        seller = Seller(
            name="Landwirt Test",
            street="Feldweg 1",
            postcode="12345",
            city="Dorf",
            country="DE",
            phone="0123456789",
            email="landwirt@example.de",
            vat="",
            tax_number="12/345/67890",
            registry_number="",
            contact_name="",
            supplier_number="L0001",
        )
        buyer = Buyer(
            name="Mein Betrieb GmbH",
            street="Betriebsweg 2",
            postcode="54321",
            city="Stadt",
            country="DE",
            leitweg_id="991-TEST-01",
            email="betrieb@example.de",
            contact_name="Einkauf",
            phone="0123456789",
            vat="DE123456789",
            tax_number="98/765/43210",
        )
        payment = Payment(
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
            account_holder="Landwirt Test",
            payment_terms="Auszahlung bis 16.10.2026",
        )
        item = InvoiceItem(
            pos=1,
            name="Weizen",
            qty="10",
            unit="TNE",
            price_without_discount="200",
            vat="7.8",
        )
        invoice = Invoice(
            seller=seller,
            buyer=buyer,
            delivery=Delivery(),
            info=InvoiceInfo(
                invoice_number="GS-TEST-1",
                invoice_date="02.10.2026",
                delivery_date="01.10.2026",
                payment_due_date="16.10.2026",
                invoice_type_code="389",
            ),
            payment=payment,
            items=[item],
            document_type=DocumentType.SELF_BILLED_INVOICE,
        )
        invoice.calculate(force=True)
        return invoice

    def test_reference_calculation(self):
        invoice = self.create_invoice()
        self.assertEqual(invoice.monetarytotal.line_extension_amount, Decimal("2000.00"))
        self.assertEqual(invoice.taxtotal[0].amount, Decimal("156.00"))
        self.assertEqual(invoice.monetarytotal.payable_amount, Decimal("2156.00"))
        self.assertEqual(validate_totals(invoice).warnings, [])

    def test_legacy_invoice_defaults_to_invoice(self):
        data = self.create_invoice().to_dict()
        data.pop("document_type")
        data["info"]["invoice_type_code"] = "380"
        loaded = Invoice.from_dict(data)
        self.assertEqual(loaded.document_type, DocumentType.INVOICE)
        self.assertEqual(loaded.info.invoice_type_code, "380")

    def test_json_roundtrip_preserves_document_type(self):
        loaded = Invoice.from_dict(self.create_invoice().to_dict())
        self.assertEqual(loaded.document_type, DocumentType.SELF_BILLED_INVOICE)
        self.assertEqual(loaded.info.invoice_type_code, "389")
        self.assertEqual(loaded.items[0].vat, Decimal("7.8"))

    def test_xml_uses_invoice_389_and_correct_roles(self):
        invoice = self.create_invoice()
        xml = create_xml(invoice)
        self.assertEqual(validate_xsd(xml).errors, [])
        root = ET.fromstring(xml)
        ns = {
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        }
        self.assertEqual(root.findtext("cbc:InvoiceTypeCode", namespaces=ns), "389")
        self.assertEqual(
            root.findtext(
                "cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
                namespaces=ns,
            ),
            "Landwirt Test",
        )
        self.assertEqual(
            root.findtext(
                "cac:AccountingCustomerParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
                namespaces=ns,
            ),
            "Mein Betrieb GmbH",
        )
        self.assertIn(b"<cbc:Percent>7.8</cbc:Percent>", xml)

    def test_xml_import_restores_self_billing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gutschrift.xml"
            path.write_bytes(create_xml(self.create_invoice()))
            loaded = read_xml_file(path)
        self.assertTrue(loaded.is_self_billed)
        self.assertEqual(loaded.seller.name, "Landwirt Test")
        self.assertEqual(loaded.buyer.name, "Mein Betrieb GmbH")
        self.assertEqual(loaded.payment.iban, "DE89370400440532013000")

    def test_invoice_and_supplier_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "test.db"
            invoice_repo = InvoiceRepository(db_path)
            supplier_repo = SupplierRepository(db_path)
            invoice = self.create_invoice()
            invoice_repo.save(invoice)
            supplier_repo.save(invoice.seller, invoice.payment)
            loaded = invoice_repo.load(invoice.info.invoice_number)
            suppliers = supplier_repo.list_suppliers()
            invoice_repo.close()
            supplier_repo.close()
        self.assertTrue(loaded.is_self_billed)
        self.assertEqual(suppliers[0][0].supplier_number, "L0001")
        self.assertEqual(suppliers[0][1].iban, "DE89370400440532013000")

    def test_pdf_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gutschrift.pdf"
            create_pdf(self.create_invoice(), path)
            self.assertGreater(path.stat().st_size, 1000)

    def test_pdf_is_addressed_to_supplier(self):
        invoice = self.create_invoice()
        issuer, recipient = _pdf_parties(invoice)

        self.assertIs(issuer, invoice.buyer)
        self.assertIs(recipient, invoice.seller)
        self.assertEqual(recipient.name, "Landwirt Test")
        self.assertEqual(recipient.street, "Feldweg 1")

    def test_pdf_omits_buyer_reference_and_labels_payout_date(self):
        details = _pdf_invoice_details(self.create_invoice())
        labels = [label for label, _ in details]

        self.assertNotIn("Leitweg-ID:", labels)
        self.assertNotIn("Käuferreferenz:", labels)
        self.assertIn("Auszahlungsdatum:", labels)
        self.assertNotIn("Zahlungsziel:", labels)

    def test_pdf_detail_columns_stay_inside_available_width(self):
        frame_width = 170
        layout = _pdf_detail_layout(frame_width)

        self.assertAlmostEqual(sum(layout["outer"]), frame_width)
        self.assertAlmostEqual(sum(layout["invoice"]), layout["outer"][0])
        self.assertAlmostEqual(sum(layout["delivery"]), layout["outer"][2])


if __name__ == "__main__":
    unittest.main()
