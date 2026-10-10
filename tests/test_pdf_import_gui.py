import queue
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from rechnungshelfer.gui.main_window import InvoiceGUI
from rechnungshelfer.gui.pdf_import_dialog import (
    PdfImportDialog,
    format_detected_fields,
    format_settlement_draft,
)
from rechnungshelfer.gui.test_document_dialog import TestDocumentDialog
from rechnungshelfer.domain.models import DocumentType
from rechnungshelfer.services.pdf_invoice_parser import (
    BUSINESS_PARTNER_NUMBER_PATH,
    DetectedInvoiceField,
)
from rechnungshelfer.services.settlement_credit_note_parser import DetectedValue


class PdfImportGuiTests(unittest.TestCase):
    @staticmethod
    def _value(value, confidence=0.91):
        return DetectedValue(
            value=value,
            raw_text=str(value),
            page_number=1,
            confidence=confidence,
        )

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

    def test_business_partner_number_label_follows_document_type(self):
        field = DetectedInvoiceField(
            path=BUSINESS_PARTNER_NUMBER_PATH,
            value="GP-100",
            confidence=0.95,
            page_number=1,
            source="Geschäftspartnernummer: GP-100",
        )

        invoice_lines = format_detected_fields([field], DocumentType.INVOICE)
        credit_note_lines = format_detected_fields(
            [field], DocumentType.SELF_BILLED_INVOICE
        )

        self.assertEqual(
            invoice_lines,
            ["Geschäftspartnernummer (Kunde): GP-100 (Seite 1, 95%)"],
        )
        self.assertEqual(
            credit_note_lines,
            [
                "Geschäftspartnernummer (Lieferant/Kreditor): GP-100 "
                "(Seite 1, 95%)"
            ],
        )

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

    def test_worker_cleans_up_generated_source_after_success_and_error(self):
        cleanup = MagicMock()
        controller = MagicMock()
        dialog = PdfImportDialog(MagicMock(), controller, MagicMock())
        dialog._results = queue.SimpleQueue()

        dialog._analyze(1, "testabrechnung.pdf", cleanup)
        cleanup.assert_called_once_with()

        cleanup.reset_mock()
        controller.analyze_pdf.side_effect = RuntimeError("OCR fehlgeschlagen")
        dialog._analyze(2, "testabrechnung.pdf", cleanup)
        cleanup.assert_called_once_with()
        self.assertEqual(dialog._results.get_nowait()[1], "result")
        self.assertEqual(dialog._results.get_nowait()[1], "error")

    def test_settlement_summary_shows_detected_values(self):
        number = self._value("91001", 0.93)
        delivery = SimpleNamespace(
            ticket_number=self._value("T1001", 0.89),
            net_amount=self._value(Decimal("402.72")),
        )
        draft = SimpleNamespace(
            credit_note_number=number,
            credit_note_date=self._value(date(2025, 11, 30)),
            deliveries=(delivery,),
            net_amount=self._value(Decimal("2087.53")),
            vat_rate=self._value(Decimal("7.8")),
            vat_amount=self._value(Decimal("162.83")),
            credit_amount=self._value(Decimal("2250.36")),
            warnings=(),
        )

        lines = format_settlement_draft(draft)

        self.assertIn("Gutschriftnummer: 91001", lines)
        self.assertTrue(any("Lieferschein T1001" in line for line in lines))
        self.assertTrue(any("2250.36" in line for line in lines))

    def test_recognized_settlement_is_not_converted_without_review(self):
        controller = MagicMock()
        dialog = PdfImportDialog(MagicMock(), controller, MagicMock())
        dialog.window = MagicMock()
        dialog.window.winfo_exists.return_value = True
        dialog._show_result = MagicMock()
        analysis = SimpleNamespace(settlement_draft=object())
        dialog._results.put((0, "result", analysis))

        dialog._poll_result()

        self.assertIs(dialog._analysis, analysis)
        self.assertIsNone(dialog._import)
        controller.create_invoice_from_pdf_analysis.assert_not_called()
        dialog._show_result.assert_called_once_with()

    def test_blocked_invoice_import_stays_in_review_without_conversion(self):
        controller = MagicMock()
        dialog = PdfImportDialog(MagicMock(), controller, MagicMock())
        dialog.window = MagicMock()
        dialog.window.winfo_exists.return_value = True
        dialog._show_result = MagicMock()
        draft = SimpleNamespace(errors=("Widerspruch",))
        analysis = SimpleNamespace(settlement_draft=None, draft=draft)
        dialog._results.put((0, "result", analysis))

        dialog._poll_result()

        self.assertIs(dialog._analysis, analysis)
        self.assertIsNone(dialog._import)
        controller.create_invoice_from_pdf_analysis.assert_not_called()
        dialog._show_result.assert_called_once_with()

    def test_recognized_settlement_opens_editable_review_dialog(self):
        controller = MagicMock()
        draft = object()
        dialog = PdfImportDialog(MagicMock(), controller, MagicMock())
        dialog.window = MagicMock()
        dialog._analysis = SimpleNamespace(settlement_draft=draft)

        with patch(
            "rechnungshelfer.gui.pdf_import_dialog.SettlementReviewDialog"
        ) as review_dialog_class:
            dialog._open_settlement_review()

        review_dialog_class.assert_called_once_with(
            dialog.window,
            controller,
            draft,
            dialog._open_grain_credit_note,
        )
        review_dialog_class.return_value.open.assert_called_once_with()
        self.assertIs(
            dialog._settlement_review_dialog,
            review_dialog_class.return_value,
        )

    def test_settlement_takeover_opens_grain_credit_note_workspace(self):
        invoice_callback = MagicMock()
        grain_callback = MagicMock()
        credit_note = object()
        dialog = PdfImportDialog(
            MagicMock(),
            MagicMock(),
            invoice_callback,
            grain_callback,
        )
        dialog.close = MagicMock()

        dialog._open_grain_credit_note(credit_note)

        dialog.close.assert_called_once_with()
        grain_callback.assert_called_once_with(credit_note)
        invoice_callback.assert_not_called()

    def test_test_document_dialog_forwards_ocr_selection(self):
        callback = MagicMock()
        dialog = TestDocumentDialog.__new__(TestDocumentDialog)
        dialog.on_ocr_test_selected = callback
        dialog.close = MagicMock()

        dialog._select_ocr_test()

        dialog.close.assert_called_once_with()
        callback.assert_called_once_with()

    def test_main_window_opens_temporary_ocr_document_with_cleanup(self):
        gui = InvoiceGUI.__new__(InvoiceGUI)
        gui.root = MagicMock()
        gui.pdf_import_dialog = MagicMock()

        with (
            patch(
                "rechnungshelfer.gui.main_window.create_temporary_test_settlement_pdf",
                return_value="C:/Temp/testabrechnung.pdf",
            ),
            patch(
                "rechnungshelfer.gui.main_window.remove_temporary_test_settlement_pdf"
            ) as remove,
        ):
            gui._open_ocr_test_document()
            cleanup = gui.pdf_import_dialog.open.call_args.kwargs["source_cleanup"]
            cleanup()

        gui.pdf_import_dialog.open.assert_called_once()
        remove.assert_called_once_with("C:/Temp/testabrechnung.pdf")

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
