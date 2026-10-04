import unittest
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app_info import DATA_DIR_ENV
from rechnungshelfer.controller import InvoiceController
from rechnungshelfer.domain.invoice_factory import InvoiceFactory
from rechnungshelfer.domain.models import (
    DEFAULT_BUYER_REFERENCE,
    DocumentType,
    Payment,
    Seller,
)


class InvoiceFactoryTests(unittest.TestCase):
    def setUp(self):
        self.factory = InvoiceFactory(today_provider=lambda: date(2026, 10, 5))
        self.own_company = Seller(
            name="Eigene Firma",
            street="Hauptstraße 1",
            postcode="12345",
            city="Berlin",
            email="rechnung@example.de",
            buyer_reference="EINKAUF",
        )
        self.own_payment = Payment(
            iban="DE02120300000000202051",
            bic="BYLADEM1001",
            account_holder="Eigene Firma",
        )

    def test_regular_invoice_uses_independent_copies_of_master_data(self):
        invoice = self.factory.create(
            DocumentType.INVOICE,
            own_company=self.own_company,
            own_payment=self.own_payment,
        )

        self.assertEqual(invoice.seller.name, "Eigene Firma")
        self.assertEqual(invoice.payment.iban, "DE02120300000000202051")
        self.assertEqual(invoice.info.invoice_type_code, "380")
        invoice.seller.name = "Geändert"
        self.assertEqual(self.own_company.name, "Eigene Firma")

    def test_self_billed_invoice_maps_own_company_to_buyer(self):
        invoice = self.factory.create(
            DocumentType.SELF_BILLED_INVOICE,
            own_company=self.own_company,
            own_payment=self.own_payment,
            supplier_number="L0042",
        )

        self.assertTrue(invoice.is_self_billed)
        self.assertEqual(invoice.info.invoice_type_code, "389")
        self.assertEqual(invoice.buyer.name, "Eigene Firma")
        self.assertEqual(invoice.buyer.leitweg_id, "EINKAUF")
        self.assertEqual(invoice.delivery.street, "Hauptstraße 1")
        self.assertEqual(invoice.seller.supplier_number, "L0042")
        self.assertEqual(invoice.seller.name, "")
        self.assertEqual(invoice.payment.iban, "")
        self.assertIn("iban", invoice.payment.required_fields)

    def test_copy_resets_identity_and_dates_without_changing_original(self):
        original = self.factory.create(own_company=self.own_company)
        original.info.invoice_number = "RE-17"
        original.info.invoice_date = "01.01.2025"
        original.info.delivery_date = "02.01.2025"
        original.items[0].price_without_discount = Decimal("10.00")

        copied = self.factory.copy(original)

        self.assertEqual(copied.info.invoice_number, "")
        self.assertEqual(copied.info.invoice_date, "05.10.2026")
        self.assertEqual(copied.info.delivery_date, "")
        self.assertEqual(copied.info.payment_due_date, "19.10.2026")
        self.assertEqual(copied.items[0].net, Decimal("10.00"))
        self.assertEqual(original.info.invoice_number, "RE-17")
        self.assertEqual(original.info.invoice_date, "01.01.2025")

    def test_seller_to_buyer_uses_default_reference_for_blank_legacy_data(self):
        buyer = self.factory.seller_to_buyer(Seller(buyer_reference=""))
        self.assertEqual(buyer.leitweg_id, DEFAULT_BUYER_REFERENCE)

    def test_controller_uses_master_data_and_supplier_number_for_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {DATA_DIR_ENV: str(Path(tmp) / "data")}):
                controller = InvoiceController()
                try:
                    controller.master_data_repository.save(
                        self.own_company,
                        self.own_payment,
                    )
                    invoice = controller.create_empty_invoice(
                        DocumentType.SELF_BILLED_INVOICE
                    )
                finally:
                    controller.close()

        self.assertEqual(invoice.buyer.name, "Eigene Firma")
        self.assertRegex(invoice.seller.supplier_number, r"^L\d{4}$")


if __name__ == "__main__":
    unittest.main()
