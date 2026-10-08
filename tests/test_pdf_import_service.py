import tempfile
import unittest
from pathlib import Path

from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

from rechnungshelfer.services.pdf_import_service import (
    ExtractionMethod,
    PdfImportError,
    PdfImportService,
    PdfPasswordError,
    assess_text_quality,
    normalize_ocr_text,
)


class PdfImportServiceTests(unittest.TestCase):
    def test_normalizes_embedded_tsv_rows_to_plain_ocr_lines(self):
        raw = (
            "MusterstraÃŸe 32\n"
            "5\t1\t17\t1\t6\t1\t421\t2013\t332\t46\t89.8\tLieferschein-Nr.:\n"
            "5\t1\t17\t1\t6\t2\t789\t1999\t194\t53\t89.2\t3076/RW\n"
            "5\t1\t17\t1\t6\t3\t1011\t2023\t87\t27\t92.6\tvom\n"
            "5\t1\t17\t1\t6\t4\t1138\t2014\t227\t36\t90.4\t14.08.2025\n"
            "4\t1\t17\t1\t7\t0\t459\t2063\t1680\t106\t-1\t\n"
        )

        normalized = normalize_ocr_text(raw)

        self.assertIn("Musterstraße 32", normalized)
        self.assertIn("Lieferschein-Nr.: 3076/RW vom 14.08.2025", normalized)
        self.assertNotIn("\t17\t", normalized)

    def _create_pdf(self, path: Path, page_texts, *, encrypt=None, subject=None):
        document = canvas.Canvas(str(path), encrypt=encrypt)
        if subject:
            document.setSubject(subject)
        for text in page_texts:
            if text:
                document.drawString(72, 760, text)
            document.showPage()
        document.save()

    def test_extracts_digital_text_from_all_pages_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mehrseitig.pdf"
            self._create_pdf(path, ["Rechnung Nummer 123", "Zweite Seite Gesamtbetrag"])

            result = PdfImportService().extract(path)

        self.assertEqual(result.page_count, 2)
        self.assertEqual(result.methods, (ExtractionMethod.DIGITAL, ExtractionMethod.DIGITAL))
        self.assertIn("Rechnung Nummer 123", result.page_texts[0])
        self.assertIn("Zweite Seite Gesamtbetrag", result.page_texts[1])
        self.assertLess(result.full_text.index("Rechnung"), result.full_text.index("Zweite"))
        self.assertFalse(result.needs_ocr)

    def test_returns_positioned_text_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bloecke.pdf"
            self._create_pdf(path, ["Rechnungsnummer 4711"])

            result = PdfImportService().extract(path)

        blocks = result.pages[0].blocks
        self.assertTrue(blocks)
        self.assertTrue(any("4711" in block.text for block in blocks))
        self.assertTrue(all(block.left < block.right for block in blocks))
        self.assertTrue(all(block.bottom < block.top for block in blocks))

    def test_extracts_document_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadaten.pdf"
            self._create_pdf(path, ["Rechnung"], subject="Importdaten")

            result = PdfImportService().extract(path)

        self.assertEqual(result.metadata["Subject"], "Importdaten")

    def test_marks_page_without_text_for_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gemischt.pdf"
            self._create_pdf(path, ["Digitale Rechnungsseite", ""])

            result = PdfImportService(ocr_engine=None).extract(path)

        self.assertEqual(result.pages[0].method, ExtractionMethod.DIGITAL)
        self.assertEqual(result.pages[1].method, ExtractionMethod.NONE)
        self.assertTrue(result.pages[1].needs_ocr)
        self.assertTrue(result.needs_ocr)
        self.assertIn("Seite 2", result.warnings[0])

    def test_rejects_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "defekt.pdf"
            path.write_bytes(b"Das ist kein PDF")

            with self.assertRaisesRegex(PdfImportError, "gueltiges|lesbares"):
                PdfImportService().extract(path)

    def test_rejects_password_protected_file_without_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "geschuetzt.pdf"
            encryption = StandardEncryption("geheim", canCopy=0, canPrint=0)
            self._create_pdf(path, ["Vertrauliche Rechnung"], encrypt=encryption)

            with self.assertRaises(PdfPasswordError):
                PdfImportService().extract(path)

            result = PdfImportService().extract(path, password="geheim")

        self.assertIn("Vertrauliche Rechnung", result.full_text)

    def test_rejects_files_above_configured_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "zu-gross.pdf"
            self._create_pdf(path, ["Rechnung"])

            with self.assertRaisesRegex(PdfImportError, "zu gross"):
                PdfImportService(max_file_size=10).extract(path)

    def test_releases_file_handle_after_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "freigabe.pdf"
            moved = Path(tmp) / "verschoben.pdf"
            self._create_pdf(path, ["Dateihandle wird freigegeben"])

            PdfImportService().extract(path)
            path.rename(moved)

            self.assertTrue(moved.is_file())

    def test_quality_check_uses_structure_and_invalid_characters(self):
        self.assertTrue(assess_text_quality("Rechnung 12345").usable)
        self.assertFalse(assess_text_quality("123").usable)
        self.assertFalse(assess_text_quality("\ufffd\ufffd\ufffd\ufffd Text").usable)


if __name__ == "__main__":
    unittest.main()
