import unittest
from datetime import date
from decimal import Decimal

from rechnungshelfer.domain.grain_calculation import (
    calculate_delivery_baseline,
    calculate_delivery_quantities,
    calculate_settlement_quantities,
)
from rechnungshelfer.domain.grain_models import (
    GrainDelivery,
    GrainValidationError,
    PriceReference,
    QualityFeature,
    QualityMeasurement,
    QuantityReference,
    RuleDirection,
    RuleKind,
    RulePhase,
    RuleTier,
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
            "supplier_number": "0001",
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

    @staticmethod
    def _quantity_rule(**changes):
        values = {
            "code": "quantity-deduction",
            "label": "Mengenabzug",
            "phase": RulePhase.QUANTITY_DEDUCTION,
            "kind": RuleKind.PERCENTAGE_OF_MEASUREMENT,
            "feature_code": "moisture",
            "quantity_reference": QuantityReference.GROSS_QUANTITY,
        }
        values.update(changes)
        return SettlementRule(**values)

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

    def test_multiple_deliveries_are_aggregated(self):
        result = calculate_settlement_quantities(
            (
                self._delivery(),
                self._delivery(
                    id="delivery-2",
                    ticket_number="WS-4712",
                    gross_quantity_kg="5000",
                ),
            ),
            self._scheme(),
        )

        self.assertEqual(len(result.delivery_results), 2)
        self.assertEqual(result.gross_quantity_kg, Decimal("15000.000"))
        self.assertEqual(result.settlement_quantity_kg, Decimal("15000.000"))
        self.assertEqual(result.deducted_quantity_kg, Decimal("0.000"))
        self.assertEqual(result.base_amount, Decimal("3000.00"))

    def test_batch_requires_deliveries_from_one_supplier(self):
        with self.assertRaisesRegex(GrainValidationError, "Lieferanten"):
            calculate_settlement_quantities(
                (
                    self._delivery(),
                    self._delivery(
                        id="delivery-2",
                        ticket_number="WS-4712",
                        supplier_number="0002",
                    ),
                ),
                self._scheme(),
            )

    def test_batch_rejects_empty_or_duplicate_tickets(self):
        with self.assertRaisesRegex(GrainValidationError, "mindestens"):
            calculate_settlement_quantities((), self._scheme())
        with self.assertRaisesRegex(GrainValidationError, "Wiegescheinnummern"):
            calculate_settlement_quantities(
                (
                    self._delivery(),
                    self._delivery(id="delivery-2"),
                ),
                self._scheme(),
            )

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

    def test_absolute_price_deduction_changes_money_not_quantity(self):
        rule = SettlementRule(
            code="drying",
            label="Trocknung",
            phase=RulePhase.PRICE_ADJUSTMENT,
            kind=RuleKind.ABSOLUTE_PER_TONNE,
            parameters={"amount_per_tonne": "10"},
        )

        result = calculate_delivery_quantities(
            self._delivery(),
            self._scheme(rules=(rule,)),
        )

        self.assertEqual(result.settlement_quantity_kg, Decimal("10000.000"))
        self.assertEqual(result.base_amount, Decimal("2000.00"))
        self.assertEqual(result.settlement_price_per_tonne, Decimal("190.00"))
        self.assertEqual(result.net_amount, Decimal("1900.00"))
        self.assertEqual(
            result.monetary_adjustments[0].amount_delta,
            Decimal("-100.00"),
        )

    def test_tiered_drying_cost_uses_measurement_for_price_deduction(self):
        rule = SettlementRule(
            code="drying-tier",
            label="Trocknung nach Feuchte",
            phase=RulePhase.PRICE_ADJUSTMENT,
            kind=RuleKind.TIERED,
            feature_code="moisture",
            parameters={"result_kind": "absolute_per_tonne"},
            tiers=(
                RuleTier(value="0", upper_bound="14.5"),
                RuleTier(value="5", lower_bound="14.5"),
            ),
        )

        result = calculate_delivery_quantities(
            self._delivery(),
            self._scheme(rules=(rule,)),
        )

        self.assertEqual(result.settlement_price_per_tonne, Decimal("195.00"))
        self.assertEqual(result.net_amount, Decimal("1950.00"))

    def test_drying_cost_can_charge_each_unit_above_basis(self):
        rule = SettlementRule(
            code="drying-excess",
            label="Trocknung über Basisfeuchte",
            phase=RulePhase.PRICE_ADJUSTMENT,
            kind=RuleKind.EXCESS_OVER_BASIS,
            feature_code="moisture",
            parameters={"basis_value": "14", "amount_per_unit": "2"},
        )

        result = calculate_delivery_quantities(
            self._delivery(),
            self._scheme(rules=(rule,)),
        )

        self.assertEqual(result.settlement_price_per_tonne, Decimal("199.00"))
        self.assertEqual(result.net_amount, Decimal("1990.00"))

    def test_percentage_surcharge_and_fixed_cost_follow_price_rules(self):
        surcharge = SettlementRule(
            code="premium",
            label="Qualitätszuschlag",
            phase=RulePhase.PRICE_ADJUSTMENT,
            kind=RuleKind.PERCENTAGE_OF_PRICE,
            direction=RuleDirection.SURCHARGE,
            price_reference=PriceReference.BASE_PRICE,
            parameters={"percentage": "10"},
        )
        cost = SettlementRule(
            code="handling",
            label="Bearbeitungskosten",
            phase=RulePhase.COST,
            kind=RuleKind.FIXED_AMOUNT,
            parameters={"amount": "25"},
        )

        result = calculate_delivery_quantities(
            self._delivery(),
            self._scheme(rules=(surcharge, cost)),
        )

        self.assertEqual(result.settlement_price_per_tonne, Decimal("220.00"))
        self.assertEqual(result.net_amount, Decimal("2175.00"))
        self.assertEqual(len(result.monetary_adjustments), 2)

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

    def test_percentage_measurement_rule_supports_configurable_factor(self):
        rule = self._quantity_rule(
            code="dockage",
            label="Besatzabzug",
            feature_code="dockage",
            parameters={"factor": "1.1"},
        )
        scheme = self._scheme(
            quality_features=(QualityFeature("dockage", "Besatz"),),
            rules=(rule,),
        )
        delivery = self._delivery(
            measurements=(QualityMeasurement("dockage", "3"),),
        )

        result = calculate_delivery_quantities(delivery, scheme)

        self.assertEqual(
            result.quantity_deductions[0].deducted_quantity_kg,
            Decimal("330.000"),
        )
        self.assertEqual(result.settlement_quantity_kg, Decimal("9670.000"))
        self.assertEqual(result.base_amount, Decimal("1934.00"))
        deduction_step = result.steps[1]
        self.assertEqual(deduction_step.basis, Decimal("10000.000"))
        self.assertEqual(deduction_step.unrounded_result, Decimal("330.0000"))

    def test_rules_use_explicit_order_and_remaining_quantity(self):
        fixed = self._quantity_rule(
            code="fixed",
            label="Fester Abzug",
            kind=RuleKind.FIXED_QUANTITY,
            feature_code=None,
            order=0,
            parameters={"amount_kg": "100"},
        )
        percentage = self._quantity_rule(
            code="percentage",
            label="Prozentualer Abzug",
            order=1,
            quantity_reference=QuantityReference.REMAINING_QUANTITY,
        )
        result = calculate_delivery_quantities(
            self._delivery(
                measurements=(QualityMeasurement("moisture", "10"),),
            ),
            self._scheme(rules=(percentage, fixed)),
        )

        self.assertEqual(
            [item.rule_code for item in result.quantity_deductions],
            ["fixed", "percentage"],
        )
        self.assertEqual(
            result.quantity_deductions[1].reference_quantity_kg,
            Decimal("9900.000"),
        )
        self.assertEqual(result.settlement_quantity_kg, Decimal("8910.000"))

    def test_excess_rule_only_deducts_value_above_basis(self):
        rule = self._quantity_rule(
            kind=RuleKind.EXCESS_OVER_BASIS,
            parameters={"basis_value": "14", "factor": "1"},
        )
        result = calculate_delivery_quantities(
            self._delivery(
                measurements=(QualityMeasurement("moisture", "15.5"),),
            ),
            self._scheme(rules=(rule,)),
        )

        self.assertEqual(
            result.quantity_deductions[0].deducted_quantity_kg,
            Decimal("150.000"),
        )

    def test_corrected_measurement_is_used_by_quantity_rule(self):
        rule = self._quantity_rule()
        result = calculate_delivery_quantities(
            self._delivery(
                measurements=(
                    QualityMeasurement(
                        "moisture",
                        "10",
                        corrected_value="2.5",
                        correction_reason="Kontrollanalyse",
                    ),
                ),
            ),
            self._scheme(rules=(rule,)),
        )

        self.assertEqual(
            result.quantity_deductions[0].deducted_quantity_kg,
            Decimal("250.000"),
        )
        self.assertEqual(
            result.quantity_deductions[0].measurement_value,
            Decimal("2.5"),
        )

    def test_tiered_rule_selects_matching_percentage(self):
        rule = self._quantity_rule(
            kind=RuleKind.TIERED,
            tiers=(
                RuleTier(value="0", upper_bound="14.5"),
                RuleTier(value="2", lower_bound="14.5", upper_bound="16"),
                RuleTier(value="3.5", lower_bound="16"),
            ),
        )
        result = calculate_delivery_quantities(
            self._delivery(
                measurements=(QualityMeasurement("moisture", "15"),),
            ),
            self._scheme(rules=(rule,)),
        )

        self.assertEqual(
            result.quantity_deductions[0].deducted_quantity_kg,
            Decimal("200.000"),
        )

    def test_tier_can_define_a_fixed_quantity(self):
        rule = self._quantity_rule(
            kind=RuleKind.TIERED,
            parameters={"result_kind": "fixed_quantity_kg"},
            tiers=(RuleTier(value="75", lower_bound="14"),),
        )
        result = calculate_delivery_quantities(
            self._delivery(),
            self._scheme(rules=(rule,)),
        )

        self.assertEqual(
            result.quantity_deductions[0].deducted_quantity_kg,
            Decimal("75.000"),
        )

    def test_noncovered_tier_value_is_reported(self):
        rule = self._quantity_rule(
            kind=RuleKind.TIERED,
            tiers=(
                RuleTier(value="1", upper_bound="10"),
                RuleTier(value="2", lower_bound="20"),
            ),
        )
        with self.assertRaisesRegex(GrainValidationError, "nicht abgedeckt"):
            calculate_delivery_quantities(
                self._delivery(
                    measurements=(QualityMeasurement("moisture", "15"),),
                ),
                self._scheme(rules=(rule,)),
            )

    def test_overlapping_tiers_are_rejected(self):
        rule = self._quantity_rule(
            kind=RuleKind.TIERED,
            tiers=(
                RuleTier(value="1", upper_bound="15", upper_inclusive=True),
                RuleTier(value="2", lower_bound="15"),
            ),
        )
        with self.assertRaisesRegex(GrainValidationError, "ueberlappen"):
            calculate_delivery_quantities(
                self._delivery(),
                self._scheme(rules=(rule,)),
            )

    def test_rule_requires_reference_and_required_parameters(self):
        without_reference = self._quantity_rule(quantity_reference=None)
        with self.assertRaisesRegex(GrainValidationError, "Bezugsmenge"):
            calculate_delivery_quantities(
                self._delivery(),
                self._scheme(rules=(without_reference,)),
            )

        without_amount = self._quantity_rule(
            kind=RuleKind.FIXED_QUANTITY,
            feature_code=None,
        )
        with self.assertRaisesRegex(GrainValidationError, "amount_kg"):
            calculate_delivery_quantities(
                self._delivery(),
                self._scheme(rules=(without_amount,)),
            )

    def test_deduction_cannot_exceed_remaining_quantity(self):
        rule = self._quantity_rule(
            kind=RuleKind.FIXED_QUANTITY,
            feature_code=None,
            parameters={"amount_kg": "10001"},
        )
        with self.assertRaisesRegex(GrainValidationError, "Restmenge"):
            calculate_delivery_quantities(
                self._delivery(),
                self._scheme(rules=(rule,)),
            )

    def test_each_deduction_is_rounded_before_the_next_rule(self):
        first = self._quantity_rule(order=0)
        second = self._quantity_rule(
            code="second",
            order=1,
            quantity_reference=QuantityReference.REMAINING_QUANTITY,
        )
        result = calculate_delivery_quantities(
            self._delivery(
                gross_quantity_kg="1000",
                measurements=(QualityMeasurement("moisture", "0.00055"),),
            ),
            self._scheme(rules=(first, second)),
        )

        self.assertEqual(
            result.quantity_deductions[0].deducted_quantity_kg,
            Decimal("0.006"),
        )
        self.assertEqual(
            result.quantity_deductions[1].reference_quantity_kg,
            Decimal("999.994"),
        )

    def test_price_rule_cannot_be_misconfigured_as_quantity_rule(self):
        rule = self._quantity_rule(kind=RuleKind.ABSOLUTE_PER_TONNE)

        with self.assertRaisesRegex(GrainValidationError, "kein Mengenabzug"):
            calculate_delivery_quantities(
                self._delivery(),
                self._scheme(rules=(rule,)),
            )

    def test_rule_order_must_be_unique_within_phase(self):
        first = self._quantity_rule(code="first")
        second = self._quantity_rule(code="second")

        with self.assertRaisesRegex(GrainValidationError, "reihenfolge"):
            self._scheme(rules=(first, second))


if __name__ == "__main__":
    unittest.main()
