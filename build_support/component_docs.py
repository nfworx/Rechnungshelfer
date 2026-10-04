"""Erzeugt sichtbare Komponenteninformationen aus external/components.json."""

from __future__ import annotations

import json
from pathlib import Path


BEGIN = "<!-- BEGIN GENERATED EXTERNAL COMPONENTS -->"
END = "<!-- END GENERATED EXTERNAL COMPONENTS -->"
COMPONENT_NAMES = {
    "java-runtime": "Java-Laufzeit",
    "kosit-validator": "KoSIT XML Validator",
    "ubl-schemas": "OASIS UBL-Schemata",
    "xrechnung-configuration": "XRechnung-Konfiguration",
}


def load_versions(project_root: Path) -> dict[str, str]:
    path = project_root / "external" / "components.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    components = data.get("components")
    if not isinstance(components, dict) or not components:
        raise ValueError(f"Komponentenstatus ist ungueltig: {path}")
    return {str(key): str(value) for key, value in components.items()}


def render_versions(versions: dict[str, str]) -> str:
    rows = ["| Komponente | Mitgelieferter Stand |", "|---|---|"]
    for component_id, version in sorted(versions.items()):
        name = COMPONENT_NAMES.get(component_id, component_id)
        rows.append(f"| {name} | `{version}` |")
    return "\n".join([
        BEGIN,
        "## Mitgelieferte externe Komponenten",
        "",
        "Dieser Abschnitt wird vom Release-Werkzeug aus `external/components.json` erzeugt.",
        "",
        *rows,
        END,
    ])


def _updated_text(path: Path, block: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
            raise ValueError(f"Generierter Komponentenblock ist beschaedigt: {path}")
        new_text = text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
    else:
        new_text = text.rstrip() + "\n\n" + block + "\n"
    return text, new_text


def _replace_or_append(path: Path, block: str) -> bool:
    text, new_text = _updated_text(path, block)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def update_component_documentation(project_root: Path) -> list[Path]:
    block = render_versions(load_versions(project_root))
    changed = []
    for relative in ("readme.md", "THIRD_PARTY_NOTICES.md"):
        path = project_root / relative
        if _replace_or_append(path, block):
            changed.append(path)
    return changed


def outdated_component_documentation(project_root: Path) -> list[Path]:
    """Liefert abweichende generierte Abschnitte, ohne Dateien zu veraendern."""
    block = render_versions(load_versions(project_root))
    outdated = []
    for relative in ("readme.md", "THIRD_PARTY_NOTICES.md"):
        path = project_root / relative
        text, expected = _updated_text(path, block)
        if text != expected:
            outdated.append(path)
    return outdated
