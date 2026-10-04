"""Manuelles Wartungswerkzeug fuer den Software-Herausgeber."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from updater.external_components_update import update_external_components


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aktualisiert externe Komponenten im Rechnungshelfer-Projekt."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    versions = update_external_components(args.manifest.resolve(), args.project_root.resolve())
    for component_id, version in sorted(versions.items()):
        print(f"{component_id}: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
