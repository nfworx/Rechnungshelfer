"""Nur fuer den Herausgeber: externe Komponenten im Projekt aktualisieren."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from updater.core import (
    ComponentUpdate,
    ComponentsManifest,
    UpdateError,
    apply_component_updates,
    load_manifest,
)


def _validate_component(component: ComponentUpdate, project_root: Path) -> None:
    if component.component_id == "tesseract-runtime":
        executable = project_root / "external" / "tesseract" / "tesseract.exe"
        language = project_root / "external" / "tesseract" / "tessdata" / "deu.traineddata"
        if not executable.is_file() or not language.is_file():
            raise UpdateError("Tesseract-Smoke-Test findet Laufzeit oder deutsche Sprachdaten nicht.")
        try:
            version = subprocess.run(
                [str(executable), "--version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            languages = subprocess.run(
                [str(executable), "--list-langs"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UpdateError(f"Tesseract-Smoke-Test konnte nicht ausgefuehrt werden: {exc}") from exc
        version_text = version.stdout.decode("utf-8", errors="replace").lower()
        language_text = languages.stdout.decode("utf-8", errors="replace").splitlines()
        if (
            version.returncode != 0
            or f"tesseract v{component.version}" not in version_text
            or languages.returncode != 0
            or "deu" not in {line.strip() for line in language_text}
        ):
            raise UpdateError("Tesseract-Smoke-Test ist fehlgeschlagen.")
        return
    if component.component_id != "kosit-validator":
        return
    java_name = "java.exe" if os.name == "nt" else "java"
    java = project_root / "external" / "java" / "bin" / java_name
    jars = sorted((project_root / "external" / "kosit" / "validator").glob("validator-*-standalone.jar"))
    if not java.is_file() or len(jars) != 1:
        raise UpdateError("KoSIT-Smoke-Test findet Java oder das Validator-JAR nicht eindeutig.")
    try:
        result = subprocess.run(
            [str(java), "-jar", str(jars[0]), "--help"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"KoSIT-Smoke-Test konnte nicht ausgefuehrt werden: {exc}") from exc
    output = result.stdout.decode("utf-8", errors="replace")
    if result.returncode != 0 or "KoSIT Validator" not in output:
        raise UpdateError("KoSIT-Smoke-Test ist fehlgeschlagen.")


def update_external_components(manifest_source: str | Path, project_root: Path) -> dict[str, str]:
    """Aktualisiert den Projektinhalt; diese Funktion wird nicht an Benutzer ausgeliefert."""
    manifest = load_manifest(manifest_source)
    if not isinstance(manifest, ComponentsManifest):
        raise UpdateError("Das Manifest ist kein Komponenten-Wartungsupdate.")
    return apply_component_updates(
        manifest,
        manifest_source,
        project_root,
        validator=_validate_component,
    )


__all__ = ["update_external_components"]
