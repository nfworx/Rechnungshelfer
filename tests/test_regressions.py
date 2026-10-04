import copy
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from lxml import etree

from controller import InvoiceController
from models import DEFAULT_BUYER_REFERENCE, Payment, Seller
from repositories.customer_repository import CustomerRepository
from repositories.invoice_repository import InvoiceRepository, get_data_dir
from app_info import DATA_DIR_ENV
from repositories.master_data_repository import MasterDataRepository
from repositories.supplier_repository import SupplierRepository
from services.format_service import parse_de
from services.validation_service import validate_document, validate_xsd
from services.xml_service import create_xml
from tests import test_gutschrift as gutschrift_fixtures


class RegressionTests(unittest.TestCase):
    @staticmethod
    def _invoice():
        return gutschrift_fixtures.SelfBilledInvoiceTests().create_invoice()

    def _controller_for(self, directory: Path) -> InvoiceController:
        controller = InvoiceController.__new__(InvoiceController)
        controller.repo = InvoiceRepository(directory / "audit.db")
        controller.customer_repo = CustomerRepository(connection=controller.repo.conn)
        controller.supplier_repo = SupplierRepository(connection=controller.repo.conn)
        controller.master_data_repository = MasterDataRepository(directory / "master.json")
        controller.last_validation_result = None
        return controller

    def test_invalid_number_is_not_silently_converted_to_zero(self):
        with self.assertRaises(ValueError):
            parse_de("abc")

    def test_buyer_reference_defaults_to_accounting(self):
        self.assertEqual(Seller().buyer_reference, DEFAULT_BUYER_REFERENCE)
        buyer = InvoiceController._seller_to_buyer(Seller(buyer_reference=""))
        self.assertEqual(buyer.leitweg_id, DEFAULT_BUYER_REFERENCE)

    def test_blank_legacy_buyer_reference_is_upgraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = MasterDataRepository(Path(tmp) / "master.json")
            repository.save(Seller(buyer_reference=""), Payment())

            seller, _ = repository.load_into(Seller(), Payment())

            self.assertEqual(seller.buyer_reference, DEFAULT_BUYER_REFERENCE)

    def test_legacy_placeholder_master_data_is_upgraded_to_useful_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = MasterDataRepository(Path(tmp) / "master.json")
            repository.save(
                Seller(
                    name="Musterfirma",
                    street="Musterstraße 10",
                    postcode="XXXXX",
                    city="Musterstadt",
                    phone="XXXXXXXX",
                    email="info@musterfirma.de",
                    vat="XXXXXXX",
                ),
                Payment(
                    iban="XXXXXXXXXX",
                    bic="XXXXXXXX",
                    account_holder="Musterfirma",
                ),
            )

            seller, payment = repository.load_into(Seller(), Payment())

            self.assertEqual(seller.name, "Musterfirma")
            self.assertEqual(seller.street, "Musterstraße 10")
            self.assertEqual(seller.postcode, "12345")
            self.assertEqual(seller.city, "Musterhausen")
            self.assertEqual(seller.email, "info@musterfirma.de")
            self.assertEqual(payment.iban, "DE89370400440532013000")
            self.assertEqual(payment.bic, "COBADEFFXXX")
            self.assertEqual(payment.account_holder, "Musterfirma")

    def test_duplicate_customer_does_not_persist_invoice(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self._controller_for(Path(tmp))
            invoice = self._invoice()
            invoice.set_document_type("invoice")
            invoice.info.invoice_number = "DUP-1"
            invoice.buyer.customer_number = "K-NEW"

            existing = copy.deepcopy(invoice.buyer)
            existing.customer_number = "K-OLD"
            controller.customer_repo.save(existing)

            with self.assertRaisesRegex(ValueError, "CUSTOMER_DUPLICATE_FOUND"):
                controller.save_invoice(invoice)

            self.assertFalse(controller.repo.exists("DUP-1"))
            controller.close()

    def test_supplier_and_invoice_are_rolled_back_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self._controller_for(Path(tmp))
            invoice = self._invoice()

            with patch.object(controller.repo, "save", side_effect=RuntimeError("DB error")):
                with self.assertRaisesRegex(RuntimeError, "DB error"):
                    controller.save_invoice(invoice)

            self.assertEqual(controller.supplier_repo.list_suppliers(), [])
            controller.close()

    def test_zero_vat_uses_zero_rated_category(self):
        invoice = self._invoice()
        invoice.items[0].set_vat(Decimal("0.00"))
        invoice.calculate(force=True)

        self.assertEqual(invoice.items[0].tax_category, "Z")
        self.assertEqual(invoice.taxtotal[0].tax_category, "Z")
        self.assertEqual(validate_document(invoice).errors, [])
        self.assertEqual(validate_xsd(create_xml(invoice)).errors, [])

    def test_xml_does_not_create_empty_delivery_element(self):
        invoice = self._invoice()
        invoice.info.delivery_date = ""
        invoice.buyer.use_invoice_address_as_delivery = True
        invoice.delivery.name = ""
        invoice.delivery.street = ""
        invoice.delivery.postcode = ""
        invoice.delivery.city = ""

        root = etree.fromstring(create_xml(invoice))
        deliveries = root.xpath(
            "//*[local-name()='Delivery']"
        )

        self.assertEqual(deliveries, [])

    def test_xml_precheck_reports_invalid_contact_and_payment_values(self):
        invoice = self._invoice()
        invoice.buyer.use_invoice_address_as_delivery = True
        invoice.seller.email = "123"
        invoice.seller.phone = ""
        invoice.buyer.vat = "XXXXXXX"
        invoice.payment.iban = "123"
        invoice.payment.bic = "123"
        controller = InvoiceController.__new__(InvoiceController)

        issue_fields = {
            field
            for _, _, field in controller.get_missing_required_fields(
                invoice,
                for_xml=True,
            )
        }

        self.assertTrue(
            {"email_invalid", "phone", "vat_invalid", "iban_invalid", "bic_invalid"}
            <= issue_fields
        )

    def test_missing_self_billed_supplier_number_is_assigned(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self._controller_for(Path(tmp))
            invoice = self._invoice()
            invoice.buyer.use_invoice_address_as_delivery = True
            invoice.seller.supplier_number = ""
            invoice.seller.registry_number = ""
            invoice.seller.vat = ""

            self.assertTrue(controller.check_xml_required_fields(invoice))
            self.assertRegex(invoice.seller.supplier_number, r"^L\d{4}$")
            controller.close()

    def test_zero_quantity_is_rejected(self):
        invoice = self._invoice()
        invoice.items[0].qty = Decimal("0")
        invoice.calculate(force=True)
        self.assertTrue(validate_document(invoice).errors)

    def test_buyer_reference_blocks_xml_but_not_pdf(self):
        invoice = self._invoice()
        invoice.buyer.use_invoice_address_as_delivery = True
        invoice.buyer.leitweg_id = ""
        controller = InvoiceController.__new__(InvoiceController)

        self.assertTrue(controller.check_pdf_required_fields(invoice))
        self.assertFalse(controller.check_xml_required_fields(invoice))
        message = controller.format_missing_fields(
            controller.get_missing_required_fields(invoice, for_xml=True),
            "XML",
        )
        self.assertIn("Käuferreferenz (BT-10)", message)

    def test_pdf_export_works_without_buyer_reference(self):
        invoice = self._invoice()
        invoice.buyer.use_invoice_address_as_delivery = True
        invoice.buyer.leitweg_id = ""
        controller = InvoiceController.__new__(InvoiceController)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "gutschrift.pdf"
            controller.generate_pdf(invoice, output)
            self.assertGreater(output.stat().st_size, 0)

    def test_regular_invoice_leitweg_id_is_only_required_for_xml(self):
        invoice = self._invoice()
        invoice.set_document_type("invoice")
        invoice.buyer.use_invoice_address_as_delivery = True
        invoice.buyer.leitweg_id = ""
        invoice.seller.vat = "DE123456789"
        invoice.seller.registry_number = "HRB 123"
        invoice.seller.contact_name = "Buchhaltung"
        controller = InvoiceController.__new__(InvoiceController)

        self.assertNotIn("leitweg_id", invoice.buyer.required_fields)
        self.assertTrue(controller.check_pdf_required_fields(invoice))
        self.assertFalse(controller.check_xml_required_fields(invoice))

    def test_existing_database_is_backed_up_before_first_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            connection = sqlite3.connect(db_path)
            connection.execute("CREATE TABLE legacy (value TEXT)")
            connection.execute("INSERT INTO legacy VALUES ('kept')")
            connection.commit()
            connection.close()

            repository = InvoiceRepository(db_path)
            backups = list(Path(tmp).glob("legacy.backup-v0-*.db"))
            repository.close()

            self.assertEqual(len(backups), 1)
            backup = sqlite3.connect(backups[0])
            try:
                self.assertEqual(backup.execute("SELECT value FROM legacy").fetchone()[0], "kept")
            finally:
                backup.close()

    def test_invoice_list_uses_summary_columns_without_parsing_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = InvoiceRepository(Path(tmp) / "summaries.db")
            invoice = self._invoice()
            repository.save(invoice)

            with patch(
                "repositories.invoice_repository.json.loads",
                side_effect=AssertionError("JSON should not be parsed"),
            ):
                summaries = repository.list_invoice_summaries()

            self.assertEqual(summaries[0]["invoice_number"], invoice.info.invoice_number)
            self.assertEqual(summaries[0]["counterparty_name"], invoice.seller.name)
            repository.close()

    def test_customer_search_is_limited_and_field_specific(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self._controller_for(Path(tmp))
            buyer = copy.deepcopy(self._invoice().buyer)
            buyer.customer_number = "K0001"
            buyer.city = "Hamburg"
            controller.customer_repo.save(buyer)

            results = controller.customer_repo.search("city", "Hamb", limit=1)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].customer_number, "K0001")
            self.assertEqual(controller.customer_repo.search("unknown", "x"), [])
            controller.close()

    def test_data_directory_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {DATA_DIR_ENV: tmp}):
                self.assertEqual(get_data_dir(), Path(tmp))

    def test_packaged_app_always_uses_portable_data_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe_dir = Path(tmp) / "Rechnungshelfer"
            exe_dir.mkdir()

            with patch.object(__import__("sys"), "frozen", True, create=True):
                with patch.object(
                    __import__("sys"),
                    "executable",
                    str(exe_dir / "Rechnungshelfer.exe"),
                ):
                    with patch.dict("os.environ", {}, clear=True):
                        data_dir = get_data_dir()

            self.assertEqual(data_dir, exe_dir / "data")
            self.assertTrue(data_dir.is_dir())

if __name__ == "__main__":
    unittest.main()
