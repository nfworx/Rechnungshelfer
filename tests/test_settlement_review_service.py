import unittest
from dataclasses import replace
from decimal import Decimal

from rechnungshelfer.application.settlement_review_service import (
    SettlementReviewService,
)
from rechnungshelfer.services.settlement_credit_note_parser import (
    SettlementCreditNoteParser,
)
from tests.test_settlement_credit_note_parser import (
    SETTLEMENT_TEXT,
    extraction_with,
)


class SettlementReviewServiceTests(unittest.TestCase):
    def setUp(self):
        draft = SettlementCreditNoteParser().parse(extraction_with(SETTLEMENT_TEXT))
        self.assertIsNotNone(draft)
        self.service = SettlementReviewService()
        self.review = self.service.create_review(draft)

    def test_creates_editable_review_and_preserves_source_metadata(self):
        self.assertEqual(self.review.credit_note_number.value, "91001")
        self.assertEqual(self.review.credit_note_date.value, "30.11.2025")
        self.assertEqual(self.review.deliveries[0].gross_quantity_kg.value, "2815")
        self.assertEqual(self.review.net_amount.value, "2087,53")
        self.assertEqual(self.review.supplier_number.value, "1001")
        self.assertEqual(self.review.supplier_name.value, "Musterhof Testlieferant")
        self.assertEqual(self.review.iban.value, "DE89370400440532013000")
        self.assertEqual(
            self.review.credit_note_number.source,
            "Nr.: 91001 vom 30.11.2025",
        )
        self.assertEqual(self.review.credit_note_number.page_number, 1)
        self.assertEqual(self.review.credit_note_number.confidence, 1.0)

    def test_consistent_test_settlement_is_valid(self):
        result = self.service.validate(self.review)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.issues, ())

    def test_detects_ocr_quantity_error_and_accepts_manual_correction(self):
        delivery = self.review.deliveries[2]
        wrong_delivery = replace(
            delivery,
            gross_quantity_kg=delivery.gross_quantity_kg.with_value("6.252"),
        )
        wrong_review = replace(
            self.review,
            deliveries=(
                *self.review.deliveries[:2],
                wrong_delivery,
                *self.review.deliveries[3:],
            ),
        )

        result = self.service.validate(wrong_review)

        self.assertFalse(result.is_valid)
        self.assertIn(
            "deliveries.2.settlement_quantity_kg",
            {issue.field_path for issue in result.issues},
        )

        corrected_delivery = replace(
            wrong_delivery,
            gross_quantity_kg=wrong_delivery.gross_quantity_kg.with_value("6.352"),
        )
        corrected_review = replace(
            wrong_review,
            deliveries=(
                *wrong_review.deliveries[:2],
                corrected_delivery,
                *wrong_review.deliveries[3:],
            ),
        )
        self.assertTrue(self.service.validate(corrected_review).is_valid)

    def test_detects_delivery_and_total_arithmetic_mismatches(self):
        first = self.review.deliveries[0]
        wrong_first = replace(
            first,
            net_amount=first.net_amount.with_value("400,00"),
        )
        wrong_review = replace(
            self.review,
            deliveries=(wrong_first, *self.review.deliveries[1:]),
            vat_amount=self.review.vat_amount.with_value("160,00"),
            total_amount=self.review.total_amount.with_value("2247,53"),
            credit_amount=self.review.credit_amount.with_value("2200,00"),
        )

        result = self.service.validate(wrong_review)
        paths = {issue.field_path for issue in result.issues}

        self.assertFalse(result.is_valid)
        self.assertIn("deliveries.0.net_amount", paths)
        self.assertIn("net_amount", paths)
        self.assertIn("vat_amount", paths)
        self.assertIn("credit_amount", paths)

    def test_reconciles_quantity_and_price_changes_with_delivery_values(self):
        first = self.review.deliveries[0]
        quantity_detail = replace(
            first.details[0],
            quantity_change_kg=first.details[0].quantity_change_kg.with_value("-20"),
        )
        price_detail = replace(
            first.details[1],
            price_change_per_tonne=(
                first.details[1].price_change_per_tonne.with_value("-14,50")
            ),
        )
        wrong_first = replace(
            first,
            details=(quantity_detail, price_detail),
        )
        wrong_review = replace(
            self.review,
            deliveries=(wrong_first, *self.review.deliveries[1:]),
        )

        result = self.service.validate(wrong_review)
        paths = {issue.field_path for issue in result.issues}

        self.assertFalse(result.is_valid)
        self.assertIn("deliveries.0.settlement_quantity_kg", paths)
        self.assertIn("deliveries.0.settlement_price_per_tonne", paths)

    def test_rejects_missing_and_malformed_required_values(self):
        wrong_review = replace(
            self.review,
            credit_note_number=self.review.credit_note_number.with_value(""),
            credit_note_date=self.review.credit_note_date.with_value("2025-11-30"),
        )

        result = self.service.validate(wrong_review)
        paths = {issue.field_path for issue in result.issues}

        self.assertFalse(result.is_valid)
        self.assertIn("credit_note_number", paths)
        self.assertIn("credit_note_date", paths)

    def test_nonzero_advance_payment_is_preserved_in_structured_document(self):
        review = replace(
            self.review,
            advance_payment=self.review.advance_payment.with_value("100,00"),
            credit_amount=self.review.credit_amount.with_value("2150,36"),
        )

        result = self.service.validate(review)
        credit_note = self.service.create_credit_note(review)

        self.assertTrue(result.is_valid)
        self.assertEqual(credit_note.advance_payment, Decimal("100.00"))
        self.assertEqual(credit_note.credit_amount, Decimal("2150.36"))

    def test_recalculates_delivery_amount_and_document_totals_after_edit(self):
        first = self.review.deliveries[0]
        changed_first = replace(
            first,
            settlement_price_per_tonne=(
                first.settlement_price_per_tonne.with_value("145,00")
            ),
        )
        changed_review = replace(
            self.review,
            deliveries=(changed_first, *self.review.deliveries[1:]),
        )

        recalculated = self.service.recalculate_financials(changed_review)

        self.assertEqual(recalculated.deliveries[0].net_amount.value, "404,12")
        self.assertEqual(recalculated.net_amount.value, "2088,93")
        self.assertEqual(recalculated.vat_amount.value, "162,94")
        self.assertEqual(recalculated.total_amount.value, "2251,87")
        self.assertEqual(recalculated.credit_amount.value, "2251,87")

    def test_creates_structured_credit_note_without_flattening_deliveries(self):
        credit_note = self.service.create_credit_note(self.review)

        self.assertEqual(credit_note.credit_note_number, "91001")
        self.assertEqual(credit_note.credit_note_date.isoformat(), "2025-11-30")
        self.assertEqual(len(credit_note.deliveries), 4)
        self.assertEqual(
            [delivery.net_amount for delivery in credit_note.deliveries],
            [
                Decimal("402.72"),
                Decimal("538.70"),
                Decimal("908.76"),
                Decimal("237.35"),
            ],
        )
        first = credit_note.deliveries[0]
        self.assertEqual(first.ticket_number, "T1001")
        self.assertEqual(first.gross_quantity_kg, Decimal("2815"))
        self.assertEqual(first.settlement_quantity_kg, Decimal("2787"))
        self.assertEqual(first.details[0].label, "Besatz")
        self.assertEqual(first.details[0].analysis_value, Decimal("1.00"))
        self.assertEqual(first.details[0].quantity_change_kg, Decimal("-28"))
        self.assertEqual(
            first.details[1].price_change_per_tonne,
            Decimal("-15.50"),
        )
        self.assertEqual(credit_note.net_amount, Decimal("2087.53"))
        self.assertEqual(credit_note.credit_amount, Decimal("2250.36"))
        self.assertEqual(credit_note.supplier.supplier_number, "1001")
        self.assertEqual(credit_note.supplier.name, "Musterhof Testlieferant")
        self.assertEqual(credit_note.payment.iban, "DE89370400440532013000")

    def test_structured_credit_note_can_be_edited_through_review_model(self):
        credit_note = self.service.create_credit_note(self.review)
        credit_note = replace(
            credit_note,
            deliveries=(
                replace(credit_note.deliveries[0], grain_type_code="oats"),
                *credit_note.deliveries[1:],
            ),
        )

        restored_review = self.service.create_review_from_credit_note(credit_note)

        self.assertEqual(restored_review.credit_note_number.value, "91001")
        self.assertEqual(restored_review.credit_note_date.value, "30.11.2025")
        self.assertEqual(restored_review.deliveries[0].details[0].label.value, "Besatz")
        self.assertEqual(restored_review.deliveries[0].grain_type_code, "oats")
        self.assertEqual(restored_review.supplier_name.value, "Musterhof Testlieferant")
        self.assertEqual(restored_review.payment_terms.value, "Auszahlung innerhalb von 14 Tagen.")
        self.assertTrue(self.service.validate(restored_review).is_valid)
        restored_note = self.service.create_credit_note(restored_review)
        self.assertEqual(restored_note.deliveries[0].grain_type_code, "oats")


if __name__ == "__main__":
    unittest.main()
