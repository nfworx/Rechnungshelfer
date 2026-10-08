import unittest
from datetime import date
from decimal import Decimal

from rechnungshelfer.domain.grain_calculation import calculate_delivery_baseline
from rechnungshelfer.domain.grain_models import (
    GrainDelivery,
    GrainValidationError,
    PriceReference,
    QualityFeature,
    QualityMeasurement,
    RuleDirection,
    RuleKind,
    RulePhase,
    SettlementRule,
    SettlementSchemeVersion,
)


class GrainCalculationContractTests(unittest.TestCase):
    @staticmethod
    def _scheme(**changes):
        values = {
            "id": "wheat-2026-v1",
            "scheme_id": "wheat-standard",
            "version": 1,
            "name": "Weizen Standard 2026",
            "grain_type_code": "wheat",
            "quality_features": (
                QualityFeature("moisture", "Feuchtigkeit"),
                QualityFeature("protein", "Protein", required=False),
            ),
            "default_base_price_per_tonne": "200.00",
        }
        values.update(changes)
        return SettlementSchemeVersion(**values)

    @staticmethod
    def _delivery(**changes):
        values = {
            "id": "delivery-1",
            "supplier_number": "L0001",
            "delivery_date": date(2026, 8, 1),
            "ticket_number": "WS-4711",
            "grain_type_code": "wheat",
            "gross_quantity_kg": "10000",
            "measurements": (
                QualityMeasurement("moisture", "14.5"),
            ),
        }
        values.update(changes)
        return GrainDelivery(**values)

    def test_neutral_baseline_uses_decimal_units_and_structured_steps(self):
        result = calculate_delivery_baseline(self._delivery(), self._scheme())

        self.assertEqual(result.gross_quantity_kg, Decimal("10000.000"))
        self.assertEqual(result.settlement_quantity_kg, Decimal("10000.000"))
        self.assertEqual(result.base_price_per_tonne, Decimal("200.00"))
        self.assertEqual(result.net_amount, Decimal("2000.00"))
        self.assertEqual(
            [step.code for step in result.steps],
            ["gross_quantity", "base_price", "base_amount"],
        )

    def test_delivery_price_overrides_scheme_default(self):
        result = calculate_delivery_baseline(
            self._delivery(base_price_per_tonne="212.345"),
            self._scheme(),
        )

        self.assertEqual(result.base_price_per_tonne, Decimal("212.35"))
        self.assertEqual(result.net_amount, Decimal("2123.50"))

    def test_missing_required_measurement_is_rejected(self):
        with self.assertRaisesRegex(GrainValidationError, "Feuchtigkeit"):
            calculate_delivery_baseline(
                self._delivery(measurements=()),
                self._scheme(),
            )

    def test_negative_or_zero_quantity_is_rejected(self):
        for quantity in ("0", "-1"):
            with self.subTest(quantity=quantity):
                with self.assertRaisesRegex(GrainValidationError, "Bruttomenge"):
                    self._delivery(gross_quantity_kg=quantity)

    def test_duplicate_measurements_are_rejected(self):
        values = (
            QualityMeasurement("moisture", "14.5"),
            QualityMeasurement("moisture", "14.7"),
        )
        with self.assertRaisesRegex(GrainValidationError, "nur einmal"):
            self._delivery(measurements=values)

    def test_corrected_measurement_preserves_raw_value(self):
        measurement = QualityMeasurement(
            "moisture",
            "15.1",
            corrected_value="14.9",
            correction_reason="Kontrollanalyse",
        )

        self.assertEqual(measurement.raw_value, Decimal("15.1"))
        self.assertEqual(measurement.effective_value, Decimal("14.9"))

    def test_price_deduction_is_editable_rule_data(self):
        rule = SettlementRule(
            code="protein-deduction",
            label="Proteinabschlag",
            phase=RulePhase.PRICE_ADJUSTMENT,
            kind=RuleKind.ABSOLUTE_PER_TONNE,
            feature_code="protein",
            direction=RuleDirection.DEDUCTION,
            price_reference=PriceReference.BASE_PRICE,
            parameters={"amount_per_tonne": "2.50", "threshold": "11.5"},
        )
        scheme = self._scheme(rules=(rule,))

        self.assertEqual(
            scheme.rules[0].parameters["amount_per_tonne"],
            "2.50",
        )
        with self.assertRaises(TypeError):
            scheme.rules[0].parameters["amount_per_tonne"] = "3.00"

    def test_scheme_rejects_duplicate_feature_and_rule_codes(self):
        duplicate_features = (
            QualityFeature("moisture", "Feuchtigkeit"),
            QualityFeature("moisture", "Feuchte"),
        )
        with self.assertRaisesRegex(GrainValidationError, "Merkmalscodes"):
            self._scheme(quality_features=duplicate_features)

        rule = SettlementRule(
            code="deduction",
            label="Abschlag",
            phase=RulePhase.PRICE_ADJUSTMENT,
            kind=RuleKind.FIXED_AMOUNT,
        )
        with self.assertRaisesRegex(GrainValidationError, "Regelcodes"):
            self._scheme(rules=(rule, rule))

    def test_rule_may_only_reference_an_active_feature(self):
        rule = SettlementRule(
            code="falling-number-deduction",
            label="Fallzahlabschlag",
            phase=RulePhase.PRICE_ADJUSTMENT,
            kind=RuleKind.TIERED,
            feature_code="falling_number",
        )

        with self.assertRaisesRegex(GrainValidationError, "nicht aktive Merkmale"):
            self._scheme(rules=(rule,))


if __name__ == "__main__":
    unittest.main()
