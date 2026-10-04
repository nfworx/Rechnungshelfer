"""Erzeugt gehashte Anwendungs- und Komponentenmanifeste fuer Updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from updater.core import COMPONENT_MANAGED_PATHS


def _package_data(package: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with package.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return {"url": package.name, "size": size, "sha256": digest.hexdigest()}


def _write_manifest(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def create_application_manifest(
    package: Path,
    version: str,
    channel: str,
    output: Path | None = None,
) -> Path:
    package = package.resolve()
    output = output or package.with_name(f"Rechnungshelfer-{version}-{channel}-manifest.json")
    return _write_manifest(
        output,
        {
            "schema_version": 1,
            "kind": "application",
            "channel": channel,
            "version": version,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "package": _package_data(package),
            "release_notes_url": "",
            "mandatory": False,
        },
    )


def create_component_package(
    component_id: str,
    version: str,
    source: Path,
    output_dir: Path,
    channel: str,
) -> tuple[Path, Path]:
    try:
        managed_paths = COMPONENT_MANAGED_PATHS[component_id]
    except KeyError as exc:
        raise SystemExit(f"Unbekannte Komponente: {component_id}") from exc
    if len(managed_paths) != 1:
        raise SystemExit("Der Paketgenerator unterstuetzt derzeit genau einen Komponentenpfad.")
    source = source.resolve()
    if not source.is_dir():
        raise SystemExit(f"Komponentenordner fehlt: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    package = output_dir / f"Rechnungshelfer-{component_id}-{version}.zip"
    prefix = Path(managed_paths[0])
    files = sorted(path for path in source.rglob("*") if path.is_file())
    forbidden = [path for path in files if path.name.endswith(("-report.xml", "-report.html"))]
    if forbidden:
        raise SystemExit("Komponentenordner enthaelt erzeugte Pruefberichte.")
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, (prefix / path.relative_to(source)).as_posix())
    manifest = output_dir / f"Rechnungshelfer-{component_id}-{version}-{channel}-manifest.json"
    _write_manifest(
        manifest,
        {
            "schema_version": 1,
            "kind": "components",
            "channel": channel,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "components": [
                {
                    "id": component_id,
                    "version": version,
                    "package": _package_data(package),
                }
            ],
        },
    )
    return package, manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    application = subparsers.add_parser("application")
    application.add_argument("--package", type=Path, required=True)
    application.add_argument("--version", required=True)
    application.add_argument("--channel", choices=("stable", "test"), default="stable")
    application.add_argument("--output", type=Path)
    component = subparsers.add_parser("component")
    component.add_argument("--id", required=True)
    component.add_argument("--version", required=True)
    component.add_argument("--source", type=Path, required=True)
    component.add_argument("--output-dir", type=Path, required=True)
    component.add_argument("--channel", choices=("stable", "test"), default="test")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "application":
        print(create_application_manifest(args.package, args.version, args.channel, args.output))
    else:
        package, manifest = create_component_package(
            args.id,
            args.version,
            args.source,
            args.output_dir,
            args.channel,
        )
        print(package)
        print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
