"""Read-only check of the official Tesseract GitHub release channel."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from packaging.version import InvalidVersion, Version


LATEST_RELEASE_URL = "https://api.github.com/repos/tesseract-ocr/tesseract/releases/latest"
RELEASE_PAGE_PREFIX = "https://github.com/tesseract-ocr/tesseract/releases/tag/"
RELEASE_DOWNLOAD_PREFIX = "https://github.com/tesseract-ocr/tesseract/releases/download/"
MAX_API_BYTES = 2 * 1024 * 1024
MAX_INSTALLER_BYTES = 250 * 1024 * 1024
USER_AGENT = "Rechnungshelfer-Tesseract-Checker/1"
INSTALLER_PATTERN = re.compile(
    r"tesseract-ocr-w64-setup-(?P<version>\d+(?:\.\d+){3})\.exe",
    re.IGNORECASE,
)


class TesseractReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class TesseractRelease:
    version: Version
    package_version: Version
    page_url: str
    installer_name: str
    installer_url: str
    installer_size: int
    github_sha256: str | None = None
    immutable: bool = False


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
        raise TesseractReleaseError("Tesseract-Releaseantwort ist zu gross.")
    return data


def _parse_release(data: dict) -> TesseractRelease:
    if data.get("draft") or data.get("prerelease"):
        raise TesseractReleaseError("GitHub lieferte kein stabiles Tesseract-Release.")
    tag = data.get("tag_name")
    if not isinstance(tag, str):
        raise TesseractReleaseError("Tesseract-Release enthaelt keine Versionsnummer.")
    try:
        version = Version(tag.removeprefix("v"))
    except InvalidVersion as exc:
        raise TesseractReleaseError(f"Ungueltige Tesseract-Version: {tag}") from exc

    page_url = data.get("html_url")
    if not isinstance(page_url, str) or not page_url.startswith(RELEASE_PAGE_PREFIX):
        raise TesseractReleaseError("Tesseract-Release besitzt keine erlaubte offizielle Seite.")
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise TesseractReleaseError("Tesseract-Release enthaelt keine Assetliste.")
    matches = []
    for asset in assets:
        name = asset.get("name") if isinstance(asset, dict) else None
        if isinstance(name, str) and INSTALLER_PATTERN.fullmatch(name):
            matches.append(asset)
    if len(matches) != 1:
        raise TesseractReleaseError(
            "Offizieller 64-Bit-Windows-Installer fehlt oder ist nicht eindeutig."
        )

    asset = matches[0]
    name = asset["name"]
    match = INSTALLER_PATTERN.fullmatch(name)
    assert match is not None
    package_version = Version(match.group("version"))
    url = asset.get("browser_download_url")
    size = asset.get("size")
    if not isinstance(url, str) or not url.startswith(RELEASE_DOWNLOAD_PREFIX):
        raise TesseractReleaseError("Tesseract-Installer besitzt keine erlaubte Downloadadresse.")
    if not isinstance(size, int) or not 0 < size <= MAX_INSTALLER_BYTES:
        raise TesseractReleaseError("Tesseract-Installer besitzt eine ungueltige Groesse.")

    digest = asset.get("digest")
    sha256 = None
    if digest is not None:
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise TesseractReleaseError("GitHub meldet einen ungueltigen Installer-Digest.")
        sha256 = digest.removeprefix("sha256:").lower()
        if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
            raise TesseractReleaseError("GitHub meldet einen ungueltigen SHA-256-Digest.")

    return TesseractRelease(
        version=version,
        package_version=package_version,
        page_url=page_url,
        installer_name=name,
        installer_url=url,
        installer_size=size,
        github_sha256=sha256,
        immutable=data.get("immutable") is True,
    )


def fetch_latest_release() -> TesseractRelease:
    try:
        with _open_url(LATEST_RELEASE_URL) as response:
            payload = _read_limited(response, MAX_API_BYTES)
        data = json.loads(payload.decode("utf-8"))
    except (OSError, urllib.error.URLError, UnicodeError, json.JSONDecodeError) as exc:
        raise TesseractReleaseError(
            f"Tesseract-Releasestand konnte nicht abgefragt werden: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise TesseractReleaseError("Tesseract-Releaseantwort ist ungueltig.")
    return _parse_release(data)


__all__ = [
    "TesseractRelease",
    "TesseractReleaseError",
    "fetch_latest_release",
]
