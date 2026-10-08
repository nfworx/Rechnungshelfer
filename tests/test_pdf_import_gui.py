import queue
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from rechnungshelfer.gui.main_window import InvoiceGUI
from rechnungshelfer.gui.pdf_import_dialog import PdfImportDialog, format_detected_fields
from rechnungshelfer.services.pdf_invoice_parser import DetectedInvoiceField


class PdfImportGuiTests(unittest.TestCase):
    def test_detected_fields_are_presented_with_source_page_and_confidence(self):
        lines = format_detected_fields(
            [
                DetectedInvoiceField(
                    path="info.invoice_number",
                    value="RE-101",
                    confidence=0.98,
                    page_number=2,
                    source="Rechnungsnummer: RE-101",
                )
            ]
        )

        self.assertEqual(lines, ["Belegnummer: RE-101 (Seite 2, 98%)"])

    def test_file_selection_opens_pdf_dialog(self):
        gui = InvoiceGUI.__new__(InvoiceGUI)
        gui.root = MagicMock()
        gui.pdf_import_dialog = MagicMock()

        with patch(
            "rechnungshelfer.gui.main_window.filedialog.askopenfilename",
            return_value="rechnung.pdf",
        ):
            gui.load_pdf()

        gui.pdf_import_dialog.open.assert_called_once_with("rechnung.pdf")

    def test_cancelled_file_selection_does_nothing(self):
        gui = InvoiceGUI.__new__(InvoiceGUI)
        gui.root = MagicMock()
        gui.pdf_import_dialog = MagicMock()

        with patch(
            "rechnungshelfer.gui.main_window.filedialog.askopenfilename",
            return_value="",
        ):
            gui.load_pdf()

        gui.pdf_import_dialog.open.assert_not_called()

    def test_worker_only_analyzes_and_queues_result(self):
        controller = MagicMock()
        analysis = object()
        controller.analyze_pdf.return_value = analysis
        dialog = PdfImportDialog(MagicMock(), controller, MagicMock())
        dialog._filepath = "rechnung.pdf"
        dialog._results = queue.SimpleQueue()

        dialog._analyze(7, "rechnung.pdf")

        self.assertEqual(dialog._results.get_nowait(), (7, "result", analysis))
        controller.create_invoice_from_pdf_analysis.assert_not_called()

    def test_form_takeover_requires_confirmation_and_does_not_save(self):
        controller = MagicMock()
        callback = MagicMock()
        invoice = object()
        dialog = PdfImportDialog(MagicMock(), controller, callback)
        dialog.window = MagicMock()
        dialog._import = SimpleNamespace(invoice=invoice)
        dialog.close = MagicMock()

        with patch(
            "rechnungshelfer.gui.pdf_import_dialog.messagebox.askyesno",
            return_value=True,
        ):
            dialog._apply_to_form()

        callback.assert_called_once_with(invoice)
        controller.save_invoice.assert_not_called()

    def test_declined_form_takeover_keeps_dialog_open(self):
        callback = MagicMock()
        dialog = PdfImportDialog(MagicMock(), MagicMock(), callback)
        dialog.window = MagicMock()
        dialog._import = SimpleNamespace(invoice=object())
        dialog.close = MagicMock()

        with patch(
            "rechnungshelfer.gui.pdf_import_dialog.messagebox.askyesno",
            return_value=False,
        ):
            dialog._apply_to_form()

        callback.assert_not_called()
        dialog.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
