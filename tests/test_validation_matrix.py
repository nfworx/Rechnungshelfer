import copy
import unittest
from decimal import Decimal

from lxml import etree

from rechnungshelfer.controller import InvoiceController
from rechnungshelfer.services.input_validation_service import (
    InputValidationError,
    normalize_invoice_input,
)
from rechnungshelfer.services.kosit_validation_service import (
    JAVA_EXE,
    KOSIT_JAR,
    SCENARIOS_XML,
)
from rechnungshelfer.services.validation_service import (
    validate_document,
    validate_invoice,
    validate_totals,
    validate_xsd,
)
from rechnungshelfer.services.xml_service import NSMAP, create_xml
from tests.generate_validator_fixtures import OUTPUT_DIR
from tests.validation_documents import (
    create_validator_invoice,
    create_validator_self_billed_invoice,
)


KOSIT_AVAILABLE = all(path.exists() for path in (JAVA_EXE, KOSIT_JAR, SCENARIOS_XML))
NS = {
    "ubl": NSMAP[None],
    "cbc": NSMAP["cbc"],
    "cac": NSMAP["cac"],
}


class ValidationDocumentTests(unittest.TestCase):
    def setUp(self):
        self.controller = InvoiceController.__new__(InvoiceController)

    @staticmethod
    def _field_names(missing):
        return {field for _, _, field in missing}

    def test_checked_in_xml_fixtures_are_current_and_locally_valid(self):
        documents = {
            "test-rechnung.xml": create_validator_invoice(),
            "test-gutschrift.xml": create_validator_self_billed_invoice(),
        }
        for filename, invoice in documents.items():
            with self.subTest(filename=filename):
                generated = create_xml(invoice)
                self.assertEqual((OUTPUT_DIR / filename).read_bytes(), generated)
                self.assertEqual(validate_xsd(generated).errors, [])
                self.assertEqual(validate_document(invoice).errors, [])
                self.assertEqual(validate_totals(invoice).warnings, [])
                self.assertEqual(
                    self.controller.get_missing_required_fields(invoice, for_xml=True),
                    [],
                )

    @unittest.skipUnless(KOSIT_AVAILABLE, "Portable Java/KoSIT ist nicht vorhanden")
    def test_both_reference_documents_pass_kosit(self):
        documents = (
            create_validator_invoice(),
            create_validator_self_billed_invoice(),
        )
        for invoice in documents:
            with self.subTest(document_type=invoice.document_type.value):
                result = validate_invoice(create_xml(invoice), invoice, use_kosit=True)
                self.assertTrue(result.valid, result.errors)
                self.assertEqual(result.errors, [])
                self.assertEqual(result.warnings, [])

    def test_reference_documents_cover_distinct_xml_branches(self):
        invoice_root = etree.fromstring(create_xml(create_validator_invoice()))
        self_billed_root = etree.fromstring(
            create_xml(create_validator_self_billed_invoice())
        )

        self.assertEqual(invoice_root.findtext("cbc:InvoiceTypeCode", namespaces=NS), "380")
        self.assertEqual(
            self_billed_root.findtext("cbc:InvoiceTypeCode", namespaces=NS),
            "389",
        )
        self.assertIsNotNone(invoice_root.find("cac:DespatchDocumentReference", NS))
        self.assertIsNone(invoice_root.find("cac:InvoicePeriod", NS))
        self.assertIsNotNone(invoice_root.find("cac:Delivery/cac:DeliveryLocation", NS))
        self.assertIsNotNone(self_billed_root.find("cac:InvoicePeriod", NS))
        self.assertIsNone(self_billed_root.find("cac:Delivery", NS))

        for root in (invoice_root, self_billed_root):
            self.assertEqual(len(root.findall("cac:InvoiceLine", NS)), 4)
            rates = {
                node.text
                for node in root.findall(
                    "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:Percent",
                    NS,
                )
            }
            self.assertEqual(rates, {"0", "7", "7.8", "19"})

    def test_regular_invoice_required_field_matrix(self):
        cases = [
            ("seller", "name"),
            ("seller", "street"),
            ("seller", "postcode"),
            ("seller", "city"),
            ("seller", "country"),
            ("seller", "vat"),
            ("seller", "registry_number"),
            ("seller", "email"),
            ("seller", "contact_name"),
            ("buyer", "name"),
            ("buyer", "street"),
            ("buyer", "postcode"),
            ("buyer", "city"),
            ("buyer", "country"),
            ("buyer", "email"),
            ("info", "invoice_number"),
            ("info", "invoice_date"),
            ("info", "payment_due_date"),
            ("info", "currency"),
            ("info", "customization_id"),
            ("info", "profile_id"),
            ("info", "invoice_type_code"),
            ("payment", "iban"),
            ("payment", "bic"),
            ("payment", "account_holder"),
            ("payment", "payment_means_code"),
            ("payment", "payment_terms"),
            ("delivery", "name"),
            ("delivery", "street"),
            ("delivery", "postcode"),
            ("delivery", "city"),
            ("delivery", "country"),
        ]
        for section, field in cases:
            with self.subTest(section=section, field=field):
                invoice = create_validator_invoice()
                setattr(getattr(invoice, section), field, "")
                missing = self._field_names(
                    self.controller.get_missing_required_fields(invoice, for_xml=True)
                )
                self.assertIn(field, missing)

        for field in ("name", "unit"):
            with self.subTest(section="item", field=field):
                invoice = create_validator_invoice()
                setattr(invoice.items[0], field, "")
                missing = self._field_names(
                    self.controller.get_missing_required_fields(invoice, for_xml=True)
                )
                self.assertIn(field, missing)

    def test_self_billed_required_field_matrix(self):
        cases = [
            ("seller", "name"),
            ("seller", "street"),
            ("seller", "postcode"),
            ("seller", "city"),
            ("seller", "country"),
            ("seller", "email"),
            ("buyer", "name"),
            ("buyer", "street"),
            ("buyer", "postcode"),
            ("buyer", "city"),
            ("buyer", "country"),
            ("buyer", "email"),
            ("buyer", "leitweg_id"),
            ("payment", "iban"),
            ("payment", "bic"),
            ("payment", "account_holder"),
            ("payment", "payment_means_code"),
        ]
        for section, field in cases:
            with self.subTest(section=section, field=field):
                invoice = create_validator_self_billed_invoice()
                setattr(getattr(invoice, section), field, "")
                missing = self._field_names(
                    self.controller.get_missing_required_fields(invoice, for_xml=True)
                )
                self.assertIn(field, missing)

        invoice = create_validator_self_billed_invoice()
        invoice.seller.vat = ""
        invoice.seller.tax_number = ""
        missing = self._field_names(
            self.controller.get_missing_required_fields(invoice, for_xml=True)
        )
        self.assertIn("vat_or_tax_number", missing)

    def test_xml_format_issue_matrix(self):
        cases = [
            ("seller email", lambda i: setattr(i.seller, "email", "ungueltig"), "email_invalid"),
            ("buyer email", lambda i: setattr(i.buyer, "email", "ungueltig"), "email_invalid"),
            ("seller vat", lambda i: setattr(i.seller, "vat", "123"), "vat_invalid"),
            ("buyer vat", lambda i: setattr(i.buyer, "vat", "123"), "vat_invalid"),
            ("phone missing", lambda i: setattr(i.seller, "phone", ""), "phone"),
            ("phone invalid", lambda i: setattr(i.seller, "phone", "12"), "phone_invalid"),
            ("iban", lambda i: setattr(i.payment, "iban", "DE00123"), "iban_invalid"),
            ("bic", lambda i: setattr(i.payment, "bic", "ABC"), "bic_invalid"),
        ]
        for name, mutate, expected in cases:
            with self.subTest(case=name):
                invoice = create_validator_invoice()
                mutate(invoice)
                missing = self._field_names(
                    self.controller.get_missing_required_fields(invoice, for_xml=True)
                )
                self.assertIn(expected, missing)

        invoice = create_validator_invoice()
        invoice.seller.supplier_number = ""
        invoice.seller.registry_number = ""
        invoice.seller.vat = ""
        missing = self._field_names(
            self.controller.get_missing_required_fields(invoice, for_xml=True)
        )
        self.assertIn("seller_identifier", missing)

    def test_buyer_reference_is_xml_only_and_delivery_is_conditional(self):
        invoice = create_validator_invoice()
        invoice.buyer.leitweg_id = ""
        self.assertNotIn(
            "leitweg_id",
            self._field_names(
                self.controller.get_missing_required_fields(invoice, for_xml=False)
            ),
        )
        self.assertIn(
            "leitweg_id",
            self._field_names(
                self.controller.get_missing_required_fields(invoice, for_xml=True)
            ),
        )

        invoice = create_validator_invoice()
        invoice.buyer.use_invoice_address_as_delivery = True
        invoice.delivery.street = ""
        self.assertNotIn(
            "street",
            self._field_names(
                self.controller.get_missing_required_fields(invoice, for_xml=True)
            ),
        )

    def test_date_validation_matrix(self):
        for field in ("invoice_date", "payment_due_date"):
            for value in ("", "31.02.2026", "kein Datum"):
                with self.subTest(field=field, value=value):
                    invoice = create_validator_invoice()
                    setattr(invoice.info, field, value)
                    with self.assertRaises(InputValidationError):
                        normalize_invoice_input(invoice)

        invoice = create_validator_invoice()
        invoice.info.delivery_date = ""
        normalize_invoice_input(invoice)
        self.assertEqual(invoice.info.delivery_date, "")

    def test_document_rule_matrix(self):
        cases = [
            (
                "type code",
                create_validator_invoice,
                lambda i: setattr(i.info, "invoice_type_code", "389"),
                "InvoiceTypeCode",
            ),
            (
                "self billing tax id",
                create_validator_self_billed_invoice,
                lambda i: (setattr(i.seller, "vat", ""), setattr(i.seller, "tax_number", "")),
                "Steuernummer oder USt-ID",
            ),
            (
                "self billing iban",
                create_validator_self_billed_invoice,
                lambda i: setattr(i.payment, "iban", ""),
                "IBAN",
            ),
            (
                "quantity",
                create_validator_invoice,
                lambda i: setattr(i.items[0], "qty", Decimal("0")),
                "positiv",
            ),
            (
                "negative amount",
                create_validator_invoice,
                lambda i: setattr(i.items[0], "net", Decimal("-1")),
                "positiv",
            ),
            (
                "zero tax category",
                create_validator_invoice,
                lambda i: (setattr(i.items[0], "vat", Decimal("0")), setattr(i.items[0], "tax_category", "S")),
                "Steuerkategorie Z",
            ),
        ]
        for name, factory, mutate, expected in cases:
            with self.subTest(case=name):
                invoice = factory()
                mutate(invoice)
                errors = validate_document(invoice).errors
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_total_warning_matrix(self):
        invoice = create_validator_invoice()
        invoice.monetarytotal.line_extension_amount += Decimal("0.01")
        self.assertTrue(
            any("Nettosumme" in warning for warning in validate_totals(invoice).warnings)
        )

        invoice = create_validator_invoice()
        invoice.taxtotal[0].amount += Decimal("0.01")
        self.assertTrue(
            any("Steuer falsch" in warning for warning in validate_totals(invoice).warnings)
        )

        invoice = create_validator_invoice()
        invoice.monetarytotal.payable_amount += Decimal("0.01")
        self.assertTrue(
            any("Bruttobetrag" in warning for warning in validate_totals(invoice).warnings)
        )

    def test_xsd_rejects_malformed_and_incomplete_xml(self):
        malformed = validate_xsd(b"<Invoice>")
        self.assertFalse(malformed.valid)
        self.assertTrue(any("nicht geparst" in error for error in malformed.errors))

        root = etree.fromstring(create_xml(create_validator_invoice()))
        invoice_id = root.find("cbc:ID", NS)
        root.remove(invoice_id)
        incomplete = validate_xsd(etree.tostring(root))
        self.assertFalse(incomplete.valid)
        self.assertTrue(any("XSD Fehler" in error for error in incomplete.errors))


if __name__ == "__main__":
    unittest.main()
