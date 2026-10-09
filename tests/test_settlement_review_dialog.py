import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from rechnungshelfer.gui.settlement_review_dialog import SettlementReviewDialog


class SettlementReviewDialogTests(unittest.TestCase):
    @staticmethod
    def _dialog(valid=True):
        dialog = SettlementReviewDialog.__new__(SettlementReviewDialog)
        dialog.window = MagicMock()
        dialog.controller = MagicMock()
        dialog.review = object()
        dialog.on_invoice_loaded = MagicMock()
        dialog.validate = MagicMock(return_value=SimpleNamespace(is_valid=valid))
        dialog.close = MagicMock()
        return dialog

    def test_valid_review_is_transferred_after_confirmation(self):
        dialog = self._dialog()
        invoice = object()
        dialog.controller.create_invoice_from_settlement_review.return_value = invoice

        with patch(
            "rechnungshelfer.gui.settlement_review_dialog.messagebox.askyesno",
            return_value=True,
        ):
            result = dialog.apply_to_form()

        self.assertTrue(result)
        dialog.controller.create_invoice_from_settlement_review.assert_called_once_with(
            dialog.review
        )
        dialog.close.assert_called_once_with()
        dialog.on_invoice_loaded.assert_called_once_with(invoice)

    def test_invalid_review_is_not_transferred(self):
        dialog = self._dialog(valid=False)

        with patch(
            "rechnungshelfer.gui.settlement_review_dialog.messagebox.askyesno"
        ) as confirm:
            result = dialog.apply_to_form()

        self.assertFalse(result)
        confirm.assert_not_called()
        dialog.controller.create_invoice_from_settlement_review.assert_not_called()
        dialog.on_invoice_loaded.assert_not_called()

    def test_declined_confirmation_keeps_review_open(self):
        dialog = self._dialog()

        with patch(
            "rechnungshelfer.gui.settlement_review_dialog.messagebox.askyesno",
            return_value=False,
        ):
            result = dialog.apply_to_form()

        self.assertFalse(result)
        dialog.controller.create_invoice_from_settlement_review.assert_not_called()
        dialog.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
