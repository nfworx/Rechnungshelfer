import unittest
from unittest.mock import Mock, patch

from rechnungshelfer.gui.grain_credit_note_load_dialog import (
    GrainCreditNoteLoadDialog,
)


class GrainCreditNoteLoadDialogTests(unittest.TestCase):
    def test_selected_note_is_loaded_and_dialog_is_closed(self):
        dialog = GrainCreditNoteLoadDialog.__new__(GrainCreditNoteLoadDialog)
        note = object()
        dialog.controller = Mock()
        dialog.controller.load_grain_credit_note.return_value = note
        dialog.on_loaded = Mock()
        dialog.close = Mock()
        dialog.window = Mock()

        loaded = dialog.load("91001")

        self.assertTrue(loaded)
        dialog.controller.load_grain_credit_note.assert_called_once_with("91001")
        dialog.on_loaded.assert_called_once_with(note)
        dialog.close.assert_called_once_with()

    def test_missing_selection_does_not_load(self):
        dialog = GrainCreditNoteLoadDialog.__new__(GrainCreditNoteLoadDialog)
        dialog.selected_number = None
        dialog.window = Mock()

        with patch(
            "rechnungshelfer.gui.grain_credit_note_load_dialog.messagebox.showwarning"
        ) as warning:
            loaded = dialog.load_selected()

        self.assertFalse(loaded)
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
