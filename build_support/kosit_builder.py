"""Prueft den offiziellen KoSIT-Releasekanal und aktualisiert das Quellprojekt."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packaging.version import InvalidVersion, Version

from build_support.create_update_manifest import create_component_package
from updater.core import UpdateError
from updater.external_components_update import update_external_components


LATEST_RELEASE_URL = "https://api.github.com/repos/itplr-kosit/validator/releases/latest"
RELEASE_DOWNLOAD_PREFIX = "https://github.com/itplr-kosit/validator/releases/download/"
MAX_API_BYTES = 2 * 1024 * 1024
MAX_JAR_BYTES = 250 * 1024 * 1024
USER_AGENT = "Rechnungshelfer-KoSIT-Builder/1"


class KositBuilderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class KositRelease:
    version: Version
    page_url: str
    asset: ReleaseAsset


def _open_url(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    return urllib.request.urlopen(request, timeout=30)


def _read_limited(response, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise KositBuilderError("Antwort ist groesser als das erlaubte Limit.")
    return data


def _parse_release(data: dict) -> KositRelease:
    if data.get("draft") or data.get("prerelease"):
        raise KositBuilderError("GitHub lieferte kein stabiles KoSIT-Release.")
    tag = data.get("tag_name")
    if not isinstance(tag, str):
        raise KositBuilderError("KoSIT-Release enthaelt keine Versionsnummer.")
    try:
        version = Version(tag.removeprefix("v"))
    except InvalidVersion as exc:
        raise KositBuilderError(f"Ungueltige KoSIT-Version: {tag}") from exc
    expected_name = f"validator-{version}-standalone.jar"
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise KositBuilderError("KoSIT-Release enthaelt keine Assetliste.")
    matches = [asset for asset in assets if asset.get("name") == expected_name]
    if len(matches) != 1:
        raise KositBuilderError(f"Release-Asset fehlt oder ist nicht eindeutig: {expected_name}")
    asset = matches[0]
    url = asset.get("browser_download_url")
    size = asset.get("size")
    digest = asset.get("digest")
    if not isinstance(url, str) or not url.startswith(RELEASE_DOWNLOAD_PREFIX):
        raise KositBuilderError("KoSIT-Asset besitzt keine erlaubte offizielle Downloadadresse.")
    if not isinstance(size, int) or not 0 < size <= MAX_JAR_BYTES:
        raise KositBuilderError("KoSIT-Asset besitzt eine ungueltige Groesse.")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise KositBuilderError(
            "GitHub liefert fuer dieses Asset keinen SHA-256-Digest; automatisches Update abgebrochen."
        )
    sha256 = digest.removeprefix("sha256:").lower()
    if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
        raise KositBuilderError("KoSIT-Asset besitzt einen ungueltigen SHA-256-Digest.")
    page_url = data.get("html_url")
    if not isinstance(page_url, str):
        page_url = f"https://github.com/itplr-kosit/validator/releases/tag/{tag}"
    return KositRelease(version, page_url, ReleaseAsset(expected_name, url, size, sha256))


def fetch_latest_release() -> KositRelease:
    try:
        with _open_url(LATEST_RELEASE_URL) as response:
            payload = _read_limited(response, MAX_API_BYTES)
        data = json.loads(payload.decode("utf-8"))
    except (OSError, urllib.error.URLError, UnicodeError, json.JSONDecodeError) as exc:
        raise KositBuilderError(f"KoSIT-Releasestand konnte nicht abgefragt werden: {exc}") from exc
    if not isinstance(data, dict):
        raise KositBuilderError("KoSIT-Releaseantwort ist ungueltig.")
    return _parse_release(data)


def installed_version(project_root: Path) -> Version:
    path = project_root / "external" / "components.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data["components"]["kosit-validator"]
        return Version(str(value))
    except (OSError, KeyError, TypeError, json.JSONDecodeError, InvalidVersion) as exc:
        raise KositBuilderError(f"Installierte KoSIT-Version ist nicht lesbar: {path}") from exc


def _download_verified(asset: ReleaseAsset, destination: Path) -> None:
    digest = hashlib.sha256()
    total = 0
    try:
        with _open_url(asset.url) as response, destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > asset.size or total > MAX_JAR_BYTES:
                    raise KositBuilderError("KoSIT-Download ist groesser als im Release angegeben.")
                digest.update(chunk)
                output.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        destination.unlink(missing_ok=True)
        raise KositBuilderError(f"KoSIT konnte nicht heruntergeladen werden: {exc}") from exc
    if total != asset.size:
        destination.unlink(missing_ok=True)
        raise KositBuilderError(f"KoSIT-Dateigroesse stimmt nicht: {total} statt {asset.size} Bytes.")
    if digest.hexdigest() != asset.sha256:
        destination.unlink(missing_ok=True)
        raise KositBuilderError("SHA-256 des KoSIT-Downloads stimmt nicht mit GitHub ueberein.")


def install_release(project_root: Path, release: KositRelease) -> None:
    """Installiert genau den zuvor geprueften Release in das Quellprojekt."""
    project_root = project_root.resolve()
    with tempfile.TemporaryDirectory(prefix="Rechnungshelfer-KoSIT-") as directory:
        work_root = Path(directory)
        source = work_root / "source"
        source.mkdir()
        jar = source / release.asset.name
        _download_verified(release.asset, jar)
        _, manifest = create_component_package(
            "kosit-validator",
            str(release.version),
            source,
            work_root / "package",
            "test",
        )
        update_external_components(manifest, project_root)


def check_and_update(project_root: Path, *, check_only: bool = False) -> bool:
    project_root = project_root.resolve()
    current = installed_version(project_root)
    release = fetch_latest_release()
    print(f"Installiert: KoSIT {current}")
    print(f"Offiziell verfuegbar: KoSIT {release.version}")
    print(f"Release: {release.page_url}")
    if release.version <= current:
        print("KoSIT ist aktuell; keine Aenderung erforderlich.")
        return False
    if check_only:
        print("Eine neuere KoSIT-Version ist verfuegbar.")
        return True

    install_release(project_root, release)
    print(f"KoSIT wurde erfolgreich auf {release.version} aktualisiert.")
    print("Vor einem Release jetzt die komplette Testsuite ausfuehren.")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prueft KoSIT und aktualisiert bei Bedarf das Rechnungshelfer-Quellprojekt."
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    try:
        check_and_update(args.project_root, check_only=args.check_only)
    except (KositBuilderError, UpdateError) as exc:
        parser.exit(1, f"Fehler: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
