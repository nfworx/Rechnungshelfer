"""Validierung der bewusst freigegebenen portablen Tesseract-Laufzeit."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRUSTED_RELEASES = Path(__file__).with_name("tesseract_trusted_releases.json")


class TesseractRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TesseractRuntimeInfo:
    version: str
    release_tag: str
    installer_filename: str
    installer_sha256: str
    runtime_sha256: str
    languages: tuple[str, ...]
    files: tuple[Path, ...]


def runtime_files(runtime_dir: Path) -> tuple[Path, ...]:
    """Liefert nur Dateien, die die Endnutzer-OCR wirklich benoetigt."""

    candidates = [runtime_dir / "tesseract.exe"]
    candidates.extend(sorted(runtime_dir.glob("*.dll")))
    candidates.extend(
        runtime_dir / "tessdata" / name
        for name in ("deu.traineddata", "eng.traineddata", "osd.traineddata")
        if (runtime_dir / "tessdata" / name).is_file()
    )
    tsv_config = runtime_dir / "tessdata" / "configs" / "tsv"
    if tsv_config.is_file():
        candidates.append(tsv_config)
    license_dir = runtime_dir / "licenses"
    if license_dir.is_dir():
        candidates.extend(sorted(path for path in license_dir.rglob("*") if path.is_file()))
    return tuple(path for path in candidates if path.is_file())


def runtime_digest(runtime_dir: Path, files: tuple[Path, ...] | None = None) -> str:
    files = files or runtime_files(runtime_dir)
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(runtime_dir).as_posix()):
        relative = path.relative_to(runtime_dir).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _trusted_release(path: Path = TRUSTED_RELEASES) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    releases = data.get("releases")
    if not isinstance(releases, list) or len(releases) != 1:
        raise TesseractRuntimeError("Tesseract-Freigabedatei ist ungueltig.")
    return releases[0]


def validate_installed_runtime(
    project_root: Path = PROJECT_ROOT,
    *,
    trusted_releases: Path = TRUSTED_RELEASES,
    verify_digest: bool = True,
) -> TesseractRuntimeInfo:
    release = _trusted_release(trusted_releases)
    runtime_dir = project_root / "external" / "tesseract"
    executable = runtime_dir / "tesseract.exe"
    language_file = runtime_dir / "tessdata" / "deu.traineddata"
    tsv_config = runtime_dir / "tessdata" / "configs" / "tsv"
    missing = [path for path in (executable, language_file, tsv_config) if not path.is_file()]
    if missing:
        raise TesseractRuntimeError(
            "Tesseract-Laufzeit ist unvollstaendig: "
            + ", ".join(str(path) for path in missing)
        )

    try:
        version_result = subprocess.run(
            [str(executable), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        language_result = subprocess.run(
            [str(executable), "--list-langs"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TesseractRuntimeError(f"Tesseract-Smoke-Test fehlgeschlagen: {exc}") from exc

    version_output = version_result.stdout.decode("utf-8", errors="replace")
    language_output = language_result.stdout.decode("utf-8", errors="replace")
    version = str(release["version"])
    if version_result.returncode != 0 or f"tesseract v{version}" not in version_output.lower():
        raise TesseractRuntimeError(
            f"Tesseract-Version entspricht nicht der Freigabe {version}."
        )
    languages = tuple(
        line.strip()
        for line in language_output.splitlines()
        if line.strip() and not line.lower().startswith("list of available")
    )
    if language_result.returncode != 0 or "deu" not in languages:
        raise TesseractRuntimeError("Deutsche Tesseract-Sprachdaten fehlen.")

    files = runtime_files(runtime_dir)
    if not any(path.suffix.lower() == ".dll" for path in files):
        raise TesseractRuntimeError("Tesseract-Laufzeit enthaelt keine DLLs.")
    digest = runtime_digest(runtime_dir, files)
    expected_digest = str(release.get("runtime_sha256", "")).lower()
    if verify_digest and digest != expected_digest:
        raise TesseractRuntimeError(
            "Tesseract-Laufzeit weicht von der lokal freigegebenen Dateiauswahl ab."
        )

    return TesseractRuntimeInfo(
        version=version,
        release_tag=str(release["release_tag"]),
        installer_filename=str(release["installer_filename"]),
        installer_sha256=str(release["installer_sha256"]).lower(),
        runtime_sha256=digest,
        languages=languages,
        files=files,
    )


__all__ = [
    "TesseractRuntimeError",
    "TesseractRuntimeInfo",
    "runtime_digest",
    "runtime_files",
    "validate_installed_runtime",
]
