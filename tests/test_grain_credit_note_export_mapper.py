import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from lxml import etree

from rechnungshelfer.application.grain_invoice_mapper import (
    create_invoice_from_grain_credit_note,
)
from rechnungshelfer.controller import InvoiceController
from rechnungshelfer.domain.grain_models import GrainValidationError
from rechnungshelfer.domain.models import Invoice
from rechnungshelfer.services.kosit_validation_service import (
    JAVA_EXE,
    KOSIT_JAR,
    SCENARIOS_XML,
)
from rechnungshelfer.services.validation_service import validate_invoice, validate_xsd
from rechnungshelfer.services.pdf_invoice_metadata import (
    DOCUMENT_KIND_GRAIN_CREDIT_NOTE,
)
from rechnungshelfer.repositories.grain_credit_note_record import (
    grain_credit_note_to_data,
)
from rechnungshelfer.services.xml_service import NSMAP, create_xml
from tests.test_grain_credit_note_repository import structured_note


NS = {
    "ubl": NSMAP[None],
    "cbc": NSMAP["cbc"],
    "cac": NSMAP["cac"],
}
KOSIT_AVAILABLE = all(path.exists() for path in (JAVA_EXE, KOSIT_JAR, SCENARIOS_XML))


def exportable_note():
    return replace(
        structured_note(),
        payment_due_date=date(2025, 12, 14),
    )


def exportable_note_with_allowance_and_advance():
    note = exportable_note()
    first = note.deliveries[0]
    cost = replace(first.details[0], amount_change=Decimal("-5.00"))
    changed_first = replace(
        first,
        details=(cost, *first.details[1:]),
        net_amount=Decimal("397.72"),
    )
    net = Decimal("2082.53")
    vat = Decimal("162.44")
    changed = replace(
        note,
        deliveries=(changed_first, *note.deliveries[1:]),
        net_amount=net,
        vat_amount=vat,
        total_amount=net + vat,
        advance_payment=Decimal("100.00"),
        credit_amount=net + vat - Decimal("100.00"),
    )
    return changed, cost


class GrainCreditNoteExportMapperTests(unittest.TestCase):
    def test_controller_embeds_structured_note_in_grain_pdf_export(self):
        note = exportable_note()
        invoice = create_invoice_from_grain_credit_note(note)
        export_service = MagicMock()
        controller = InvoiceController.__new__(InvoiceController)
        controller.export_service = export_service

        controller.generate_pdf(
            invoice,
            "getreidegutschrift.pdf",
            grain_credit_note=note,
        )

        export_service.export_pdf.assert_called_once()
        args, kwargs = export_service.export_pdf.call_args
        self.assertEqual(args[0].to_dict(), invoice.to_dict())
        self.assertEqual(args[1], "getreidegutschrift.pdf")
        self.assertEqual(kwargs["document_kind"], DOCUMENT_KIND_GRAIN_CREDIT_NOTE)
        self.assertEqual(
            kwargs["grain_credit_note_data"],
            grain_credit_note_to_data(note),
        )

    def test_each_delivery_uses_kilograms_and_tonne_price_base(self):
        note = exportable_note()

        invoice = create_invoice_from_grain_credit_note(note)

        first = invoice.items[0]
        self.assertEqual(first.qty, Decimal("2787"))
        self.assertEqual(first.unit, "KGM")
        self.assertEqual(first.price_without_discount, Decimal("144.50"))
        self.assertEqual(first.price_base_quantity, Decimal("1000"))
        self.assertEqual(first.price_base_unit, "KGM")
        self.assertEqual(first.net, Decimal("402.72"))
        self.assertEqual(
            invoice.monetarytotal.tax_exclusive_amount,
            note.net_amount,
        )

    def test_analysis_and_adjustments_are_stable_item_properties(self):
        invoice = create_invoice_from_grain_credit_note(exportable_note())

        properties = {
            prop.name: prop.value for prop in invoice.items[0].item_properties
        }

        self.assertEqual(properties["Lieferscheinnummer"], "T1001")
        self.assertEqual(properties["Lieferdatum"], "09.08.2025")
        self.assertEqual(properties["Ursprungsmenge (kg)"], "2815")
        self.assertEqual(properties["Basispreis (EUR/t)"], "160.00")
        self.assertEqual(properties["Analyse – Besatz"], "1.00")
        self.assertEqual(properties["Mengenänderung (kg) – Besatz"], "-28")
        self.assertEqual(
            properties["Preisänderung (EUR/t) – HL-Gewicht"],
            "-15.50",
        )

    def test_fixed_amount_adjustment_is_kept_separate_and_cent_exact(self):
        note = exportable_note()
        first = note.deliveries[0]
        cost = replace(first.details[0], amount_change=Decimal("-5.00"))
        changed_first = replace(
            first,
            details=(cost, *first.details[1:]),
            net_amount=Decimal("397.72"),
        )
        net = Decimal("2082.53")
        vat = Decimal("162.44")
        changed = replace(
            note,
            deliveries=(changed_first, *note.deliveries[1:]),
            net_amount=net,
            vat_amount=vat,
            total_amount=net + vat,
            credit_amount=net + vat,
        )

        invoice = create_invoice_from_grain_credit_note(changed)

        adjustment = invoice.items[0].line_adjustments[0]
        self.assertFalse(adjustment.is_charge)
        self.assertEqual(adjustment.amount, Decimal("5.00"))
        self.assertEqual(invoice.items[0].net, Decimal("397.72"))

    def test_advance_payment_reduces_only_the_payout(self):
        note = exportable_note()
        changed = replace(
            note,
            advance_payment=Decimal("100.00"),
            credit_amount=Decimal("2150.36"),
        )

        invoice = create_invoice_from_grain_credit_note(changed)

        self.assertEqual(invoice.monetarytotal.prepaid_amount, Decimal("100.00"))
        self.assertEqual(invoice.monetarytotal.tax_inclusive_amount, Decimal("2250.36"))
        self.assertEqual(invoice.monetarytotal.payable_amount, Decimal("2150.36"))

    def test_export_fields_survive_generic_invoice_round_trip(self):
        invoice = create_invoice_from_grain_credit_note(exportable_note())

        restored = Invoice.from_dict(invoice.to_dict())

        self.assertEqual(restored.items[0].qty, Decimal("2787"))
        self.assertEqual(restored.items[0].price_base_quantity, Decimal("1000"))
        self.assertEqual(restored.items[0].item_properties, invoice.items[0].item_properties)
        self.assertEqual(restored.items[0].line_adjustments, ())
        self.assertEqual(
            restored.monetarytotal.prepaid_amount,
            invoice.monetarytotal.prepaid_amount,
        )

    def test_missing_due_date_blocks_export_projection(self):
        with self.assertRaisesRegex(GrainValidationError, "Auszahlungsdatum"):
            create_invoice_from_grain_credit_note(structured_note())

    def test_xml_contains_kilogram_quantity_tonne_price_and_item_properties(self):
        invoice = create_invoice_from_grain_credit_note(exportable_note())

        xml = create_xml(invoice)
        root = etree.fromstring(xml)
        first_line = root.find("cac:InvoiceLine", NS)

        self.assertEqual(validate_xsd(xml).errors, [])
        self.assertEqual(
            first_line.findtext("cbc:InvoicedQuantity", namespaces=NS),
            "2787.00",
        )
        self.assertEqual(
            first_line.find("cbc:InvoicedQuantity", NS).get("unitCode"),
            "KGM",
        )
        self.assertEqual(
            first_line.findtext("cac:Price/cbc:PriceAmount", namespaces=NS),
            "144.50",
        )
        base_quantity = first_line.find("cac:Price/cbc:BaseQuantity", NS)
        self.assertEqual(base_quantity.text, "1000.00")
        self.assertEqual(base_quantity.get("unitCode"), "KGM")

        properties = {
            node.findtext("cbc:Name", namespaces=NS): node.findtext(
                "cbc:Value",
                namespaces=NS,
            )
            for node in first_line.findall(
                "cac:Item/cac:AdditionalItemProperty",
                NS,
            )
        }
        self.assertEqual(properties["Lieferscheinnummer"], "T1001")
        self.assertEqual(properties["Ursprungsmenge (kg)"], "2815")
        self.assertEqual(properties["Analyse – Besatz"], "1.00")

    def test_xml_contains_line_allowance_and_prepaid_amount(self):
        changed, cost = exportable_note_with_allowance_and_advance()

        xml = create_xml(create_invoice_from_grain_credit_note(changed))
        root = etree.fromstring(xml)
        allowance = root.find("cac:InvoiceLine/cac:AllowanceCharge", NS)

        self.assertEqual(validate_xsd(xml).errors, [])
        self.assertEqual(
            allowance.findtext("cbc:ChargeIndicator", namespaces=NS),
            "false",
        )
        self.assertEqual(
            allowance.findtext("cbc:AllowanceChargeReason", namespaces=NS),
            cost.label,
        )
        self.assertEqual(
            allowance.findtext("cbc:Amount", namespaces=NS),
            "5.00",
        )
        self.assertEqual(
            root.findtext(
                "cac:LegalMonetaryTotal/cbc:PrepaidAmount",
                namespaces=NS,
            ),
            "100.00",
        )
        self.assertEqual(
            root.findtext(
                "cac:LegalMonetaryTotal/cbc:PayableAmount",
                namespaces=NS,
            ),
            str(changed.credit_amount),
        )

    @unittest.skipUnless(KOSIT_AVAILABLE, "Portable Java/KoSIT ist nicht vorhanden")
    def test_grain_credit_note_xml_passes_kosit(self):
        note, _cost = exportable_note_with_allowance_and_advance()
        invoice = create_invoice_from_grain_credit_note(note)

        result = validate_invoice(create_xml(invoice), invoice, use_kosit=True)

        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])


if __name__ == "__main__":
    unittest.main()
