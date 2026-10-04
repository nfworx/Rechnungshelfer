"""Lebenszyklus temporaerer HTML-Pruefberichte."""

from __future__ import annotations

import atexit
import os
import tempfile
import threading
from pathlib import Path


REPORT_PREFIX = "rechnungshelfer-pruefbericht-"
LEGACY_REPORT_PREFIX = "xrechnung_pruefbericht_"

_created_reports: set[Path] = set()
_lock = threading.Lock()


def _temp_directory(directory: Path | None = None) -> Path:
    return Path(directory) if directory is not None else Path(tempfile.gettempdir())


def create_temp_report(html_content: str, *, directory: Path | None = None) -> Path:
    """Schreibt einen Bericht und merkt ihn fuer die Bereinigung dieser Sitzung vor."""
    temp_dir = _temp_directory(directory)
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        errors="replace",
        prefix=f"{REPORT_PREFIX}{os.getpid()}-",
        suffix=".html",
        dir=temp_dir,
        delete=False,
    ) as report_file:
        report_file.write(html_content)
        report_path = Path(report_file.name).resolve()
    with _lock:
        _created_reports.add(report_path)
    return report_path


def _remove(paths: list[Path]) -> int:
    removed = 0
    for path in paths:
        try:
            existed = path.exists()
            path.unlink(missing_ok=True)
            if existed:
                removed += 1
        except OSError:
            # Ein Browser kann die Datei unter Windows kurzzeitig sperren. Der
            # naechste Programmstart versucht die Bereinigung erneut.
            continue
    return removed


def cleanup_current_temp_reports() -> int:
    """Entfernt alle in dieser Programmsitzung erzeugten Berichte."""
    with _lock:
        paths = list(_created_reports)
        _created_reports.clear()
    return _remove(paths)


def cleanup_stale_temp_reports(*, directory: Path | None = None) -> int:
    """Entfernt eindeutig benannte Berichte aus frueheren Sitzungen."""
    temp_dir = _temp_directory(directory)
    paths: set[Path] = set()
    for pattern in (f"{REPORT_PREFIX}*.html", f"{LEGACY_REPORT_PREFIX}*.html"):
        try:
            paths.update(path.resolve() for path in temp_dir.glob(pattern) if path.is_file())
        except OSError:
            continue
    return _remove(list(paths))


atexit.register(cleanup_current_temp_reports)
