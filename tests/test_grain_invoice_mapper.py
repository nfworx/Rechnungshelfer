import tempfile
import unittest
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

from rechnungshelfer.application.grain_invoice_mapper import (
    create_grain_settlement_invoice,
)
from rechnungshelfer.controller import InvoiceController
from rechnungshelfer.domain.grain_calculation import calculate_settlement_quantities
from rechnungshelfer.domain.grain_models import (
    GrainDelivery,
    GrainValidationError,
    QualityFeature,
    QualityMeasurement,
    QuantityReference,
    RuleDirection,
    RuleKind,
    RulePhase,
    SettlementRule,
    SettlementSchemeVersion,
)
from rechnungshelfer.domain.invoice_factory import InvoiceFactory
from rechnungshelfer.domain.models import (
    DocumentType,
    Invoice,
    Payment,
    Seller,
)
from rechnungshelfer.repositories.invoice_repository import InvoiceRepository
from rechnungshelfer.services.pdf_service import create_pdf
from rechnungshelfer.services.validation_service import (
    validate_document,
    validate_xsd,
)
from rechnungshelfer.services.xml_service import create_xml


class GrainInvoiceMapperTests(unittest.TestCase):
    def setUp(self):
        self.scheme = SettlementSchemeVersion(
            id="wheat-2026-v1",
            scheme_id="wheat-2026",
            version=1,
            name="Weizen 2026",
            grain_type_code="wheat",
            quality_features=(QualityFeature("dockage", "Besatz"),),
            rules=(
                SettlementRule(
                    code="dockage-deduction",
                    label="Besatzabzug",
                    phase=RulePhase.QUANTITY_DEDUCTION,
                    kind=RuleKind.PERCENTAGE_OF_MEASUREMENT,
                    feature_code="dockage",
                    quantity_reference=QuantityReference.GROSS_QUANTITY,
                    parameters={"factor": "1"},
                ),
                SettlementRule(
                    code="drying",
                    label="Trocknungskosten",
                    phase=RulePhase.PRICE_ADJUSTMENT,
                    kind=RuleKind.ABSOLUTE_PER_TONNE,
                    direction=RuleDirection.DEDUCTION,
                    parameters={"amount_per_tonne": "5"},
                ),
            ),
        )
        self.deliveries = (
            self._delivery("delivery-1", "WS-4711", "10000", "3"),
            self._delivery("delivery-2", "WS-4712", "8000", "2"),
        )
        self.settlement = calculate_settlement_quantities(
            self.deliveries,
            self.scheme,
        )
        self.template = InvoiceFactory().create(
            DocumentType.SELF_BILLED_INVOICE,
            supplier_number="0001",
        )

    @staticmethod
    def _delivery(delivery_id, ticket_number, quantity, dockage):
        return GrainDelivery(
            id=delivery_id,
            supplier_number="0001",
            delivery_date=date(2026, 10, 8),
            ticket_number=ticket_number,
            grain_type_code="wheat",
            gross_quantity_kg=Decimal(quantity),
            base_price_per_tonne=Decimal("200"),
            measurements=(QualityMeasurement("dockage", Decimal(dockage)),),
        )

    def test_creates_one_exact_net_item_per_delivery(self):
        invoice = create_grain_settlement_invoice(
            self.template,
            self.deliveries,
            self.settlement,
            Decimal("7.8"),
        )

        self.assertTrue(invoice.is_self_billed)
        self.assertEqual(invoice.info.invoice_type_code, "389")
        self.assertEqual(len(invoice.items), 2)
        self.assertEqual([item.pos for item in invoice.items], ["1", "2"])
        self.assertTrue(all(item.qty == Decimal("1") for item in invoice.items))
        self.assertEqual(
            [item.net for item in invoice.items],
            [result.net_amount for result in self.settlement.delivery_results],
        )
        self.assertEqual(
            invoice.monetarytotal.tax_exclusive_amount,
            self.settlement.net_amount,
        )

    def test_uses_existing_invoice_tax_calculation_for_supported_rates(self):
        for rate in (Decimal("0"), Decimal("7"), Decimal("7.8"), Decimal("19")):
            with self.subTest(rate=rate):
                invoice = create_grain_settlement_invoice(
                    self.template,
                    self.deliveries,
                    self.settlement,
                    rate,
                )
                expected_tax = (
                    self.settlement.net_amount * rate / Decimal("100")
                ).quantize(Decimal("0.01"))
                self.assertEqual(sum(tax.amount for tax in invoice.taxtotal), expected_tax)
                self.assertEqual(
                    invoice.monetarytotal.payable_amount,
                    self.settlement.net_amount + expected_tax,
                )
                expected_category = "Z" if rate == 0 else "S"
                self.assertTrue(
                    all(item.tax_category == expected_category for item in invoice.items)
                )

    def test_description_contains_traceable_values_and_omits_zero_rows(self):
        invoice = create_grain_settlement_invoice(
            self.template,
            self.deliveries,
            self.settlement,
            Decimal("7"),
        )

        description = invoice.items[0].description
        self.assertIn("Lieferdatum: 08.10.2026", description)
        self.assertIn("Wiegeschein: WS-4711", description)
        self.assertIn("Ursprungsmenge: 10.000,000 kg", description)
        self.assertIn("Mengenabzug – Besatzabzug: -300,000 kg", description)
        self.assertIn("Preis-/Kostenabzug – Trocknungskosten: -48,50 EUR", description)
        self.assertIn("Abrechnungsbetrag: 1.891,50 EUR", description)
        self.assertNotIn("-0,00", description)

    def test_template_is_not_modified(self):
        original = deepcopy(self.template.to_dict())

        invoice = create_grain_settlement_invoice(
            self.template,
            self.deliveries,
            self.settlement,
            Decimal("7"),
        )

        self.assertEqual(self.template.to_dict(), original)
        self.assertIsNot(invoice, self.template)
        self.assertEqual(len(self.template.items), 1)

    def test_rejects_regular_invoice_template(self):
        template = InvoiceFactory().create(DocumentType.INVOICE)

        with self.assertRaisesRegex(GrainValidationError, "nur als Gutschrift"):
            create_grain_settlement_invoice(
                template,
                self.deliveries,
                self.settlement,
                Decimal("7"),
            )

    def test_rejects_supplier_mismatch(self):
        self.template.seller.supplier_number = "9999"

        with self.assertRaisesRegex(GrainValidationError, "Lieferant der Gutschrift"):
            create_grain_settlement_invoice(
                self.template,
                self.deliveries,
                self.settlement,
                Decimal("7"),
            )

    def test_rejects_delivery_result_mismatch(self):
        changed_delivery = GrainDelivery(
            id="delivery-1",
            supplier_number="0001",
            delivery_date=date(2026, 10, 8),
            ticket_number="WS-4711",
            grain_type_code="wheat",
            gross_quantity_kg=Decimal("9999"),
            base_price_per_tonne=Decimal("200"),
            measurements=(QualityMeasurement("dockage", Decimal("3")),),
        )

        with self.assertRaisesRegex(GrainValidationError, "veraltet"):
            create_grain_settlement_invoice(
                self.template,
                (changed_delivery, self.deliveries[1]),
                self.settlement,
                Decimal("7"),
            )

    def test_rejects_unsupported_vat_rate(self):
        with self.assertRaisesRegex(GrainValidationError, "nicht unterstützt"):
            create_grain_settlement_invoice(
                self.template,
                self.deliveries,
                self.settlement,
                Decimal("10"),
            )

    def _complete_invoice(self):
        own_company = Seller(
            name="Muster Agrarhandel GmbH",
            street="Handelsweg 10",
            postcode="12345",
            city="Musterstadt",
            country="DE",
            phone="0123456789",
            email="abrechnung@example.de",
            vat="DE123456789",
            tax_number="98/765/43210",
            registry_number="HRB 12345",
            buyer_reference="80001",
        )
        template = InvoiceFactory().create(
            DocumentType.SELF_BILLED_INVOICE,
            own_company=own_company,
            supplier_number="0001",
        )
        template.seller = Seller(
            name="Landwirt Test",
            street="Feldweg 1",
            postcode="54321",
            city="Dorf",
            country="DE",
            phone="0987654321",
            email="landwirt@example.de",
            tax_number="12/345/67890",
            supplier_number="0001",
            buyer_reference="0001",
        )
        template.payment = Payment(
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
            account_holder="Landwirt Test",
            payment_terms="Auszahlung bis 23.10.2026",
        )
        template.info.invoice_number = "80001"
        template.info.invoice_date = "09.10.2026"
        template.info.payment_due_date = "23.10.2026"
        return create_grain_settlement_invoice(
            template,
            self.deliveries,
            self.settlement,
            Decimal("7.8"),
        )

    def test_generated_invoice_is_ready_for_existing_pdf_and_xml_workflows(self):
        invoice = self._complete_invoice()
        controller = InvoiceController.__new__(InvoiceController)

        self.assertTrue(controller.check_pdf_required_fields(invoice))
        self.assertTrue(controller.check_xml_required_fields(invoice))
        self.assertEqual(validate_document(invoice).errors, [])

        restored = Invoice.from_dict(invoice.to_dict())
        xml = create_xml(restored)

        self.assertEqual(validate_xsd(xml).errors, [])
        self.assertEqual(restored.document_type, DocumentType.SELF_BILLED_INVOICE)
        self.assertEqual(
            restored.monetarytotal.payable_amount,
            invoice.monetarytotal.payable_amount,
        )
        self.assertIn("Wiegeschein: WS-4711", restored.items[0].description)

        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "getreide-gutschrift.pdf"
            create_pdf(restored, pdf_path)
            self.assertGreater(pdf_path.stat().st_size, 1000)

    def test_generated_invoice_can_be_saved_and_loaded(self):
        invoice = self._complete_invoice()

        with tempfile.TemporaryDirectory() as directory:
            repository = InvoiceRepository(Path(directory) / "invoices.db")
            try:
                repository.save(invoice)
                loaded = repository.load("80001")
            finally:
                repository.close()

        self.assertIsNotNone(loaded)
        self.assertTrue(loaded.is_self_billed)
        self.assertEqual(loaded.seller.supplier_number, "0001")
        self.assertEqual(len(loaded.items), len(self.deliveries))
        self.assertEqual(
            loaded.monetarytotal.payable_amount,
            invoice.monetarytotal.payable_amount,
        )


if __name__ == "__main__":
    unittest.main()
