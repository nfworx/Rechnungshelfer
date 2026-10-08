"""Offline-OCR mit einer optional mitgelieferten Tesseract-Laufzeit."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import BytesIO, StringIO
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .pdf_import_service import ExtractionMethod, PdfTextBlock


TESSERACT_PATH_ENV = "RECHNUNGSHELFER_TESSERACT"
DEFAULT_OCR_DPI = 300
DEFAULT_OCR_TIMEOUT = 90
DEFAULT_MAX_OCR_PIXELS = 40_000_000


class OcrExecutionError(RuntimeError):
    """Kontrollierter Fehler einer OCR-Ausfuehrung."""


@dataclass(frozen=True)
class TesseractRuntime:
    executable: Path
    tessdata_dir: Path | None = None


@dataclass(frozen=True)
class OcrPageData:
    text: str
    blocks: tuple[PdfTextBlock, ...]


def application_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def resolve_tesseract_runtime(
    configured_path: str | Path | None = None,
    *,
    root: str | Path | None = None,
    environ: dict[str, str] | None = None,
    path_lookup=shutil.which,
) -> TesseractRuntime | None:
    """Loest expliziten, konfigurierten, gebuendelten und Systempfad auf."""

    environ = os.environ if environ is None else environ
    root = Path(root) if root is not None else application_root()
    executable_name = "tesseract.exe" if os.name == "nt" else "tesseract"
    candidates = []

    if configured_path:
        candidates.append(Path(configured_path))
    if environ.get(TESSERACT_PATH_ENV):
        candidates.append(Path(environ[TESSERACT_PATH_ENV]))
    candidates.append(root / "external" / "tesseract" / executable_name)

    system_executable = path_lookup("tesseract")
    if system_executable:
        candidates.append(Path(system_executable))

    seen = set()
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.is_dir():
            candidate = candidate / executable_name
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        normalized = os.path.normcase(str(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        if not candidate.is_file():
            continue
        tessdata = candidate.parent / "tessdata"
        return TesseractRuntime(
            executable=candidate,
            tessdata_dir=tessdata if tessdata.is_dir() else None,
        )

    return None


class TesseractOcrEngine:
    """Rendert einzelne PDF-Seiten und uebergibt sie per stdin an Tesseract."""

    def __init__(
        self,
        runtime: TesseractRuntime | None = None,
        *,
        language: str = "deu",
        dpi: int = DEFAULT_OCR_DPI,
        timeout: int = DEFAULT_OCR_TIMEOUT,
        max_pixels: int = DEFAULT_MAX_OCR_PIXELS,
        runner=subprocess.run,
    ):
        if dpi < 72:
            raise ValueError("OCR-Aufloesung muss mindestens 72 DPI betragen.")
        if timeout <= 0:
            raise ValueError("OCR-Timeout muss groesser als null sein.")
        if max_pixels <= 0:
            raise ValueError("OCR-Pixelgrenze muss groesser als null sein.")
        self.runtime = runtime if runtime is not None else resolve_tesseract_runtime()
        self.language = language
        self.dpi = dpi
        self.timeout = timeout
        self.max_pixels = max_pixels
        self._runner = runner

    @property
    def is_available(self) -> bool:
        if self.runtime is None or not self.runtime.executable.is_file():
            return False
        if self.runtime.tessdata_dir is None:
            return True
        languages = [item.strip() for item in self.language.split("+") if item.strip()]
        return all(
            (self.runtime.tessdata_dir / f"{language}.traineddata").is_file()
            for language in languages
        )

    def extract_page(self, page) -> OcrPageData:
        if not self.is_available:
            raise OcrExecutionError("Tesseract oder die benoetigten Sprachdaten fehlen.")

        scale = self.dpi / 72
        pixel_count = (page.get_width() * scale) * (page.get_height() * scale)
        if pixel_count > self.max_pixels:
            raise OcrExecutionError(
                "Seite ist fuer die konfigurierte OCR-Aufloesung zu gross."
            )
        bitmap = page.render(scale=scale)
        try:
            image = bitmap.to_pil()
            payload = BytesIO()
            image.save(payload, format="PNG")
            png_data = payload.getvalue()
        finally:
            bitmap.close()

        command = [
            str(self.runtime.executable),
            "stdin",
            "stdout",
            "-l",
            self.language,
            "--dpi",
            str(self.dpi),
            "tsv",
        ]
        environment = os.environ.copy()
        if self.runtime.tessdata_dir is not None:
            environment["TESSDATA_PREFIX"] = str(self.runtime.tessdata_dir)

        try:
            completed = self._runner(
                command,
                input=png_data,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                check=False,
                env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrExecutionError(
                f"OCR wurde nach {self.timeout} Sekunden abgebrochen."
            ) from exc
        except OSError as exc:
            raise OcrExecutionError("Tesseract konnte nicht gestartet werden.") from exc

        if completed.returncode != 0:
            raise OcrExecutionError(
                f"Tesseract wurde mit Fehlercode {completed.returncode} beendet."
            )

        try:
            tsv = completed.stdout.decode("utf-8", errors="replace")
        except AttributeError as exc:
            raise OcrExecutionError("Tesseract lieferte keine gueltigen Ausgabedaten.") from exc
        return self._parse_tsv(tsv, page_height=float(page.get_height()), scale=scale)

    @staticmethod
    def _parse_tsv(tsv: str, *, page_height: float, scale: float) -> OcrPageData:
        words = []
        blocks = []
        lines = {}

        try:
            rows = csv.DictReader(StringIO(tsv), delimiter="\t")
            required = {
                "level", "block_num", "par_num", "line_num", "left", "top",
                "width", "height", "conf", "text",
            }
            if rows.fieldnames is None or not required.issubset(rows.fieldnames):
                raise ValueError("TSV-Kopf fehlt")

            for row in rows:
                text = (row.get("text") or "").strip()
                if row.get("level") != "5" or not text:
                    continue
                confidence = float(row.get("conf") or -1)
                if confidence < 0:
                    continue
                left_px = int(row["left"])
                top_px = int(row["top"])
                width_px = int(row["width"])
                height_px = int(row["height"])
                left = left_px / scale
                right = (left_px + width_px) / scale
                top = page_height - (top_px / scale)
                bottom = page_height - ((top_px + height_px) / scale)
                blocks.append(
                    PdfTextBlock(
                        text=text,
                        left=left,
                        bottom=bottom,
                        right=right,
                        top=top,
                        method=ExtractionMethod.OCR,
                    )
                )
                line_key = (
                    row.get("block_num", "0"),
                    row.get("par_num", "0"),
                    row.get("line_num", "0"),
                )
                lines.setdefault(line_key, []).append(text)
                words.append(text)
        except (TypeError, ValueError, KeyError) as exc:
            raise OcrExecutionError("Tesseract lieferte ungueltige TSV-Daten.") from exc

        if not words:
            return OcrPageData(text="", blocks=())
        text = "\n".join(" ".join(line_words) for line_words in lines.values())
        return OcrPageData(text=text, blocks=tuple(blocks))


__all__ = [
    "DEFAULT_OCR_DPI",
    "DEFAULT_MAX_OCR_PIXELS",
    "DEFAULT_OCR_TIMEOUT",
    "OcrExecutionError",
    "OcrPageData",
    "TESSERACT_PATH_ENV",
    "TesseractOcrEngine",
    "TesseractRuntime",
    "application_root",
    "resolve_tesseract_runtime",
]
