import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from rechnungshelfer.application.settlement_review_service import (
    SettlementReviewIssue,
    SettlementReviewResult,
)
from rechnungshelfer.gui.settlement_review_dialog import SettlementReviewDialog


class SettlementReviewDialogTests(unittest.TestCase):
    @staticmethod
    def _dialog(valid=True):
        dialog = SettlementReviewDialog.__new__(SettlementReviewDialog)
        dialog.window = MagicMock()
        dialog.controller = MagicMock()
        dialog.review = object()
        dialog.edit_mode = False
        dialog.on_credit_note_loaded = MagicMock()
        dialog.validate = MagicMock(return_value=SimpleNamespace(is_valid=valid))
        dialog.close = MagicMock()
        return dialog

    def test_valid_review_is_transferred_after_confirmation(self):
        dialog = self._dialog()
        credit_note = object()
        dialog.controller.create_grain_credit_note_from_review.return_value = (
            credit_note
        )

        with patch(
            "rechnungshelfer.gui.settlement_review_dialog.messagebox.askyesno",
            return_value=True,
        ):
            result = dialog.apply_to_form()

        self.assertTrue(result)
        dialog.controller.create_grain_credit_note_from_review.assert_called_once_with(
            dialog.review
        )
        dialog.close.assert_called_once_with()
        dialog.on_credit_note_loaded.assert_called_once_with(credit_note)

    def test_invalid_review_is_not_transferred(self):
        dialog = self._dialog(valid=False)

        with patch(
            "rechnungshelfer.gui.settlement_review_dialog.messagebox.askyesno"
        ) as confirm:
            result = dialog.apply_to_form()

        self.assertFalse(result)
        confirm.assert_not_called()
        dialog.controller.create_grain_credit_note_from_review.assert_not_called()
        dialog.on_credit_note_loaded.assert_not_called()

    def test_declined_confirmation_keeps_review_open(self):
        dialog = self._dialog()

        with patch(
            "rechnungshelfer.gui.settlement_review_dialog.messagebox.askyesno",
            return_value=False,
        ):
            result = dialog.apply_to_form()

        self.assertFalse(result)
        dialog.controller.create_grain_credit_note_from_review.assert_not_called()
        dialog.close.assert_not_called()

    def test_blocking_difference_marks_field_and_disables_transfer(self):
        dialog = SettlementReviewDialog.__new__(SettlementReviewDialog)
        entry = MagicMock()
        dialog.entries = {"net_amount": entry}
        dialog.review = SimpleNamespace(
            net_amount=SimpleNamespace(confidence=None),
        )
        dialog.controller = MagicMock()
        dialog.controller.compare_settlement_review.return_value = dialog.review
        issue = SettlementReviewIssue(
            "net_amount",
            "Nettosumme – Belegwert: 10,00 EUR; Prüfwert: 12,00 EUR; "
            "Differenz (Belegwert − Prüfwert): -2,00 EUR.",
        )
        dialog.controller.validate_settlement_review.return_value = (
            SettlementReviewResult((issue,))
        )
        dialog.collect_review = MagicMock(return_value=dialog.review)
        dialog._set_status = MagicMock()
        dialog.transfer_button = MagicMock()

        result = dialog.validate()

        self.assertFalse(result.is_valid)
        entry.configure.assert_any_call(border_color="#ef4444", border_width=2)
        dialog._set_status.assert_called_once()
        self.assertIn("BLOCKIERT:", dialog._set_status.call_args.args[0])
        dialog.transfer_button.configure.assert_called_once_with(state="disabled")


if __name__ == "__main__":
    unittest.main()
