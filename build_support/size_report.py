"""Read-only size inventory for a built Rechnungshelfer release."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


MIB = 1024 * 1024


class SizeReportError(RuntimeError):
    pass


def path_size(path: Path) -> tuple[int, int]:
    """Return byte and file counts without following directory symlinks."""
    if not path.exists():
        return 0, 0
    if path.is_file():
        return path.stat().st_size, 1
    total = 0
    files = 0
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            total += item.stat().st_size
            files += 1
    return total, files


def _measurement(path: Path, root: Path) -> dict[str, object]:
    size, files = path_size(path)
    try:
        display_path = path.relative_to(root).as_posix()
    except ValueError:
        display_path = str(path)
    return {"path": display_path, "bytes": size, "mib": round(size / MIB, 3), "files": files}


def _largest_components(build_dir: Path, limit: int = 15) -> list[dict[str, object]]:
    internal = build_dir / "_internal"
    candidates = [item for item in build_dir.iterdir() if item.name != "_internal"]
    if internal.is_dir():
        candidates.extend(item for item in internal.iterdir() if item.name != "external")
        external = internal / "external"
        if external.is_dir():
            candidates.extend(external.iterdir())
    measured = [_measurement(path, build_dir) for path in candidates]
    return sorted(measured, key=lambda item: int(item["bytes"]), reverse=True)[:limit]


def create_size_report(
    build_dir: Path,
    *,
    archive: Path | None = None,
    baseline: Path | None = None,
) -> dict[str, object]:
    build_dir = build_dir.resolve()
    if not build_dir.is_dir():
        raise SizeReportError(f"Build-Verzeichnis fehlt: {build_dir}")

    internal = build_dir / "_internal"
    java = internal / "external" / "java"
    kosit = internal / "external" / "kosit"
    tesseract = internal / "external" / "tesseract"
    kosit_validator = kosit / "validator"
    xrechnung = kosit / "xrechnung"
    ubl = kosit / "xrechnung" / "resources" / "ubl"
    babel = internal / "babel"

    complete_bytes, complete_files = path_size(build_dir)
    java_bytes, _ = path_size(java)
    kosit_bytes, _ = path_size(kosit)
    tesseract_bytes, _ = path_size(tesseract)
    python_bytes = complete_bytes - java_bytes - kosit_bytes - tesseract_bytes

    measurements: dict[str, dict[str, object]] = {
        "release_build": _measurement(build_dir, build_dir.parent),
        "python_application": {
            "path": f"{build_dir.name} (ohne Java, KoSIT und Tesseract)",
            "bytes": python_bytes,
            "mib": round(python_bytes / MIB, 3),
            "files": (
                complete_files
                - path_size(java)[1]
                - path_size(kosit)[1]
                - path_size(tesseract)[1]
            ),
        },
        "java_runtime": _measurement(java, build_dir),
        "kosit_bundle": _measurement(kosit, build_dir),
        "tesseract_runtime": _measurement(tesseract, build_dir),
        "kosit_validator": _measurement(kosit_validator, build_dir),
        "xrechnung_configuration": _measurement(xrechnung, build_dir),
        "ubl_schemas": _measurement(ubl, build_dir),
        "babel_locale_data": _measurement(babel, build_dir),
    }
    if archive is not None:
        archive = archive.resolve()
        if not archive.is_file():
            raise SizeReportError(f"Release-ZIP fehlt: {archive}")
        measurements["release_archive"] = _measurement(archive, archive.parent)

    report: dict[str, object] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "measurements": measurements,
        "largest_components": _largest_components(build_dir),
    }
    if baseline is not None:
        previous = json.loads(baseline.read_text(encoding="utf-8"))
        previous_measurements = previous.get("measurements", {})
        deltas = {}
        for name, current in measurements.items():
            old = previous_measurements.get(name)
            if isinstance(old, dict) and isinstance(old.get("bytes"), int):
                delta = int(current["bytes"]) - old["bytes"]
                deltas[name] = {"bytes": delta, "mib": round(delta / MIB, 3)}
        report["baseline"] = str(baseline)
        report["deltas"] = deltas
    return report


def render_table(report: dict[str, object]) -> str:
    labels = {
        "release_build": "Release-Build",
        "release_archive": "Release-ZIP",
        "python_application": "Python-Anwendung",
        "java_runtime": "Java-Runtime",
        "tesseract_runtime": "Tesseract-OCR-Runtime",
        "kosit_bundle": "KoSIT gesamt",
        "kosit_validator": "KoSIT-Validator",
        "xrechnung_configuration": "XRechnung-Konfiguration",
        "ubl_schemas": "UBL-Schemas (Teilmenge KoSIT)",
        "babel_locale_data": "Babel-Sprachdaten",
    }
    measurements = report["measurements"]
    lines = [f"{'Bestandteil':34} {'MiB':>12} {'Bytes':>16} {'Dateien':>9}", "-" * 75]
    for name, item in measurements.items():
        lines.append(
            f"{labels.get(name, name):34} {item['mib']:12.3f} {item['bytes']:16,d} {item['files']:9,d}"
        )
    deltas = report.get("deltas", {})
    if deltas:
        lines.extend(["", "Veraenderung zur Ausgangsbasis:"])
        for name, item in deltas.items():
            lines.append(f"  {labels.get(name, name):32} {item['mib']:+10.3f} MiB")
    lines.extend(["", "Groesste Bestandteile:"])
    for item in report["largest_components"]:
        lines.append(f"  {item['mib']:9.3f} MiB  {item['path']}")
    return "\n".join(lines)


def write_size_report(report: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Release-Groessen reproduzierbar messen")
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = create_size_report(args.build_dir, archive=args.archive, baseline=args.baseline)
        if args.output:
            write_size_report(report, args.output)
        print(render_table(report))
        if args.output:
            print(f"\nJSON-Bericht: {args.output.resolve()}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, SizeReportError) as exc:
        print(f"FEHLER: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
