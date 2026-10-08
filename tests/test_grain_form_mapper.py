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
    calculate_settlement_preview,
    parse_parameters,
    parse_tiers,
)
from rechnungshelfer.gui.main_window import InvoiceGUI


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


if __name__ == "__main__":
    unittest.main()
