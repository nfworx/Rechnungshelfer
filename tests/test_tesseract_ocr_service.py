import subprocess
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from rechnungshelfer.services.pdf_import_service import (
    ExtractionMethod,
    PdfImportService,
)
from rechnungshelfer.services.tesseract_ocr_service import (
    OcrExecutionError,
    TESSERACT_PATH_ENV,
    TesseractOcrEngine,
    TesseractRuntime,
    resolve_tesseract_runtime,
)


TSV_RESULT = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
1\t1\t0\t0\t0\t0\t0\t0\t1000\t1000\t-1\t
5\t1\t1\t1\t1\t1\t100\t200\t180\t40\t96.1\tGescannte
5\t1\t1\t1\t1\t2\t300\t200\t160\t40\t92.0\tRechnung
5\t1\t1\t1\t2\t1\t100\t280\t120\t40\t89.5\t4711
"""
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TesseractRuntimeTests(unittest.TestCase):
    def test_explicit_runtime_has_priority_and_finds_tessdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = root / "custom" / "tesseract.exe"
            explicit.parent.mkdir()
            explicit.write_bytes(b"runtime")
            (explicit.parent / "tessdata").mkdir()

            runtime = resolve_tesseract_runtime(
                explicit,
                root=root,
                environ={TESSERACT_PATH_ENV: str(root / "anderer-pfad")},
                path_lookup=lambda _name: None,
            )

        self.assertEqual(runtime.executable, explicit.resolve())
        self.assertEqual(runtime.tessdata_dir, (explicit.parent / "tessdata").resolve())

    def test_uses_configured_environment_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            runtime_dir.mkdir()
            executable = runtime_dir / "tesseract.exe"
            executable.write_bytes(b"runtime")

            with patch("rechnungshelfer.services.tesseract_ocr_service.os.name", "nt"):
                runtime = resolve_tesseract_runtime(
                    root=root,
                    environ={TESSERACT_PATH_ENV: str(runtime_dir)},
                    path_lookup=lambda _name: None,
                )

        self.assertEqual(runtime.executable, executable.resolve())

    def test_returns_none_when_no_runtime_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = resolve_tesseract_runtime(
                root=tmp,
                environ={},
                path_lookup=lambda _name: None,
            )

        self.assertIsNone(runtime)


class TesseractOcrEngineTests(unittest.TestCase):
    def _runtime(self, root: Path):
        executable = root / "tesseract.exe"
        executable.write_bytes(b"runtime")
        tessdata = root / "tessdata"
        tessdata.mkdir()
        (tessdata / "deu.traineddata").write_bytes(b"language")
        return TesseractRuntime(executable=executable, tessdata_dir=tessdata)

    def _blank_pdf(self, path: Path):
        document = canvas.Canvas(str(path))
        document.showPage()
        document.save()

    def _mixed_pdf(self, path: Path):
        document = canvas.Canvas(str(path))
        document.drawString(72, 760, "Digitale erste Rechnungsseite")
        document.showPage()
        document.showPage()
        document.save()

    def test_ocr_fallback_extracts_text_and_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "scan.pdf"
            self._blank_pdf(pdf_path)
            runtime = self._runtime(root)
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                self.assertTrue(kwargs["input"].startswith(b"\x89PNG"))
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=TSV_RESULT.encode("utf-8"),
                    stderr=b"",
                )

            engine = TesseractOcrEngine(runtime, dpi=300, runner=runner)
            result = PdfImportService(ocr_engine=engine).extract(pdf_path)

        page = result.pages[0]
        self.assertEqual(page.method, ExtractionMethod.OCR)
        self.assertEqual(page.text, "Gescannte Rechnung\n4711")
        self.assertEqual([block.text for block in page.blocks], ["Gescannte", "Rechnung", "4711"])
        self.assertTrue(all(block.method is ExtractionMethod.OCR for block in page.blocks))
        self.assertTrue(all(block.left < block.right for block in page.blocks))
        self.assertEqual(
            [block.confidence for block in page.blocks],
            [0.961, 0.92, 0.895],
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["env"]["TESSDATA_PREFIX"], str(runtime.tessdata_dir))

    def test_mixed_pdf_only_uses_ocr_for_page_without_usable_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "gemischt.pdf"
            self._mixed_pdf(pdf_path)
            runtime = self._runtime(root)
            call_count = 0

            def runner(command, **kwargs):
                nonlocal call_count
                call_count += 1
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=TSV_RESULT.encode("utf-8"),
                    stderr=b"",
                )

            engine = TesseractOcrEngine(runtime, runner=runner)
            result = PdfImportService(ocr_engine=engine).extract(pdf_path)

        self.assertEqual(result.methods, (ExtractionMethod.DIGITAL, ExtractionMethod.OCR))
        self.assertEqual(call_count, 1)

    def test_oversized_render_is_rejected_before_tesseract_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "scan.pdf"
            self._blank_pdf(pdf_path)
            runtime = self._runtime(root)

            def runner(*_args, **_kwargs):
                self.fail("Tesseract darf bei ueberschrittener Pixelgrenze nicht starten")

            engine = TesseractOcrEngine(runtime, max_pixels=100, runner=runner)
            result = PdfImportService(ocr_engine=engine).extract(pdf_path)

        self.assertTrue(result.errors)
        self.assertIn("zu gross", result.errors[0])

    def test_timeout_is_reported_as_controlled_page_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "scan.pdf"
            self._blank_pdf(pdf_path)
            runtime = self._runtime(root)

            def runner(command, **kwargs):
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])

            engine = TesseractOcrEngine(runtime, timeout=1, runner=runner)
            result = PdfImportService(ocr_engine=engine).extract(pdf_path)

        self.assertTrue(result.errors)
        self.assertIn("abgebrochen", result.errors[0])

    def test_missing_language_data_disables_ocr_without_breaking_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "scan.pdf"
            self._blank_pdf(pdf_path)
            executable = root / "tesseract.exe"
            executable.write_bytes(b"runtime")
            tessdata = root / "tessdata"
            tessdata.mkdir()
            engine = TesseractOcrEngine(
                TesseractRuntime(executable=executable, tessdata_dir=tessdata)
            )

            result = PdfImportService(ocr_engine=engine).extract(pdf_path)

        self.assertEqual(result.pages[0].method, ExtractionMethod.NONE)
        self.assertTrue(result.pages[0].needs_ocr)
        self.assertTrue(any("Sprachdaten fehlen" in item for item in result.warnings))

    def test_failed_ocr_is_reported_without_document_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "scan.pdf"
            self._blank_pdf(pdf_path)
            runtime = self._runtime(root)

            def runner(command, **kwargs):
                return subprocess.CompletedProcess(
                    command,
                    2,
                    stdout=b"",
                    stderr=b"sensitive document output",
                )

            engine = TesseractOcrEngine(runtime, runner=runner)
            result = PdfImportService(ocr_engine=engine).extract(pdf_path)

        self.assertEqual(result.pages[0].method, ExtractionMethod.NONE)
        self.assertTrue(result.errors)
        self.assertNotIn("sensitive", result.errors[0])
        self.assertIn("Fehlercode 2", result.errors[0])

    def test_invalid_tsv_raises_controlled_error(self):
        with self.assertRaises(OcrExecutionError):
            TesseractOcrEngine._parse_tsv(
                "kein\tgueltiger\tkopf\n",
                page_height=800,
                scale=1,
            )

    @unittest.skipUnless(
        (PROJECT_ROOT / "external" / "tesseract" / "tesseract.exe").is_file(),
        "Portable Tesseract-Laufzeit ist nicht installiert.",
    )
    def test_real_portable_runtime_recognizes_scanned_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "echter-scan.pdf"
            image = Image.new("RGB", (1800, 500), "white")
            font = ImageFont.truetype(
                str(PROJECT_ROOT / "assets" / "fonts" / "LMRoman10-Bold.ttf"),
                110,
            )
            ImageDraw.Draw(image).text(
                (100, 150),
                "RECHNUNG 4711",
                font=font,
                fill="black",
            )
            image_data = BytesIO()
            image.save(image_data, format="PNG")
            image_data.seek(0)
            document = canvas.Canvas(str(pdf_path), pagesize=(900, 250))
            document.drawImage(ImageReader(image_data), 0, 0, width=900, height=250)
            document.showPage()
            document.save()

            result = PdfImportService().extract(pdf_path)

        self.assertEqual(result.pages[0].method, ExtractionMethod.OCR)
        self.assertIn("4711", result.full_text)


if __name__ == "__main__":
    unittest.main()
