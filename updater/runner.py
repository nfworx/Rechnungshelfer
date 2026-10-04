"""An Benutzer ausgelieferter Prozess nur fuer Rechnungshelfer-Programmupdates."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Callable

from updater.application_update import prepare_application_update
from updater.core import ApplicationManifest, UpdateError, load_manifest
from updater.readiness import READY_ARGUMENT, READY_PREFIX


LOG_PATH = Path(tempfile.gettempdir()) / "Rechnungshelfer-Updater.log"
ProgressCallback = Callable[[int, str], None]


def _report(progress: ProgressCallback | None, percent: int, message: str) -> None:
    if progress is not None:
        progress(percent, message)


def _configure_logging() -> None:
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def wait_for_process(process_id: int, timeout: float = 120.0) -> None:
    if process_id <= 0 or process_id == os.getpid():
        return
    if os.name == "nt":
        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, process_id)
        if not handle:
            return
        try:
            result = ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000))
            if result == 0x00000102:
                raise UpdateError("Das Hauptprogramm wurde nicht rechtzeitig beendet.")
            if result == 0xFFFFFFFF:
                raise UpdateError("Auf das Ende des Hauptprogramms konnte nicht gewartet werden.")
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            return
        time.sleep(0.2)
    raise UpdateError("Das Hauptprogramm wurde nicht rechtzeitig beendet.")


def _restart_command(args, install_root: Path) -> list[str]:
    if args.restart_command_json:
        try:
            command = json.loads(args.restart_command_json)
        except json.JSONDecodeError as exc:
            raise UpdateError("Neustartbefehl ist ungueltiges JSON.") from exc
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            raise UpdateError("Neustartbefehl muss eine Liste von Zeichenketten sein.")
        return command
    return [str(install_root / "Rechnungshelfer.exe")]


def _launch(command: list[str], ready_file: Path | None = None) -> subprocess.Popen:
    full_command = list(command)
    if ready_file is not None:
        full_command.extend([READY_ARGUMENT, str(ready_file)])
    try:
        return subprocess.Popen(
            full_command,
            cwd=str(Path(full_command[0]).resolve().parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except OSError as exc:
        raise UpdateError(f"Rechnungshelfer konnte nicht neu gestartet werden: {exc}") from exc


def _release_detached_process(process: subprocess.Popen) -> None:
    """Gibt unter Windows den Handle frei, ohne die gestartete App zu beenden."""
    if process.poll() is not None or os.name != "nt":
        return
    handle = getattr(process, "_handle", None)
    if handle is not None:
        handle.Close()
        process._handle = None
        # Popen besitzt den Prozess danach absichtlich nicht mehr. Der gesetzte
        # Status verhindert, dass der Destruktor einen bereits geschlossenen
        # Handle als noch laufenden Kindprozess behandelt.
        process.returncode = 0


def _restart_without_monitoring(args, install_root: Path) -> None:
    process = _launch(_restart_command(args, install_root))
    _release_detached_process(process)


def _wait_until_ready(process: subprocess.Popen, ready_file: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready_file.is_file():
            return
        if process.poll() is not None:
            raise UpdateError("Die neue Anwendung wurde vor der Startbestaetigung beendet.")
        time.sleep(0.2)
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    except OSError:
        pass
    raise UpdateError("Die neue Anwendung hat ihren erfolgreichen Start nicht bestaetigt.")


def _run_application(
    args,
    manifest: ApplicationManifest,
    manifest_source,
    install_root: Path,
    progress: ProgressCallback | None = None,
) -> None:
    transaction, work_root = prepare_application_update(
        manifest,
        manifest_source,
        install_root,
        current_version=args.current_version,
        allow_downgrade=args.allow_downgrade,
        progress=progress,
    )
    ready_file = Path(tempfile.gettempdir()) / f"{READY_PREFIX}{uuid.uuid4().hex}.txt"
    ready_file.unlink(missing_ok=True)
    try:
        if args.no_restart:
            _report(progress, 100, "Update erfolgreich abgeschlossen.")
            transaction.commit()
            return
        _report(progress, 100, "Update ist installiert. Rechnungshelfer wird gestartet ...")
        process = _launch(_restart_command(args, install_root), ready_file)
        _wait_until_ready(process, ready_file, args.ready_timeout)
        _release_detached_process(process)
        transaction.commit()
        _report(progress, 100, "Update erfolgreich abgeschlossen.")
    except Exception:
        transaction.rollback()
        if not args.no_restart:
            try:
                _restart_without_monitoring(args, install_root)
            except UpdateError:
                logging.exception("Auch die vorherige Anwendung konnte nicht neu gestartet werden.")
        raise
    finally:
        ready_file.unlink(missing_ok=True)
        shutil.rmtree(work_root, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="Rechnungshelfer-Updater")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--install-root", required=True)
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--current-version", default="0.0.0")
    parser.add_argument("--restart-command-json", default="")
    parser.add_argument("--ready-timeout", type=float, default=45.0)
    parser.add_argument("--allow-downgrade", action="store_true")
    parser.add_argument("--no-restart", action="store_true")
    return parser


def run(
    argv: list[str] | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging()
    _report(progress, 1, "Updateinformationen werden geprueft ...")
    install_root = Path(args.install_root).resolve()
    if not install_root.is_dir():
        raise UpdateError(f"Installationsordner fehlt: {install_root}")
    parsed_manifest = urllib.parse.urlparse(args.manifest)
    manifest_source = (
        args.manifest
        if parsed_manifest.scheme.lower() == "https"
        else Path(args.manifest).resolve()
    )
    manifest = load_manifest(manifest_source)
    _report(progress, 4, "Rechnungshelfer wird fuer das Update beendet ...")
    wait_for_process(args.pid)
    if not isinstance(manifest, ApplicationManifest):
        raise UpdateError("Updater.exe akzeptiert nur Rechnungshelfer-Programmupdates.")
    _report(progress, 6, "Update wird vorbereitet ...")
    _run_application(args, manifest, manifest_source, install_root, progress)
    logging.info("Rechnungshelfer-Programmupdate erfolgreich abgeschlossen")
    return 0


def _show_error(message: str) -> None:
    try:
        from tkinter import messagebox

        messagebox.showerror("Rechnungshelfer-Updater", message)
    except Exception:
        pass


def main() -> int:
    try:
        _configure_logging()
        from updater.progress_ui import run_with_progress

        return run_with_progress(lambda progress: run(progress=progress), LOG_PATH)
    except Exception as exc:
        _configure_logging()
        logging.exception("Update fehlgeschlagen")
        _show_error(f"Update fehlgeschlagen:\n\n{exc}\n\nProtokoll: {LOG_PATH}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
