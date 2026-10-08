import unittest
from decimal import Decimal
from unittest.mock import Mock

from rechnungshelfer.domain.grain_models import GrainValidationError
from rechnungshelfer.domain.models import DocumentType
from rechnungshelfer.gui.grain_form_mapper import (
    AnalysisFormValue,
    DeliveryFormValue,
    FeatureFormValue,
    GrainSettlementForm,
    RuleFormValue,
    build_preview_scheme,
    calculate_settlement_preview,
    deserialize_rule_set,
    missing_required_analyses,
    parse_parameters,
    parse_tiers,
    serialize_rule_set,
)
from rechnungshelfer.gui.main_window import InvoiceGUI
from rechnungshelfer.gui.grain_settlement_view import GrainSettlementView
from rechnungshelfer.gui.grain_settlement_dialogs import (
    delivery_input_errors,
    require_features_used_by_active_rules,
)
from rechnungshelfer.gui.grain_rule_presets import grain_rule_preset


class GrainFormMapperTests(unittest.TestCase):
    @staticmethod
    def _delivery(**changes):
        values = {
            "id": "delivery-1",
            "delivery_date": "08.10.2026",
            "ticket_number": "WS-4711",
            "grain_type_code": "wheat",
            "gross_quantity_kg": "10.000",
            "base_price_per_tonne": "200,00",
            "analyses": (AnalysisFormValue("dockage", "3,0"),),
        }
        values.update(changes)
        return DeliveryFormValue(**values)

    @classmethod
    def _form(cls, **changes):
        values = {
            "supplier_number": "L0001",
            "features": (FeatureFormValue("dockage", "Besatz"),),
            "rules": (
                RuleFormValue(
                    code="dockage-deduction",
                    label="Besatzabzug",
                    kind="percentage_of_measurement",
                    feature_code="dockage",
                    quantity_reference="gross_quantity",
                    parameters="factor=1,1",
                ),
            ),
            "deliveries": (cls._delivery(),),
        }
        values.update(changes)
        return GrainSettlementForm(**values)

    def test_multiple_deliveries_are_calculated_and_summed(self):
        second = self._delivery(
            id="delivery-2",
            ticket_number="WS-4712",
            gross_quantity_kg="8.000",
            analyses=(AnalysisFormValue("dockage", "2,0"),),
        )

        result = calculate_settlement_preview(
            self._form(deliveries=(self._delivery(), second))
        )

        self.assertEqual(len(result.delivery_results), 2)
        self.assertEqual(result.gross_quantity_kg, Decimal("18000.000"))
        self.assertEqual(result.deducted_quantity_kg, Decimal("506.000"))
        self.assertEqual(result.settlement_quantity_kg, Decimal("17494.000"))
        self.assertEqual(result.base_amount, Decimal("3498.80"))

    def test_corrected_gui_value_is_used(self):
        delivery = self._delivery(
            analyses=(AnalysisFormValue("dockage", "10,0", "2,0"),)
        )

        result = calculate_settlement_preview(self._form(deliveries=(delivery,)))

        deduction = result.delivery_results[0].quantity_deductions[0]
        self.assertEqual(deduction.deducted_quantity_kg, Decimal("220.000"))

    def test_grain_type_is_taken_from_delivery_and_must_be_consistent(self):
        barley = self._delivery(
            id="delivery-2",
            ticket_number="WS-4712",
            grain_type_code="barley",
        )

        with self.assertRaisesRegex(GrainValidationError, "eine Getreideart"):
            calculate_settlement_preview(
                self._form(deliveries=(self._delivery(), barley))
            )

    def test_multiple_rules_follow_visible_row_order(self):
        rules = (
            RuleFormValue(
                code="fixed",
                label="Fester Abzug",
                kind="fixed_quantity",
                feature_code="",
                quantity_reference="gross_quantity",
                parameters="amount_kg=100",
                order=0,
            ),
            RuleFormValue(
                code="percentage",
                label="Besatzabzug",
                kind="percentage_of_measurement",
                feature_code="dockage",
                quantity_reference="remaining_quantity",
                parameters="factor=1",
                order=1,
            ),
        )

        result = calculate_settlement_preview(self._form(rules=rules))
        delivery_result = result.delivery_results[0]

        self.assertEqual(
            [item.rule_code for item in delivery_result.quantity_deductions],
            ["fixed", "percentage"],
        )
        self.assertEqual(delivery_result.settlement_quantity_kg, Decimal("9603.000"))

    def test_price_rule_from_gui_reduces_money_without_reducing_quantity(self):
        price_rule = RuleFormValue(
            code="drying",
            label="Trocknungskosten",
            kind="absolute_per_tonne",
            feature_code="",
            quantity_reference="",
            parameters="amount_per_tonne=5",
            phase="price_adjustment",
        )

        result = calculate_settlement_preview(self._form(rules=(price_rule,)))
        delivery_result = result.delivery_results[0]

        self.assertEqual(
            delivery_result.settlement_quantity_kg,
            Decimal("10000.000"),
        )
        self.assertEqual(delivery_result.base_amount, Decimal("2000.00"))
        self.assertEqual(delivery_result.net_amount, Decimal("1950.00"))
        self.assertEqual(result.deducted_amount, Decimal("50.00"))

    def test_parameter_parser_accepts_german_decimals_and_text_values(self):
        self.assertEqual(
            parse_parameters("factor=1,1; result_kind=fixed_quantity_kg"),
            {"factor": "1.1", "result_kind": "fixed_quantity_kg"},
        )

    def test_parameter_parser_rejects_duplicate_or_malformed_values(self):
        with self.assertRaisesRegex(GrainValidationError, "doppelt"):
            parse_parameters("factor=1; factor=2")
        with self.assertRaisesRegex(GrainValidationError, "name=wert"):
            parse_parameters("factor")

    def test_tier_parser_supports_open_interval_boundaries(self):
        tiers = parse_tiers("..14,5=0 | 14,5..16=2 | 16..=3,5")

        self.assertEqual(len(tiers), 3)
        self.assertIsNone(tiers[0].lower_bound)
        self.assertEqual(tiers[1].lower_bound, Decimal("14.5"))
        self.assertIsNone(tiers[2].upper_bound)
        self.assertEqual(tiers[2].value, Decimal("3.5"))

    def test_invalid_date_and_required_fields_are_reported(self):
        invalid = self._delivery(delivery_date="2026-10-08")
        with self.assertRaisesRegex(GrainValidationError, "TT.MM.JJJJ"):
            calculate_settlement_preview(self._form(deliveries=(invalid,)))
        with self.assertRaisesRegex(GrainValidationError, "Lieferantennummer"):
            calculate_settlement_preview(self._form(supplier_number=""))

    def test_missing_required_analysis_is_reported_by_domain(self):
        delivery = self._delivery(analyses=(AnalysisFormValue("dockage", ""),))
        with self.assertRaisesRegex(GrainValidationError, "Besatz"):
            calculate_settlement_preview(self._form(deliveries=(delivery,)))

    def test_disabled_rules_are_not_added_to_preview_scheme(self):
        rule = RuleFormValue(
            code="optional",
            label="Optionale Regel",
            kind="fixed_quantity",
            feature_code="",
            quantity_reference="gross_quantity",
            parameters="amount_kg=100",
            enabled=False,
        )

        scheme = build_preview_scheme(
            "wheat",
            (FeatureFormValue("moisture", "Feuchtigkeit", unit="%"),),
            (rule,),
        )

        self.assertEqual(scheme.rules, ())
        self.assertEqual(scheme.quality_features[0].unit, "%")

    def test_rule_set_json_snapshot_roundtrip_preserves_disabled_rules(self):
        features = (FeatureFormValue("moisture", "Feuchtigkeit", unit="%"),)
        rules = (
            RuleFormValue(
                code="drying",
                label="Trocknungskosten",
                kind="absolute_per_tonne",
                feature_code="",
                quantity_reference="",
                parameters="amount_per_tonne=8",
                phase="price_adjustment",
                enabled=False,
            ),
        )

        payload = serialize_rule_set("Weizen Standard", features, rules)
        restored = deserialize_rule_set(payload)

        self.assertEqual(restored, (features, rules))

    def test_delivery_table_creates_one_detail_row_per_adjustment(self):
        price_rule = RuleFormValue(
            code="drying",
            label="Trocknungskosten",
            kind="absolute_per_tonne",
            feature_code="",
            quantity_reference="",
            parameters="amount_per_tonne=5",
            phase="price_adjustment",
            order=1,
        )
        form = self._form(rules=(*self._form().rules, price_rule))
        result = calculate_settlement_preview(form).delivery_results[0]
        view = GrainSettlementView.__new__(GrainSettlementView)
        view.features = form.features

        rows = view._adjustment_rows(result)

        self.assertEqual(
            len(rows),
            len(result.quantity_deductions) + len(result.monetary_adjustments),
        )
        self.assertIn("Mengenabzug · Besatzabzug", rows[0][3])
        self.assertEqual(rows[0][5], "−330,000")
        self.assertEqual(rows[0][6], "-66,00")
        self.assertEqual(rows[0][7], "1.934,00")
        self.assertIn("Preisabzug · Trocknungskosten", rows[1][3])
        self.assertEqual(rows[1][6], "-48,35")
        self.assertEqual(view._gross_base_amount(result), Decimal("2000.00"))
        self.assertEqual(
            view._residual_row(result)[3],
            "= Verbleibender Abrechnungsbetrag",
        )
        self.assertEqual(view._residual_row(result)[7], "1.885,65")

    def test_delivery_input_validation_reports_fields_individually(self):
        features = (
            FeatureFormValue("moisture", "Feuchtigkeit", required=True),
            FeatureFormValue("protein", "Protein", required=False),
        )

        errors = delivery_input_errors(
            delivery_date="abc",
            ticket_number=" ",
            gross_quantity="null",
            base_price="-1",
            features=features,
            analyses={
                "moisture": ("", ""),
                "protein": ("", "12,5"),
            },
        )

        self.assertEqual(
            set(errors),
            {
                "delivery_date",
                "ticket_number",
                "gross_quantity",
                "base_price",
                "analysis:moisture:raw",
                "analysis:protein:corrected",
            },
        )

    def test_delivery_input_validation_accepts_german_numbers_and_date(self):
        errors = delivery_input_errors(
            delivery_date="8.10.26",
            ticket_number="WS-1",
            gross_quantity="10.000,5",
            base_price="200,00",
            features=(FeatureFormValue("moisture", "Feuchtigkeit"),),
            analyses={"moisture": ("14,5", "")},
        )

        self.assertEqual(errors, {})

    def test_zero_effect_rules_are_not_shown_as_adjustment_rows(self):
        preset = grain_rule_preset("wheat")
        form = GrainSettlementForm(
            supplier_number="L0001",
            features=preset.features,
            rules=preset.rules,
            deliveries=(
                self._delivery(
                    analyses=(
                        AnalysisFormValue("moisture", "14,5"),
                        AnalysisFormValue("dockage", "2,0"),
                    )
                ),
            ),
        )
        result = calculate_settlement_preview(form).delivery_results[0]
        view = GrainSettlementView.__new__(GrainSettlementView)
        view.features = form.features

        self.assertGreater(len(result.quantity_deductions), 0)
        self.assertEqual(view._adjustment_rows(result), ())

    def test_active_rule_makes_its_analysis_feature_required(self):
        features = (FeatureFormValue("protein", "Rohprotein", required=False),)
        active_rule = RuleFormValue(
            code="protein-price",
            label="Proteinabschlag",
            kind="tiered",
            feature_code="protein",
            quantity_reference="",
            tiers="..12=1 | 12..=0",
            phase="price_adjustment",
            price_reference="base_price",
            enabled=True,
        )

        normalized = require_features_used_by_active_rules(
            features,
            (active_rule,),
        )

        self.assertTrue(normalized[0].required)

    def test_missing_required_analyses_are_grouped_by_ticket(self):
        deliveries = (
            self._delivery(ticket_number="WS-1", analyses=()),
            self._delivery(
                id="delivery-2",
                ticket_number="WS-2",
                analyses=(AnalysisFormValue("protein", "12,5"),),
            ),
        )
        features = (FeatureFormValue("protein", "Rohprotein", required=True),)

        missing = missing_required_analyses(deliveries, features)

        self.assertEqual(missing, (("WS-1", ("Rohprotein",)),))


class GrainWorkspaceNavigationTests(unittest.TestCase):
    @staticmethod
    def _gui():
        gui = InvoiceGUI.__new__(InvoiceGUI)
        gui.active_workspace = "invoice"
        gui.form_host = Mock()
        gui.grain_view = Mock()
        gui.root = Mock()
        gui._refresh_application_menu = Mock()
        return gui

    def test_grain_workspace_hides_only_invoice_controls(self):
        gui = self._gui()

        gui._open_grain_workspace()

        self.assertEqual(gui.active_workspace, "grain")
        gui.form_host.grid_remove.assert_called_once_with()
        gui.grain_view.grid.assert_called_once_with()
        gui._refresh_application_menu.assert_called_once_with()

    def test_invoice_workspace_restores_existing_document_form(self):
        gui = self._gui()
        gui.invoice = Mock(is_self_billed=True)

        gui._activate_invoice_workspace()

        self.assertEqual(gui.active_workspace, "self_billed")
        gui.grain_view.grid_remove.assert_called_once_with()
        gui.form_host.grid.assert_called_once_with()
        gui._refresh_application_menu.assert_called_once_with()

    def test_same_document_workspace_does_not_create_a_new_document(self):
        gui = self._gui()
        gui.invoice = Mock(
            document_type=DocumentType.INVOICE,
            is_self_billed=False,
        )
        gui.controller = Mock()
        gui._activate_invoice_workspace = Mock()

        gui._open_document_workspace(DocumentType.INVOICE)

        gui._activate_invoice_workspace.assert_called_once_with()
        gui.controller.create_empty_invoice.assert_not_called()

    def test_application_menu_switches_to_grain_context(self):
        gui = InvoiceGUI.__new__(InvoiceGUI)
        gui.active_workspace = "grain"
        gui.file_menu = Mock()
        gui.document_menu = Mock()
        gui.master_data_menu = Mock()
        gui.workspace_variable = Mock()

        gui._refresh_application_menu()

        for index in (0, 2, 3):
            gui.file_menu.entryconfigure.assert_any_call(
                index,
                state="disabled",
            )
        gui.file_menu.entryconfigure.assert_any_call(
            5,
            state="disabled",
        )
        gui.file_menu.entryconfigure.assert_any_call(5, label="Speichern")
        gui.master_data_menu.entryconfigure.assert_any_call(
            0,
            label="Lieferantenliste",
        )
        gui.workspace_variable.set.assert_called_once_with("grain")


class GrainRuleSetSelectionTests(unittest.TestCase):
    def test_current_delivery_selects_its_own_rule_set(self):
        view = GrainSettlementView.__new__(GrainSettlementView)
        barley_delivery = GrainFormMapperTests._delivery(
            grain_type_code="barley"
        )
        wheat = ((FeatureFormValue("w", "Weizen"),), ())
        barley = ((FeatureFormValue("b", "Gerste"),), ())
        view.deliveries = [barley_delivery]
        view.rule_sets = {"wheat": wheat, "barley": barley}

        self.assertIs(view._current_rule_set(), barley)

    def test_missing_rule_set_is_initialized_from_matching_preset(self):
        view = GrainSettlementView.__new__(GrainSettlementView)
        view.deliveries = [
            GrainFormMapperTests._delivery(grain_type_code="maize")
        ]
        view.rule_sets = {}

        features, rules = view._current_rule_set()

        self.assertIn("maize", view.rule_sets)
        self.assertTrue(any(feature.code == "aflatoxin_b1" for feature in features))
        self.assertTrue(any(rule.code == "moisture-shrink" for rule in rules))


if __name__ == "__main__":
    unittest.main()
