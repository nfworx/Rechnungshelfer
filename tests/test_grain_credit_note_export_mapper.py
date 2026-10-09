import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from rechnungshelfer.application.grain_invoice_mapper import (
    create_invoice_from_grain_credit_note,
)
from rechnungshelfer.domain.grain_models import GrainValidationError
from rechnungshelfer.domain.models import Invoice
from tests.test_grain_credit_note_repository import structured_note


def exportable_note():
    return replace(
        structured_note(),
        payment_due_date=date(2025, 12, 14),
    )


class GrainCreditNoteExportMapperTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
