import copy
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from lxml import etree

from rechnungshelfer.controller import InvoiceController
from rechnungshelfer.application.errors import CustomerDuplicateError
from rechnungshelfer.domain.models import Buyer, DEFAULT_BUYER_REFERENCE, Payment, Seller
from rechnungshelfer.gui.export_workflow import ExportWorkflow
from rechnungshelfer.gui.main_window import InvoiceGUI
from rechnungshelfer.repositories.business_partner_repository import (
    BusinessPartnerRepository,
)
from rechnungshelfer.repositories.database import Database
from rechnungshelfer.repositories.invoice_repository import (
    InvoiceRepository,
    get_data_dir,
    get_exe_dir,
)
from app_info import DATA_DIR_ENV
from rechnungshelfer.repositories.master_data_repository import MasterDataRepository
from rechnungshelfer.services.format_service import parse_de
from rechnungshelfer.services.validation_service import validate_document, validate_xsd
from rechnungshelfer.services.xml_service import create_xml
from rechnungshelfer.services import (
    kosit_validation_service,
    pdf_service,
    update_service,
    validation_service,
)
from tests import test_gutschrift as gutschrift_fixtures


class RegressionTests(unittest.TestCase):
    @staticmethod
    def _invoice():
        return gutschrift_fixtures.SelfBilledInvoiceTests().create_invoice()

    def _controller_for(self, directory: Path) -> InvoiceController:
        controller = InvoiceController.__new__(InvoiceController)
        controller.database = Database(directory / "audit.db")
        controller.repo = InvoiceRepository(connection=controller.database.connection)
        controller.partner_repo = BusinessPartnerRepository(
            connection=controller.database.connection
        )
        controller.master_data_repository = MasterDataRepository(directory / "master.json")
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
            invoice.buyer.customer_number = "2002"

            existing = copy.deepcopy(invoice.buyer)
            existing.customer_number = "2001"
            controller.partner_repo.save_customer(existing)

            try:
                with self.assertRaises(CustomerDuplicateError) as raised:
                    controller.save_invoice(invoice)

                self.assertEqual(
                    [buyer.customer_number for buyer in raised.exception.duplicates],
                    ["2001"],
                )
                self.assertFalse(controller.repo.exists("DUP-1"))
            finally:
                controller.close()

    def test_gui_handles_typed_customer_duplicate_error(self):
        invoice = self._invoice()
        duplicate = copy.deepcopy(invoice.buyer)
        duplicate.customer_number = "2001"
        controller = MagicMock()
        controller.invoice_exists.return_value = False
        controller.save_invoice.side_effect = [
            CustomerDuplicateError([duplicate]),
            None,
        ]
        gui = InvoiceGUI.__new__(InvoiceGUI)
        gui.invoice = invoice
        gui.controller = controller

        with (
            patch(
                "rechnungshelfer.gui.main_window.messagebox.askyesno",
                return_value=True,
            ) as ask,
            patch("rechnungshelfer.gui.main_window.messagebox.showinfo"),
        ):
            gui.save_invoice()

        self.assertIn("2001", ask.call_args.args[1])
        self.assertEqual(controller.save_invoice.call_count, 2)
        controller.save_invoice.assert_called_with(
            invoice,
            allow_customer_duplicate=True,
        )

    def test_gui_startup_loads_latest_invoice(self):
        gui = InvoiceGUI.__new__(InvoiceGUI)
        gui.controller = MagicMock()
        gui.root = MagicMock()
        gui.on_ready = MagicMock()
        gui.load_latest_invoice = MagicMock()

        with patch.object(__import__("sys"), "frozen", False, create=True):
            gui._do_startup_tasks()

        gui.load_latest_invoice.assert_called_once_with()
        gui.on_ready.assert_called_once_with()

    def test_supplier_and_invoice_are_rolled_back_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self._controller_for(Path(tmp))
            invoice = self._invoice()

            with patch.object(controller.repo, "save", side_effect=RuntimeError("DB error")):
                with self.assertRaisesRegex(RuntimeError, "DB error"):
                    controller.save_invoice(invoice)

            self.assertEqual(controller.partner_repo.list_suppliers(), [])
            controller.close()

    def test_saving_old_invoice_does_not_overwrite_customer_master_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self._controller_for(Path(tmp))
            invoice = self._invoice()
            invoice.set_document_type("invoice")
            invoice.info.invoice_number = "OLD-CUSTOMER-1"
            invoice.buyer.customer_number = "2001"
            invoice.buyer.name = "Alter Kundenname"
            invoice.buyer.city = "Altdorf"
            current = copy.deepcopy(invoice.buyer)
            current.name = "Aktueller Kundenname"
            current.city = "Neustadt"
            controller.partner_repo.save_customer(current)

            controller.save_invoice(invoice)

            loaded = controller.partner_repo.load_partner("2001")
            self.assertEqual(loaded.buyer.name, "Aktueller Kundenname")
            self.assertEqual(loaded.buyer.city, "Neustadt")
            controller.close()

    def test_saving_old_credit_note_does_not_overwrite_supplier_master_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self._controller_for(Path(tmp))
            invoice = self._invoice()
            invoice.info.invoice_number = "OLD-SUPPLIER-1"
            invoice.seller.supplier_number = "2001"
            invoice.seller.name = "Alter Hof"
            invoice.seller.city = "Altdorf"
            invoice.payment.iban = "DE12500105170648489890"
            current = copy.deepcopy(invoice.seller)
            current.name = "Aktueller Hof"
            current.city = "Neustadt"
            current_payment = copy.deepcopy(invoice.payment)
            current_payment.iban = "DE89370400440532013000"
            controller.partner_repo.save_supplier(current, current_payment)

            controller.save_invoice(invoice)

            loaded = controller.partner_repo.load_partner("2001")
            self.assertEqual(loaded.seller.name, "Aktueller Hof")
            self.assertEqual(loaded.seller.city, "Neustadt")
            self.assertEqual(loaded.payment.iban, "DE89370400440532013000")
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

    def test_delivery_toggle_synchronizes_address_and_required_fields(self):
        invoice = self._invoice()
        invoice.buyer.name = "Beispielkunde GmbH"
        invoice.buyer.street = "Kundenweg 12"
        invoice.buyer.postcode = "28195"
        invoice.buyer.city = "Bremen"
        invoice.buyer.country = "DE"

        invoice.set_use_invoice_address_as_delivery(True)

        self.assertTrue(invoice.buyer.use_invoice_address_as_delivery)
        self.assertEqual(invoice.delivery.name, "Beispielkunde GmbH")
        self.assertEqual(invoice.delivery.street, "Kundenweg 12")
        self.assertEqual(invoice.delivery.postcode, "28195")
        self.assertEqual(invoice.delivery.city, "Bremen")
        self.assertEqual(invoice.delivery.country, "")
        self.assertEqual(invoice.delivery.required_fields, [])

        invoice.set_use_invoice_address_as_delivery(False)

        self.assertFalse(invoice.buyer.use_invoice_address_as_delivery)
        self.assertEqual(
            invoice.delivery.required_fields,
            ["name", "street", "postcode", "city", "country"],
        )
        self.assertEqual(invoice.delivery.country, "DE")

    def test_replacing_buyer_synchronizes_shared_delivery_address(self):
        invoice = self._invoice()
        buyer = Buyer(
            name="Neukunde AG",
            street="Marktplatz 3",
            postcode="20095",
            city="Hamburg",
            country="DE",
            use_invoice_address_as_delivery=True,
        )

        invoice.replace_buyer(buyer)

        self.assertIs(invoice.buyer, buyer)
        self.assertEqual(invoice.delivery.name, "Neukunde AG")
        self.assertEqual(invoice.delivery.street, "Marktplatz 3")
        self.assertEqual(invoice.delivery.postcode, "20095")
        self.assertEqual(invoice.delivery.city, "Hamburg")
        self.assertEqual(invoice.delivery.country, "DE")
        self.assertEqual(invoice.delivery.required_fields, [])

    def test_export_workflow_uses_the_current_invoice(self):
        controller = MagicMock()
        first_invoice = self._invoice()
        current_invoice = [first_invoice]
        workflow = ExportWorkflow(
            root=MagicMock(),
            controller=controller,
            invoice_provider=lambda: current_invoice[0],
        )
        controller.check_pdf_required_fields.return_value = True

        self.assertTrue(workflow.can_export_pdf())
        controller.check_pdf_required_fields.assert_called_once_with(first_invoice)

        second_invoice = copy.deepcopy(first_invoice)
        current_invoice[0] = second_invoice
        controller.get_missing_required_fields.return_value = []

        self.assertEqual(workflow.xml_export_hint(), "")
        controller.get_missing_required_fields.assert_called_once_with(
            second_invoice,
            for_xml=True,
        )

    def test_export_workflow_delegates_pdf_export(self):
        invoice = self._invoice()
        controller = MagicMock()
        workflow = ExportWorkflow(
            root=MagicMock(),
            controller=controller,
            invoice_provider=lambda: invoice,
        )

        with (
            patch(
                "rechnungshelfer.gui.export_workflow.filedialog.asksaveasfilename",
                return_value="rechnung.pdf",
            ),
            patch(
                "rechnungshelfer.gui.export_workflow.messagebox.showinfo"
            ) as showinfo,
        ):
            workflow.generate_pdf()

        controller.generate_pdf.assert_called_once_with(invoice, "rechnung.pdf")
        showinfo.assert_called_once_with("Export", "PDF wurde erstellt.")

    def test_export_workflow_closes_progress_after_xml_input_error(self):
        invoice = self._invoice()
        controller = MagicMock()
        controller.generate_xml.side_effect = ValueError("Pflichtfeld fehlt")
        root = MagicMock()
        root.after.side_effect = lambda _delay, callback: callback()
        progress = MagicMock()
        progress.winfo_exists.return_value = True
        workflow = ExportWorkflow(
            root=root,
            controller=controller,
            invoice_provider=lambda: invoice,
        )

        with patch(
            "rechnungshelfer.gui.export_workflow.messagebox.showwarning"
        ) as showwarning:
            workflow._export_xml(progress, "rechnung.xml")

        controller.generate_xml.assert_called_once_with(invoice, "rechnung.xml")
        progress.destroy.assert_called_once_with()
        showwarning.assert_called_once_with(
            "Export abgebrochen",
            "Pflichtfeld fehlt",
        )

    def test_export_workflow_uses_validation_result_returned_by_export(self):
        invoice = self._invoice()
        validation_result = MagicMock()
        export_result = MagicMock(validation_result=validation_result)
        controller = MagicMock()
        controller.generate_xml.return_value = export_result
        root = MagicMock()
        root.after.side_effect = lambda _delay, callback: callback()
        progress = MagicMock()
        workflow = ExportWorkflow(
            root=root,
            controller=controller,
            invoice_provider=lambda: invoice,
        )

        with patch.object(workflow, "_finish_xml_export_success") as finish:
            workflow._export_xml(progress, "rechnung.xml")

        finish.assert_called_once_with(progress, validation_result)

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

    def test_missing_self_billed_supplier_number_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self._controller_for(Path(tmp))
            invoice = self._invoice()
            invoice.buyer.use_invoice_address_as_delivery = True
            invoice.seller.supplier_number = ""
            invoice.seller.registry_number = ""
            invoice.seller.vat = ""

            self.assertFalse(controller.check_xml_required_fields(invoice))
            self.assertEqual(invoice.seller.supplier_number, "")
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
                "rechnungshelfer.repositories.invoice_repository.json.loads",
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
            buyer.customer_number = "0001"
            buyer.city = "Hamburg"
            controller.partner_repo.save_customer(buyer)

            results = controller.partner_repo.search_customers("city", "Hamb", limit=1)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].customer_number, "0001")
            self.assertEqual(
                controller.partner_repo.search_customers("unknown", "x"),
                [],
            )
            controller.close()

    def test_data_directory_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {DATA_DIR_ENV: tmp}):
                self.assertEqual(get_data_dir(), Path(tmp))

    def test_development_data_directory_stays_below_project_root(self):
        project_root = Path(__file__).resolve().parents[1]

        with patch.object(__import__("sys"), "frozen", False, create=True):
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(get_exe_dir(), project_root)

    def test_service_resources_stay_below_project_root(self):
        project_root = Path(__file__).resolve().parents[1]

        with patch.object(__import__("sys"), "frozen", False, create=True):
            self.assertEqual(
                Path(pdf_service.resource_path("assets")),
                project_root / "assets",
            )
            self.assertEqual(validation_service.get_base_dir(), project_root)
            self.assertEqual(kosit_validation_service.get_base_dir(), project_root)
            self.assertEqual(update_service.application_install_root(), project_root)

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
