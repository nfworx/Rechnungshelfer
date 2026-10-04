"""Online-Pruefung und Ausloesung des separaten Rechnungshelfer-Updaters."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

from app_info import APP_VERSION, UPDATE_CHANNEL, UPDATE_RELEASE_API_URL
from updater.core import ApplicationManifest, UpdateError, load_manifest, parse_manifest_bytes


MAX_RELEASE_METADATA_BYTES = 2 * 1024 * 1024
MAX_ONLINE_MANIFEST_BYTES = 1 * 1024 * 1024
GITHUB_RELEASE_PREFIX = "https://github.com/nfworx/Rechnungshelfer/releases/download/"
USER_AGENT = "Rechnungshelfer-Updatecheck/1"


@dataclass(frozen=True)
class UpdateSummary:
    title: str
    details: tuple[str, ...]
    manifest: ApplicationManifest


@dataclass(frozen=True)
class OnlineUpdate:
    summary: UpdateSummary
    manifest_url: str
    manifest_sha256: str
    package_url: str
    release_url: str


def application_install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _summary(manifest: ApplicationManifest) -> UpdateSummary:
    return UpdateSummary(
        title=f"Rechnungshelfer {manifest.version}",
        details=(f"Installiert: {APP_VERSION}", f"Verfuegbar: {manifest.version}"),
        manifest=manifest,
    )


def describe_application_update(source: str | Path) -> UpdateSummary:
    """Prueft ein lokales Programmmanifest fuer beaufsichtigte Tests."""
    manifest = load_manifest(source)
    if not isinstance(manifest, ApplicationManifest):
        raise UpdateError("Das gewaehlte Manifest ist kein Rechnungshelfer-Programmupdate.")
    if manifest.channel not in {UPDATE_CHANNEL, "test"}:
        raise UpdateError(f"Updatekanal '{manifest.channel}' passt nicht zu '{UPDATE_CHANNEL}'.")
    if manifest.version <= Version(APP_VERSION):
        raise UpdateError(f"Version {manifest.version} ist nicht neuer als {APP_VERSION}.")
    return _summary(manifest)


def _request_bytes(url: str, limit: int, *, accept: str) -> bytes:
    if urllib.parse.urlparse(url).scheme.lower() != "https":
        raise UpdateError("Online-Updatequellen muessen HTTPS verwenden.")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if urllib.parse.urlparse(response.geturl()).scheme.lower() != "https":
                raise UpdateError("Updatecheck wurde auf eine unsichere Adresse umgeleitet.")
            payload = response.read(limit + 1)
    except UpdateError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError(f"Updatequelle ist nicht erreichbar: {exc}") from exc
    if len(payload) > limit:
        raise UpdateError("Antwort der Updatequelle ist unerwartet gross.")
    return payload


def _sha256_from_asset(asset: dict, label: str) -> str:
    digest = asset.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise UpdateError(f"GitHub liefert fuer {label} keinen SHA-256-Digest.")
    value = digest.removeprefix("sha256:").lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise UpdateError(f"GitHub liefert fuer {label} einen ungueltigen SHA-256-Digest.")
    return value


def _asset(release: dict, name: str) -> dict:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("GitHub-Release enthaelt keine Assetliste.")
    matches = [item for item in assets if isinstance(item, dict) and item.get("name") == name]
    if len(matches) != 1:
        raise UpdateError(f"Release-Datei fehlt oder ist nicht eindeutig: {name}")
    asset = matches[0]
    url = asset.get("browser_download_url")
    if not isinstance(url, str) or not url.startswith(GITHUB_RELEASE_PREFIX):
        raise UpdateError(f"Release-Datei besitzt keine erlaubte Downloadadresse: {name}")
    return asset


def _parse_release_version(release: dict) -> Version:
    if release.get("draft") or release.get("prerelease"):
        raise UpdateError("Das neueste GitHub-Release ist nicht stabil veroeffentlicht.")
    tag = release.get("tag_name")
    try:
        return Version(str(tag).removeprefix("v"))
    except InvalidVersion as exc:
        raise UpdateError(f"GitHub-Release besitzt eine ungueltige Version: {tag}") from exc


def check_for_application_update() -> OnlineUpdate | None:
    """Liefert ein geprueftes Update oder None, wenn die Anwendung aktuell ist."""
    metadata_payload = _request_bytes(
        UPDATE_RELEASE_API_URL,
        MAX_RELEASE_METADATA_BYTES,
        accept="application/vnd.github+json",
    )
    try:
        release = json.loads(metadata_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub-Releaseinformationen sind ungueltig.") from exc
    if not isinstance(release, dict):
        raise UpdateError("GitHub-Releaseinformationen sind kein Objekt.")
    release_version = _parse_release_version(release)
    if release_version <= Version(APP_VERSION):
        return None

    manifest_name = f"Rechnungshelfer-{release_version}-{UPDATE_CHANNEL}-manifest.json"
    manifest_asset = _asset(release, manifest_name)
    manifest_url = str(manifest_asset["browser_download_url"])
    manifest_digest = _sha256_from_asset(manifest_asset, "das Update-Manifest")
    manifest_size = manifest_asset.get("size")
    if not isinstance(manifest_size, int) or not 0 < manifest_size <= MAX_ONLINE_MANIFEST_BYTES:
        raise UpdateError("Update-Manifest besitzt eine ungueltige Groesse.")
    manifest_payload = _request_bytes(manifest_url, MAX_ONLINE_MANIFEST_BYTES, accept="application/octet-stream")
    if len(manifest_payload) != manifest_size:
        raise UpdateError("Update-Manifest stimmt in der Groesse nicht mit GitHub ueberein.")
    if hashlib.sha256(manifest_payload).hexdigest() != manifest_digest:
        raise UpdateError("SHA-256 des Update-Manifests stimmt nicht mit GitHub ueberein.")
    manifest = parse_manifest_bytes(manifest_payload)
    if not isinstance(manifest, ApplicationManifest):
        raise UpdateError("Online-Manifest ist kein Rechnungshelfer-Programmupdate.")
    if manifest.channel != UPDATE_CHANNEL:
        raise UpdateError(f"Online-Manifest verwendet den falschen Kanal: {manifest.channel}")
    if manifest.version != release_version:
        raise UpdateError("Manifestversion stimmt nicht mit dem GitHub-Release ueberein.")

    package_name = Path(urllib.parse.urlparse(manifest.package.url).path).name
    package_asset = _asset(release, package_name)
    package_digest = _sha256_from_asset(package_asset, "das Programm-ZIP")
    if package_asset.get("size") != manifest.package.size or package_digest != manifest.package.sha256:
        raise UpdateError("Programm-ZIP stimmt nicht mit Manifest und GitHub-Metadaten ueberein.")
    release_url = release.get("html_url")
    if not isinstance(release_url, str) or not release_url.startswith("https://github.com/nfworx/Rechnungshelfer/releases/"):
        raise UpdateError("GitHub-Release besitzt keine erlaubte Informationsadresse.")
    return OnlineUpdate(
        summary=_summary(manifest),
        manifest_url=manifest_url,
        manifest_sha256=manifest_digest,
        package_url=str(package_asset["browser_download_url"]),
        release_url=release_url,
    )


def _updater_command() -> tuple[list[str], Path | None]:
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "updater.runner"], None
    source = application_install_root() / "Updater.exe"
    if not source.is_file():
        raise UpdateError("Updater.exe fehlt im Programmordner.")
    temp_dir = Path(tempfile.gettempdir()) / "Rechnungshelfer-Updater"
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / "Updater.exe"
    shutil.copy2(source, target)
    return [str(target)], temp_dir


def _restart_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(application_install_root() / "Rechnungshelfer.exe")]
    return [sys.executable, str(application_install_root() / "main.py")]


def _materialize_online_manifest(update: OnlineUpdate) -> Path:
    temp_dir = Path(tempfile.gettempdir()) / "Rechnungshelfer-Updater"
    temp_dir.mkdir(parents=True, exist_ok=True)
    path = temp_dir / "application-manifest.json"
    manifest = update.summary.manifest
    data = {
        "schema_version": manifest.schema_version,
        "kind": "application",
        "channel": manifest.channel,
        "version": str(manifest.version),
        "package": {
            "url": update.package_url,
            "size": manifest.package.size,
            "sha256": manifest.package.sha256,
        },
        "release_notes_url": update.release_url,
        "mandatory": manifest.mandatory,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def launch_application_update(source: str | Path | OnlineUpdate) -> subprocess.Popen:
    if isinstance(source, OnlineUpdate):
        manifest_source: str | Path = _materialize_online_manifest(source)
    else:
        describe_application_update(source)
        manifest_source = source
    if not getattr(sys, "frozen", False):
        raise UpdateError("Ein vollstaendiges Anwendungsupdate kann nur an einem One-Folder-Build getestet werden.")
    command, temp_dir = _updater_command()
    command.extend([
        "--manifest", str(manifest_source),
        "--install-root", str(application_install_root()),
        "--pid", str(os.getpid()),
        "--current-version", APP_VERSION,
        "--restart-command-json", json.dumps(_restart_command()),
    ])
    try:
        return subprocess.Popen(
            command,
            cwd=str(application_install_root()),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise UpdateError(f"Updater konnte nicht gestartet werden: {exc}") from exc
