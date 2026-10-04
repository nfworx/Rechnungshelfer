"""Getrennte Herausgeberbefehle fuer Wartung und Releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packaging.version import InvalidVersion, Version

from build_support.component_docs import outdated_component_documentation, update_component_documentation
from build_support.kosit_builder import KositBuilderError, fetch_latest_release, install_release, installed_version
from updater.core import ApplicationManifest, UpdateError, load_manifest


class BuilderError(RuntimeError):
    pass


class Reporter:
    def __init__(self, project_root: Path, command: str = "release"):
        self.log_dir = project_root / "build" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / "release-tool.log"
        self.report_path = self.log_dir / "release-report.json"
        self.started_at = datetime.now().astimezone()
        self.events: list[dict[str, str]] = []
        self.details: dict[str, object] = {"command": command}
        self.status = "running"
        self._log = self.log_path.open("a", encoding="utf-8", buffering=1)
        self._record("INFO", "START", f"Release-Werkzeug gestartet: {command}")

    def _record(self, level: str, step: str, message: str) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        event = {"time": now, "level": level, "step": step, "message": message}
        self.events.append(event)
        line = f"[{now}] [{level}] [{step}] {message}"
        print(line, file=sys.stderr if level == "FEHLER" else sys.stdout, flush=True)
        self._log.write(line + "\n")
        self._write_report()

    def start(self, step: str, message: str) -> None:
        self._record("INFO", step, message)

    def ok(self, step: str, message: str) -> None:
        self._record("OK", step, message)

    def warning(self, step: str, message: str) -> None:
        self._record("WARNUNG", step, message)

    def error(self, step: str, message: str) -> None:
        self._record("FEHLER", step, message)

    def set_detail(self, key: str, value: object) -> None:
        self.details[key] = value
        self._write_report()

    def _write_report(self) -> None:
        report = {
            "schema_version": 1,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "status": self.status,
            "details": self.details,
            "events": self.events,
        }
        temporary = self.report_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.report_path)

    def run_process(self, step: str, command: list[str], cwd: Path) -> None:
        self.start(step, "Starte: " + subprocess.list2cmdline(command))
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise BuilderError(f"Prozess konnte nicht gestartet werden: {exc}") from exc
        assert process.stdout is not None
        for line in process.stdout:
            text = line.rstrip()
            if text:
                self._record("AUSGABE", step, text)
        if process.wait() != 0:
            raise BuilderError(f"Prozess endete mit Code {process.returncode}.")
        self.ok(step, "Prozess erfolgreich abgeschlossen")

    def finish(self, status: str) -> None:
        self.status = status
        self.details["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        level = "OK" if status == "success" else "WARNUNG" if status == "cancelled" else "FEHLER"
        self._record(level, "ENDE", f"Status: {status}")
        self._log.close()


class ProjectSnapshot:
    def __init__(self, project_root: Path, relative_paths: tuple[str, ...]):
        self.project_root = project_root
        self.relative_paths = relative_paths
        self._temp = tempfile.TemporaryDirectory(prefix="Rechnungshelfer-Release-Rollback-")
        self.backup_root = Path(self._temp.name)
        self.existed: set[str] = set()
        for relative in relative_paths:
            source = project_root / relative
            if not source.exists():
                continue
            self.existed.add(relative)
            target = self.backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target) if source.is_dir() else shutil.copy2(source, target)

    def restore(self) -> None:
        for relative in self.relative_paths:
            target = self.project_root / relative
            shutil.rmtree(target) if target.is_dir() else target.unlink(missing_ok=True)
            if relative not in self.existed:
                continue
            source = self.backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target) if source.is_dir() else shutil.copy2(source, target)

    def close(self) -> None:
        self._temp.cleanup()


def _read_app_version(project_root: Path) -> Version:
    text = (project_root / "version.py").read_text(encoding="utf-8")
    match = re.fullmatch(
        r'\s*"""Einzige Quelle fuer die Programmversion\."""\s+__version__\s*=\s*"([^"]+)"\s*', text
    )
    if not match:
        raise BuilderError("version.py besitzt nicht das erwartete eindeutige Format.")
    try:
        return Version(match.group(1))
    except InvalidVersion as exc:
        raise BuilderError("version.py enthaelt keine gueltige Version.") from exc


def _write_app_version(project_root: Path, version: Version) -> None:
    (project_root / "version.py").write_text(
        f'"""Einzige Quelle fuer die Programmversion."""\n\n__version__ = "{version}"\n', encoding="utf-8"
    )


def _changelog_section(project_root: Path, version: Version) -> str:
    text = (project_root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(str(version))}\](?:\s+-\s+.*)?$", text, re.MULTILINE)
    if match is None:
        raise BuilderError(
            f"CHANGELOG.md enthaelt keinen Abschnitt fuer {version}. "
            "Releasebeschreibung bitte bewusst manuell verfassen."
        )
    next_section = re.search(r"^## \[", text[match.end():], re.MULTILINE)
    end = match.end() + next_section.start() if next_section else len(text)
    return text[match.start():end].strip() + "\n"


def _write_release_notes(project_root: Path, version: Version) -> Path:
    output = project_root / "build" / f"release-notes-{version}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_changelog_section(project_root, version), encoding="utf-8")
    return output


def _ask_yes_no(prompt: str, *, assume_yes: bool, input_fn: Callable[[str], str]) -> bool:
    if assume_yes:
        return True
    return input_fn(prompt + " [j/N]: ").strip().lower() in {"j", "ja", "y", "yes"}


def _preflight(project_root: Path) -> None:
    required = (
        "build.ps1", "version.py", "CHANGELOG.md", "readme.md", "requirements.txt",
        "requirements-dev.txt", "THIRD_PARTY_NOTICES.md", "external/components.json",
        "external/java/bin/java.exe",
    )
    missing = [relative for relative in required if not (project_root / relative).exists()]
    if missing:
        raise BuilderError("Erforderliche Dateien fehlen: " + ", ".join(missing))
    reports = [
        path for pattern in ("*-report.xml", "*-report.html")
        for path in (project_root / "external" / "kosit").rglob(pattern)
    ]
    if reports:
        raise BuilderError("Erzeugte KoSIT-Berichte muessen vor dem Build entfernt werden.")


def _report_component_status(reporter: Reporter, project_root: Path):
    current = installed_version(project_root)
    release = fetch_latest_release()
    reporter.set_detail("kosit", {
        "installed": str(current), "available": str(release.version), "release": release.page_url,
    })
    if release.version > current:
        reporter.warning("KOMPONENTEN", f"KoSIT-Update verfuegbar: {current} -> {release.version}")
    else:
        reporter.ok("KOMPONENTEN", f"KoSIT {current} ist aktuell")
    state = json.loads((project_root / "external" / "components.json").read_text(encoding="utf-8"))["components"]
    reporter.warning(
        "KOMPONENTEN",
        "Java und XRechnung werden dokumentiert, besitzen aber noch keinen automatischen Quellenadapter",
    )
    reporter.ok("KOMPONENTEN", f"UBL {state.get('ubl-schemas', 'unbekannt')} ist fest vorgegeben")
    return current, release


def _run_dependency_audit(reporter: Reporter, project_root: Path) -> None:
    reporter.run_process("SICHERHEIT", [
        sys.executable, "-m", "pip_audit", "-r", "requirements.txt", "--strict",
        "--cache-dir", "build/pip-audit-cache",
    ], project_root)


def _run_tests(reporter: Reporter, project_root: Path) -> None:
    reporter.run_process(
        "TESTS", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], project_root
    )


def _verify_source_metadata(project_root: Path, version: Version) -> None:
    _changelog_section(project_root, version)
    outdated = outdated_component_documentation(project_root)
    if outdated:
        names = ", ".join(path.name for path in outdated)
        raise BuilderError(
            f"Generierte Komponenteninformationen sind nicht aktuell: {names}. Zuerst 'prepare' ausfuehren."
        )


def _ensure_git_state(project_root: Path, *, allow_dirty: bool, skip: bool) -> None:
    if skip:
        return
    git = shutil.which("git")
    if not git:
        raise BuilderError("Git wurde nicht im PATH gefunden. Nur bewusst mit --skip-git-check uebergehen.")
    process = subprocess.run(
        [git, "status", "--porcelain"], cwd=str(project_root), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if process.returncode != 0:
        raise BuilderError("Git-Status konnte nicht gelesen werden: " + process.stderr.strip())
    if process.stdout.strip() and not allow_dirty:
        raise BuilderError(
            "Der Git-Arbeitsbaum enthaelt nicht commitete Aenderungen. Fuer Testbauten ist --allow-dirty verfuegbar."
        )


def _verify_artifacts(project_root: Path, version: Version, channel: str) -> dict[str, str]:
    architecture = "win64" if platform.architecture()[0] == "64bit" else "win32"
    archive = project_root / "release" / f"Rechnungshelfer-{version}-{architecture}.zip"
    checksum_path = Path(str(archive) + ".sha256")
    manifest_path = project_root / "release" / f"Rechnungshelfer-{version}-{channel}-manifest.json"
    for path in (archive, checksum_path, manifest_path):
        if not path.is_file():
            raise BuilderError(f"Erwartetes Release-Artefakt fehlt: {path}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = checksum_path.read_text(encoding="ascii").split()[0].lower()
    if digest != checksum:
        raise BuilderError("SHA-256-Datei stimmt nicht mit dem Release-ZIP ueberein.")
    manifest = load_manifest(manifest_path)
    if not isinstance(manifest, ApplicationManifest) or manifest.version != version:
        raise BuilderError("Anwendungsmanifest enthaelt die falsche Version oder Art.")
    if manifest.channel != channel:
        raise BuilderError("Anwendungsmanifest enthaelt den falschen Releasekanal.")
    if manifest.package.sha256 != digest or manifest.package.size != archive.stat().st_size:
        raise BuilderError("Anwendungsmanifest stimmt nicht mit dem Release-ZIP ueberein.")
    with zipfile.ZipFile(archive) as package:
        names = {name.replace("\\", "/") for name in package.namelist()}
    if "Rechnungshelfer.exe" not in names or "Updater.exe" not in names:
        raise BuilderError("Release-ZIP enthaelt Rechnungshelfer.exe oder Updater.exe nicht.")
    forbidden = [name for name in names if name.casefold().startswith("data/") or name.casefold().endswith(
        (".db", ".sqlite", ".sqlite3", "-report.xml", "-report.html")
    )]
    if forbidden:
        raise BuilderError("Release-ZIP enthaelt unzulaessige Benutzer- oder Berichtsdaten.")
    owner_names = {
        "build.ps1", "rechnungshelfer.spec", "updater.spec", "release_builder.py", "release_tool.py",
        "kosit_builder.py", "update_external_components.py",
    }
    owner_files = []
    for name in names:
        folded = tuple(part.casefold() for part in Path(name).parts)
        if "build_support" in folded or "tests" in folded or (folded and folded[-1] in owner_names):
            owner_files.append(name)
    if owner_files:
        raise BuilderError("Release-ZIP enthaelt interne Herausgeberwerkzeuge oder Tests.")
    return {
        "archive": str(archive), "checksum": str(checksum_path), "sha256": digest,
        "manifest": str(manifest_path),
    }


def _run_check(args, reporter: Reporter) -> None:
    root = args.project_root
    reporter.start("VORPRUEFUNG", "Pruefe Projekt ohne Quelldateien zu veraendern")
    _preflight(root)
    version = _read_app_version(root)
    _changelog_section(root, version)
    reporter.ok("VORPRUEFUNG", f"Rechnungshelfer {version} ist dokumentiert")
    reporter.start("KOMPONENTEN", "Pruefe externe Versionsstaende")
    _report_component_status(reporter, root)
    if outdated_component_documentation(root):
        reporter.warning("DOKUMENTATION", "Generierte Komponentenabschnitte sind nicht aktuell")
    else:
        reporter.ok("DOKUMENTATION", "Generierte Komponentenabschnitte sind aktuell")
    _run_dependency_audit(reporter, root)
    if args.with_tests:
        _run_tests(reporter, root)


def _run_update_components(args, reporter: Reporter, input_fn: Callable[[str], str]) -> None:
    root = args.project_root
    _preflight(root)
    reporter.start("KOMPONENTEN", "Pruefe KoSIT und aktualisiere nur nach Freigabe")
    current, release = _report_component_status(reporter, root)
    if release.version <= current:
        reporter.ok("KOMPONENTEN", "Keine Komponentenaenderung erforderlich")
        return
    if not _ask_yes_no(f"KoSIT {current} auf {release.version} aktualisieren?", assume_yes=args.yes, input_fn=input_fn):
        raise KeyboardInterrupt("Komponentenupdate abgebrochen")
    snapshot = ProjectSnapshot(
        root, ("external/kosit/validator", "external/components.json", "readme.md", "THIRD_PARTY_NOTICES.md")
    )
    try:
        install_release(root, release)
        changed = update_component_documentation(root)
        reporter.set_detail("documentation", [str(path.relative_to(root)) for path in changed])
        reporter.ok("KOMPONENTEN", f"KoSIT {release.version} installiert und Dokumentation synchronisiert")
        _run_tests(reporter, root)
        snapshot.close()
    except (Exception, KeyboardInterrupt):
        snapshot.restore()
        snapshot.close()
        reporter.warning("ROLLBACK", "Komponenten und generierte Dokumentation wurden zurueckgesetzt")
        raise


def _run_prepare(args, reporter: Reporter) -> None:
    root = args.project_root
    _preflight(root)
    try:
        target = Version(args.version)
    except InvalidVersion as exc:
        raise BuilderError(f"Ungueltige Releaseversion: {args.version}") from exc
    current = _read_app_version(root)
    if target < current:
        raise BuilderError(f"Releaseversion {target} ist kleiner als der aktuelle Stand {current}.")
    _changelog_section(root, target)
    snapshot = ProjectSnapshot(root, ("version.py", "readme.md", "THIRD_PARTY_NOTICES.md"))
    try:
        reporter.start("VORBEREITUNG", f"Bereite Rechnungshelfer {target} vor")
        if target != current:
            _write_app_version(root, target)
            reporter.warning("VORBEREITUNG", f"version.py geaendert: {current} -> {target}")
        else:
            reporter.ok("VORBEREITUNG", f"version.py steht bereits auf {target}")
        changed = update_component_documentation(root)
        notes = _write_release_notes(root, target)
        reporter.set_detail("documentation", [str(path.relative_to(root)) for path in changed])
        reporter.set_detail("release_notes", str(notes))
        reporter.ok("VORBEREITUNG", "Technische Metadaten synchron; Changelogtext wurde nicht veraendert")
        snapshot.close()
    except Exception:
        snapshot.restore()
        snapshot.close()
        reporter.warning("ROLLBACK", "Versionsdatei und generierte Dokumentation wurden zurueckgesetzt")
        raise


def _run_build(args, reporter: Reporter, input_fn: Callable[[str], str]) -> None:
    root = args.project_root
    reporter.start("VORPRUEFUNG", "Pruefe vorbereiteten, reproduzierbaren Releasezustand")
    _preflight(root)
    version = _read_app_version(root)
    _verify_source_metadata(root, version)
    _ensure_git_state(root, allow_dirty=args.allow_dirty, skip=args.skip_git_check)
    reporter.ok("VORPRUEFUNG", f"Quellstand fuer Rechnungshelfer {version} ist vorbereitet")
    _run_dependency_audit(reporter, root)
    _run_tests(reporter, root)
    if not _ask_yes_no(
        f"One-Folder-Build {version} fuer Kanal '{args.channel}' jetzt ausfuehren?",
        assume_yes=args.yes, input_fn=input_fn,
    ):
        raise KeyboardInterrupt("Build abgebrochen")
    reporter.run_process("BUILD", [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "build.ps1"),
        "-Channel", args.channel,
    ], root)
    reporter.start("ARTEFAKTE", "Pruefe ZIP, SHA-256, Manifest und Datenschutzregeln")
    artifacts = _verify_artifacts(root, version, args.channel)
    reporter.set_detail("artifacts", artifacts)
    reporter.ok("ARTEFAKTE", f"Release-Paket geprueft: {artifacts['archive']}")


def run_command(args, *, input_fn: Callable[[str], str] = input) -> int:
    args.project_root = Path(args.project_root).resolve()
    reporter = Reporter(args.project_root, args.command)
    try:
        if args.command == "check":
            _run_check(args, reporter)
        elif args.command == "update-components":
            _run_update_components(args, reporter, input_fn)
        elif args.command == "prepare":
            _run_prepare(args, reporter)
        elif args.command == "build":
            _run_build(args, reporter, input_fn)
        else:
            raise BuilderError(f"Unbekannter Befehl: {args.command}")
        reporter.finish("success")
        return 0
    except KeyboardInterrupt as exc:
        reporter.warning("ABBRUCH", str(exc) or "Durch Benutzer abgebrochen")
        reporter.finish("cancelled")
        return 0
    except (BuilderError, KositBuilderError, UpdateError, InvalidVersion, OSError, ValueError,
            EOFError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        reporter.error("ABBRUCH", str(exc))
        reporter.finish("failed")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Internes Release-Werkzeug fuer Rechnungshelfer")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Nur pruefen; keine Quelldateien aendern")
    check.add_argument("--with-tests", action="store_true")
    update = commands.add_parser("update-components", help="Externe Komponenten bewusst aktualisieren")
    update.add_argument("--yes", action="store_true")
    prepare = commands.add_parser("prepare", help="Technische Release-Metadaten synchronisieren")
    prepare.add_argument("--version", required=True)
    build = commands.add_parser("build", help="Aus vorbereitetem Quellstand Release-Artefakte bauen")
    build.add_argument("--channel", choices=("test", "stable"), default="test")
    build.add_argument("--yes", action="store_true")
    build.add_argument("--allow-dirty", action="store_true")
    build.add_argument("--skip-git-check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_command(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
