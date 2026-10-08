"""GUI-unabhaengige Textextraktion aus vorhandenen PDF-Dokumenten."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re

import pypdfium2 as pdfium
from pypdfium2 import PdfiumError


DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024
DEFAULT_MAX_PAGES = 200
_AUTO_OCR = object()


class PdfImportError(ValueError):
    """Kontrollierter Fehler beim Oeffnen oder Validieren eines PDFs."""


class PdfPasswordError(PdfImportError):
    """Das PDF benoetigt ein Passwort oder das Passwort ist ungueltig."""


class ExtractionMethod(str, Enum):
    DIGITAL = "Digitale Textschicht"
    OCR = "OCR"
    DIGITAL_AND_OCR = "Textschicht und OCR"
    NONE = "Kein verwertbarer Text"
    ERROR = "Fehler"


@dataclass(frozen=True)
class PdfTextBlock:
    """Textausschnitt mit Koordinaten in PDF-Punkten."""

    text: str
    left: float
    bottom: float
    right: float
    top: float
    method: ExtractionMethod = ExtractionMethod.DIGITAL


@dataclass(frozen=True)
class PdfPageResult:
    page_number: int
    text: str
    method: ExtractionMethod
    blocks: tuple[PdfTextBlock, ...] = ()
    needs_ocr: bool = False
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class PdfImportResult:
    source_file: Path
    page_count: int
    pages: tuple[PdfPageResult, ...]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def page_texts(self) -> tuple[str, ...]:
        return tuple(page.text for page in self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(text for text in self.page_texts if text).strip()

    @property
    def methods(self) -> tuple[ExtractionMethod, ...]:
        return tuple(page.method for page in self.pages)

    @property
    def needs_ocr(self) -> bool:
        return any(page.needs_ocr for page in self.pages)


@dataclass(frozen=True)
class TextQuality:
    usable: bool
    alphanumeric_characters: int
    word_count: int
    suspicious_ratio: float
    reasons: tuple[str, ...] = field(default_factory=tuple)


class PdfImportService:
    """Liest digitale PDF-Textschichten ohne Persistenz oder GUI-Abhaengigkeit."""

    def __init__(
        self,
        *,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        ocr_engine=_AUTO_OCR,
    ):
        if max_file_size <= 0 or max_pages <= 0:
            raise ValueError("PDF-Grenzwerte muessen groesser als null sein.")
        self.max_file_size = max_file_size
        self.max_pages = max_pages
        if ocr_engine is _AUTO_OCR:
            from .tesseract_ocr_service import TesseractOcrEngine

            ocr_engine = TesseractOcrEngine()
        self.ocr_engine = ocr_engine

    def extract(self, filepath: str | Path, *, password: str | None = None) -> PdfImportResult:
        source = self._validate_source(filepath)

        try:
            document = pdfium.PdfDocument(source, password=password)
        except PdfiumError as exc:
            self._raise_open_error(exc)
        except (OSError, ValueError) as exc:
            raise PdfImportError("PDF-Datei konnte nicht geoeffnet werden.") from exc

        with document:
            page_count = len(document)
            if page_count == 0:
                raise PdfImportError("Das PDF enthaelt keine Seiten.")
            if page_count > self.max_pages:
                raise PdfImportError(
                    f"Das PDF hat {page_count} Seiten; erlaubt sind hoechstens "
                    f"{self.max_pages}."
                )

            pages = tuple(
                self._extract_page(document, page_index)
                for page_index in range(page_count)
            )

        warnings = tuple(
            warning
            for page in pages
            for warning in page.warnings
        )
        errors = tuple(
            error
            for page in pages
            for error in page.errors
        )
        return PdfImportResult(
            source_file=source,
            page_count=page_count,
            pages=pages,
            warnings=warnings,
            errors=errors,
        )

    def _validate_source(self, filepath: str | Path) -> Path:
        try:
            source = Path(filepath).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PdfImportError("PDF-Datei wurde nicht gefunden.") from exc

        if not source.is_file():
            raise PdfImportError("Der ausgewaehlte Pfad ist keine Datei.")

        try:
            size = source.stat().st_size
        except OSError as exc:
            raise PdfImportError("PDF-Dateigroesse konnte nicht ermittelt werden.") from exc

        if size == 0:
            raise PdfImportError("Die ausgewaehlte Datei ist leer.")
        if size > self.max_file_size:
            max_megabytes = self.max_file_size / (1024 * 1024)
            raise PdfImportError(
                f"Die PDF-Datei ist zu gross. Erlaubt sind hoechstens "
                f"{max_megabytes:g} MB."
            )
        return source

    @staticmethod
    def _raise_open_error(exc: PdfiumError) -> None:
        message = str(exc).lower()
        if "password" in message:
            raise PdfPasswordError(
                "Das PDF ist passwortgeschuetzt oder das Passwort ist ungueltig."
            ) from exc
        raise PdfImportError("Datei ist kein gueltiges oder lesbares PDF.") from exc

    def _extract_page(self, document, page_index: int) -> PdfPageResult:
        page_number = page_index + 1
        try:
            page = document.get_page(page_index)
            try:
                text_page = page.get_textpage()
                try:
                    text = self._normalize_text(text_page.get_text_bounded())
                    blocks = self._extract_blocks(text_page)
                finally:
                    text_page.close()

                quality = assess_text_quality(text)
                if quality.usable:
                    return PdfPageResult(
                        page_number=page_number,
                        text=text,
                        method=ExtractionMethod.DIGITAL,
                        blocks=blocks,
                    )

                reasons = ", ".join(quality.reasons) or "keine verwertbare Textstruktur"
                warning = f"Seite {page_number} benoetigt OCR: {reasons}."
                return self._extract_page_with_ocr(
                    page,
                    page_number=page_number,
                    digital_text=text,
                    digital_blocks=blocks,
                    initial_warning=warning,
                )
            finally:
                page.close()
        except Exception as exc:
            return PdfPageResult(
                page_number=page_number,
                text="",
                method=ExtractionMethod.ERROR,
                needs_ocr=True,
                errors=(f"Seite {page_number} konnte nicht gelesen werden: {type(exc).__name__}.",),
            )

    def _extract_page_with_ocr(
        self,
        page,
        *,
        page_number: int,
        digital_text: str,
        digital_blocks: tuple[PdfTextBlock, ...],
        initial_warning: str,
    ) -> PdfPageResult:
        if self.ocr_engine is None or not self.ocr_engine.is_available:
            return PdfPageResult(
                page_number=page_number,
                text=digital_text,
                method=ExtractionMethod.NONE,
                blocks=digital_blocks,
                needs_ocr=True,
                warnings=(
                    initial_warning,
                    f"Seite {page_number}: Tesseract oder deutsche Sprachdaten fehlen.",
                ),
            )

        try:
            ocr_data = self.ocr_engine.extract_page(page)
        except RuntimeError as exc:
            return PdfPageResult(
                page_number=page_number,
                text=digital_text,
                method=ExtractionMethod.NONE,
                blocks=digital_blocks,
                needs_ocr=True,
                warnings=(initial_warning,),
                errors=(f"OCR fuer Seite {page_number} ist fehlgeschlagen: {exc}",),
            )

        ocr_text = self._normalize_text(ocr_data.text)
        ocr_quality = assess_text_quality(ocr_text)
        if not ocr_quality.usable:
            reasons = ", ".join(ocr_quality.reasons) or "kein verwertbares Ergebnis"
            return PdfPageResult(
                page_number=page_number,
                text=ocr_text or digital_text,
                method=ExtractionMethod.NONE,
                blocks=ocr_data.blocks or digital_blocks,
                needs_ocr=False,
                warnings=(
                    initial_warning,
                    f"OCR fuer Seite {page_number} blieb unbrauchbar: {reasons}.",
                ),
            )

        method = (
            ExtractionMethod.DIGITAL_AND_OCR
            if digital_text
            else ExtractionMethod.OCR
        )
        return PdfPageResult(
            page_number=page_number,
            text=ocr_text,
            method=method,
            blocks=ocr_data.blocks,
            warnings=(initial_warning,),
        )

    def _extract_blocks(self, text_page) -> tuple[PdfTextBlock, ...]:
        blocks = []
        seen = set()
        rectangle_count = text_page.count_rects()

        for rectangle_index in range(rectangle_count):
            left, bottom, right, top = text_page.get_rect(rectangle_index)
            text = self._normalize_text(
                text_page.get_text_bounded(left, bottom, right, top)
            )
            if not text:
                continue
            key = (
                text,
                round(left, 3),
                round(bottom, 3),
                round(right, 3),
                round(top, 3),
            )
            if key in seen:
                continue
            seen.add(key)
            blocks.append(
                PdfTextBlock(
                    text=text,
                    left=left,
                    bottom=bottom,
                    right=right,
                    top=top,
                )
            )

        return tuple(blocks)

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        value = "\n".join(line.rstrip() for line in value.split("\n"))
        return value.strip()


def assess_text_quality(text: str) -> TextQuality:
    """Bewertet Textstruktur; eine reine Zeichenanzahl reicht bewusst nicht aus."""

    if not text.strip():
        return TextQuality(False, 0, 0, 1.0, ("keine Textschicht",))

    visible = [character for character in text if not character.isspace()]
    alphanumeric = sum(character.isalnum() for character in visible)
    suspicious = sum(
        character == "\ufffd"
        or (ord(character) < 32 and character not in "\n\t")
        for character in visible
    )
    suspicious_ratio = suspicious / len(visible) if visible else 1.0
    words = re.findall(r"[^\W_]{2,}", text, flags=re.UNICODE)

    reasons = []
    if alphanumeric < 4:
        reasons.append("zu wenig alphanumerischer Inhalt")
    if not words:
        reasons.append("keine erkennbare Wortstruktur")
    if suspicious_ratio > 0.10:
        reasons.append("zu viele ungueltige Zeichen")

    return TextQuality(
        usable=not reasons,
        alphanumeric_characters=alphanumeric,
        word_count=len(words),
        suspicious_ratio=suspicious_ratio,
        reasons=tuple(reasons),
    )


__all__ = [
    "ExtractionMethod",
    "PdfImportError",
    "PdfImportResult",
    "PdfImportService",
    "PdfPageResult",
    "PdfPasswordError",
    "PdfTextBlock",
    "TextQuality",
    "assess_text_quality",
]
