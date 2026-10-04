"""Manifest-, Download-, Archiv- und Transaktionslogik fuer Updates."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from packaging.version import InvalidVersion, Version


MAX_MANIFEST_BYTES = 1_000_000
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024

APPLICATION_MANAGED_PATHS = {
    "Rechnungshelfer.exe",
    "_internal",
}
REQUIRED_APPLICATION_PATHS = {"Rechnungshelfer.exe", "_internal"}
COMPONENT_MANAGED_PATHS = {
    "kosit-validator": ("external/kosit/validator",),
    "xrechnung-configuration": ("external/kosit/xrechnung",),
    "ubl-schemas": ("external/ubl",),
    "java-runtime": ("external/java",),
}


class UpdateError(RuntimeError):
    """Kontrollierter Fehler bei Pruefung oder Installation eines Updates."""


def _is_windows_drive_path(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[0].isalpha() and value[2] in "\\/"


def _required_string(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UpdateError(f"Manifestfeld fehlt oder ist ungueltig: {key}")
    return value.strip()


def _version(value: str, field: str = "version") -> Version:
    try:
        return Version(value)
    except InvalidVersion as exc:
        raise UpdateError(f"Ungueltige Version in {field}: {value}") from exc


@dataclass(frozen=True)
class PackageSpec:
    url: str
    size: int
    sha256: str

    @classmethod
    def from_dict(cls, data: object) -> "PackageSpec":
        if not isinstance(data, dict):
            raise UpdateError("Manifestfeld 'package' muss ein Objekt sein.")
        url = _required_string(data, "url")
        size = data.get("size")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
            or size > MAX_PACKAGE_BYTES
        ):
            raise UpdateError("Paketgroesse muss eine positive Ganzzahl sein.")
        sha256 = _required_string(data, "sha256").lower()
        if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
            raise UpdateError("Paket-SHA-256 ist ungueltig.")
        return cls(url=url, size=size, sha256=sha256)


@dataclass(frozen=True)
class ApplicationManifest:
    schema_version: int
    channel: str
    version: Version
    package: PackageSpec
    release_notes_url: str = ""
    mandatory: bool = False


@dataclass(frozen=True)
class ComponentUpdate:
    component_id: str
    version: Version
    package: PackageSpec

    @property
    def managed_paths(self) -> tuple[str, ...]:
        try:
            return COMPONENT_MANAGED_PATHS[self.component_id]
        except KeyError as exc:
            raise UpdateError(f"Unbekannte externe Komponente: {self.component_id}") from exc


@dataclass(frozen=True)
class ComponentsManifest:
    schema_version: int
    channel: str
    components: tuple[ComponentUpdate, ...]


Manifest = ApplicationManifest | ComponentsManifest
ByteProgress = Callable[[int, int], None]
UpdateProgress = Callable[[int, str], None]


def _report_progress(progress: UpdateProgress | None, percent: int, message: str) -> None:
    if progress is not None:
        progress(max(0, min(100, percent)), message)


def _read_source(source: str | Path, *, limit: int = MAX_MANIFEST_BYTES) -> bytes:
    if isinstance(source, Path):
        try:
            data = source.expanduser().resolve().read_bytes()
        except OSError as exc:
            raise UpdateError(f"Updatedatei konnte nicht gelesen werden: {exc}") from exc
        if len(data) > limit:
            raise UpdateError("Update-Manifest ist unerwartet gross.")
        return data
    source_text = str(source)
    parsed = urllib.parse.urlparse(source_text)
    if parsed.scheme and not _is_windows_drive_path(source_text):
        if parsed.scheme.lower() != "https":
            raise UpdateError("Remote Updates sind ausschliesslich ueber HTTPS erlaubt.")
        request = urllib.request.Request(
            source_text,
            headers={"User-Agent": "Rechnungshelfer-Updater/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if urllib.parse.urlparse(response.geturl()).scheme.lower() != "https":
                    raise UpdateError("Das Update wurde auf eine unsichere URL umgeleitet.")
                data = response.read(limit + 1)
        except UpdateError:
            raise
        except Exception as exc:
            raise UpdateError(f"Updatequelle konnte nicht geladen werden: {exc}") from exc
    else:
        try:
            data = Path(source_text).expanduser().resolve().read_bytes()
        except OSError as exc:
            raise UpdateError(f"Updatedatei konnte nicht gelesen werden: {exc}") from exc
    if len(data) > limit:
        raise UpdateError("Update-Manifest ist unerwartet gross.")
    return data


def parse_manifest_bytes(payload: bytes) -> Manifest:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("Update-Manifest ist kein gueltiges UTF-8-JSON.") from exc
    if not isinstance(data, dict):
        raise UpdateError("Update-Manifest muss ein JSON-Objekt sein.")
    if data.get("schema_version") != 1:
        raise UpdateError("Nicht unterstuetzte Manifestversion.")
    channel = _required_string(data, "channel")
    kind = _required_string(data, "kind")
    if kind == "application":
        return ApplicationManifest(
            schema_version=1,
            channel=channel,
            version=_version(_required_string(data, "version")),
            package=PackageSpec.from_dict(data.get("package")),
            release_notes_url=str(data.get("release_notes_url") or ""),
            mandatory=bool(data.get("mandatory", False)),
        )
    if kind == "components":
        entries = data.get("components")
        if not isinstance(entries, list) or not entries:
            raise UpdateError("Komponentenmanifest enthaelt keine Updates.")
        if len(entries) != 1:
            raise UpdateError("Ein Komponentenmanifest muss genau ein atomar installierbares Update enthalten.")
        components = []
        seen = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise UpdateError(f"Komponenteneintrag {index + 1} ist ungueltig.")
            component_id = _required_string(entry, "id")
            if component_id in seen:
                raise UpdateError(f"Komponente ist doppelt im Manifest: {component_id}")
            seen.add(component_id)
            component = ComponentUpdate(
                component_id=component_id,
                version=_version(_required_string(entry, "version"), f"components[{index}].version"),
                package=PackageSpec.from_dict(entry.get("package")),
            )
            component.managed_paths
            components.append(component)
        return ComponentsManifest(1, channel, tuple(components))
    raise UpdateError(f"Unbekannter Manifesttyp: {kind}")


def load_manifest(source: str | Path) -> Manifest:
    return parse_manifest_bytes(_read_source(source))


def _resolve_package_source(manifest_source: str | Path, reference: str) -> str | Path:
    parsed_reference = urllib.parse.urlparse(reference)
    if _is_windows_drive_path(reference):
        return Path(reference).resolve()
    if parsed_reference.scheme:
        if parsed_reference.scheme.lower() != "https":
            raise UpdateError("Paketdownloads sind ausschliesslich ueber HTTPS erlaubt.")
        return reference
    if isinstance(manifest_source, Path):
        return (manifest_source.expanduser().resolve().parent / reference).resolve()
    manifest_text = str(manifest_source)
    parsed_manifest = urllib.parse.urlparse(manifest_text)
    if parsed_manifest.scheme and not _is_windows_drive_path(manifest_text):
        resolved = urllib.parse.urljoin(manifest_text, reference)
        if urllib.parse.urlparse(resolved).scheme.lower() != "https":
            raise UpdateError("Relative Paket-URL fuehrt nicht zu HTTPS.")
        return resolved
    return (Path(manifest_text).expanduser().resolve().parent / reference).resolve()


def download_verified_package(
    package: PackageSpec,
    manifest_source: str | Path,
    destination_dir: Path,
    *,
    progress: ByteProgress | None = None,
) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "package.zip"
    source = _resolve_package_source(manifest_source, package.url)
    digest = hashlib.sha256()
    written = 0
    try:
        parsed = urllib.parse.urlparse(str(source))
        if not isinstance(source, Path) and parsed.scheme:
            request = urllib.request.Request(
                str(source),
                headers={"User-Agent": "Rechnungshelfer-Updater/1"},
            )
            response = urllib.request.urlopen(request, timeout=60)
            if urllib.parse.urlparse(response.geturl()).scheme.lower() != "https":
                response.close()
                raise UpdateError("Der Paketdownload wurde auf eine unsichere URL umgeleitet.")
            input_stream = response
        else:
            input_stream = Path(source).open("rb")
        with input_stream, destination.open("wb") as output:
            while chunk := input_stream.read(1024 * 1024):
                written += len(chunk)
                if written > package.size:
                    raise UpdateError("Paket ist groesser als im Manifest angegeben.")
                digest.update(chunk)
                output.write(chunk)
                if progress is not None:
                    progress(written, package.size)
    except UpdateError:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise UpdateError(f"Updatepaket konnte nicht geladen werden: {exc}") from exc
    if written != package.size:
        destination.unlink(missing_ok=True)
        raise UpdateError("Paketgroesse stimmt nicht mit dem Manifest ueberein.")
    if digest.hexdigest().lower() != package.sha256:
        destination.unlink(missing_ok=True)
        raise UpdateError("SHA-256-Pruefung des Updatepakets ist fehlgeschlagen.")
    return destination


def _safe_archive_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if not members or len(members) > MAX_ARCHIVE_ENTRIES:
        raise UpdateError("Updatearchiv enthaelt eine ungueltige Anzahl Dateien.")
    total_size = 0
    seen = set()
    for info in members:
        if "\\" in info.filename:
            raise UpdateError(f"Ungueltiger Archivpfad: {info.filename}")
        path = PurePosixPath(info.filename)
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise UpdateError(f"Unsicherer Archivpfad: {info.filename}")
        normalized = "/".join(path.parts).rstrip("/").casefold()
        if normalized in seen and normalized:
            raise UpdateError(f"Doppelter Archivpfad: {info.filename}")
        seen.add(normalized)
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise UpdateError(f"Symbolische Links sind im Update nicht erlaubt: {info.filename}")
        total_size += info.file_size
        if total_size > MAX_UNCOMPRESSED_BYTES:
            raise UpdateError("Entpacktes Updatearchiv ist unerwartet gross.")
    return members


def extract_verified_archive(
    package_path: Path,
    destination: Path,
    *,
    progress: ByteProgress | None = None,
) -> set[str]:
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(package_path) as archive:
            members = _safe_archive_members(archive)
            total_size = sum(info.file_size for info in members)
            extracted_size = 0
            top_level = set()
            for info in members:
                relative = PurePosixPath(info.filename)
                top_level.add(relative.parts[0])
                target = destination.joinpath(*relative.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                extracted_size += info.file_size
                if progress is not None:
                    progress(extracted_size, total_size)
            return top_level
    except UpdateError:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise UpdateError(f"Updatearchiv konnte nicht sicher entpackt werden: {exc}") from exc


class UpdateTransaction:
    """Ersetzt Pfade auf demselben Laufwerk und kann sie vollstaendig zurueckrollen."""

    def __init__(self, install_root: Path, extracted_root: Path, managed_paths: tuple[str, ...]):
        self.install_root = install_root.resolve()
        self.extracted_root = extracted_root.resolve()
        self.managed_paths = tuple(managed_paths)
        self.backup_root = self.extracted_root.parent / "backup"
        self._replaced: list[tuple[Path, Path | None]] = []
        self._finished = False

    def apply(self) -> None:
        if self._replaced:
            raise UpdateError("Update-Transaktion wurde bereits gestartet.")
        self.backup_root.mkdir(parents=True, exist_ok=False)
        try:
            for relative_text in self.managed_paths:
                relative = PurePosixPath(relative_text)
                source = self.extracted_root.joinpath(*relative.parts)
                target = self.install_root.joinpath(*relative.parts)
                if not source.exists():
                    raise UpdateError(f"Updatepaket enthaelt den verwalteten Pfad nicht: {relative_text}")
                backup = self.backup_root.joinpath(*relative.parts)
                backup.parent.mkdir(parents=True, exist_ok=True)
                previous = backup if target.exists() else None
                if previous is not None:
                    os.replace(target, previous)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, target)
                self._replaced.append((target, previous))
        except Exception as exc:
            self.rollback()
            if isinstance(exc, UpdateError):
                raise
            raise UpdateError(f"Update konnte nicht installiert werden: {exc}") from exc

    def commit(self) -> None:
        if self._finished:
            return
        shutil.rmtree(self.backup_root, ignore_errors=True)
        self._finished = True

    def rollback(self) -> None:
        if self._finished:
            return
        errors = []
        for target, previous in reversed(self._replaced):
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
                if previous is not None and previous.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(previous, target)
            except Exception as exc:
                errors.append(str(exc))
        self._finished = True
        if errors:
            raise UpdateError("Rollback war unvollstaendig: " + "; ".join(errors))


def _load_component_versions(install_root: Path) -> dict[str, str]:
    path = install_root / "external" / "components.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdateError(f"Komponentenstatus ist unlesbar: {exc}") from exc
    components = data.get("components", {}) if isinstance(data, dict) else {}
    if not isinstance(components, dict):
        raise UpdateError("Komponentenstatus ist ungueltig.")
    return {str(key): str(value) for key, value in components.items()}


def _write_component_versions(install_root: Path, versions: dict[str, str]) -> None:
    path = install_root / "external" / "components.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(
        json.dumps({"schema_version": 1, "components": versions}, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def apply_component_updates(
    manifest: ComponentsManifest,
    manifest_source: str | Path,
    install_root: Path,
    *,
    validator: Callable[[ComponentUpdate, Path], None] | None = None,
    allow_downgrade: bool = False,
) -> dict[str, str]:
    install_root = install_root.resolve()
    versions = _load_component_versions(install_root)
    for component in manifest.components:
        current_text = versions.get(component.component_id)
        if current_text and not allow_downgrade and component.version <= _version(current_text):
            raise UpdateError(
                f"{component.component_id} {component.version} ist nicht neuer als {current_text}."
            )
        work_root = Path(tempfile.mkdtemp(prefix=".component-update-", dir=install_root.parent))
        transaction = None
        try:
            package = download_verified_package(component.package, manifest_source, work_root)
            extracted = work_root / "extracted"
            top_level = extract_verified_archive(package, extracted)
            if top_level != {"external"}:
                raise UpdateError("Komponentenpaket darf nur den Ordner 'external' enthalten.")
            allowed_prefixes = tuple(path.rstrip("/") + "/" for path in component.managed_paths)
            unexpected_files = [
                path.relative_to(extracted).as_posix()
                for path in extracted.rglob("*")
                if path.is_file()
                and not path.relative_to(extracted).as_posix().startswith(allowed_prefixes)
            ]
            if unexpected_files:
                raise UpdateError(
                    "Komponentenpaket enthaelt nicht freigegebene Dateien: "
                    + ", ".join(unexpected_files[:5])
                )
            transaction = UpdateTransaction(install_root, extracted, component.managed_paths)
            transaction.apply()
            if validator:
                validator(component, install_root)
            versions[component.component_id] = str(component.version)
            _write_component_versions(install_root, versions)
            transaction.commit()
        except Exception:
            if transaction is not None:
                transaction.rollback()
            raise
        finally:
            shutil.rmtree(work_root, ignore_errors=True)
    return versions


def prepare_application_update(
    manifest: ApplicationManifest,
    manifest_source: str | Path,
    install_root: Path,
    *,
    current_version: str,
    allow_downgrade: bool = False,
    progress: UpdateProgress | None = None,
) -> tuple[UpdateTransaction, Path]:
    if not allow_downgrade and manifest.version <= _version(current_version, "current_version"):
        raise UpdateError(f"Version {manifest.version} ist nicht neuer als {current_version}.")
    install_root = install_root.resolve()
    work_root = Path(tempfile.mkdtemp(prefix=".application-update-", dir=install_root.parent))
    try:
        _report_progress(progress, 8, "Download wird vorbereitet ...")
        package = download_verified_package(
            manifest.package,
            manifest_source,
            work_root,
            progress=lambda done, total: _report_progress(
                progress,
                10 + int((done / total) * 60) if total else 70,
                f"Update wird heruntergeladen ... {int((done / total) * 100) if total else 100}%",
            ),
        )
        _report_progress(progress, 72, "Download und SHA-256 wurden geprueft.")
        extracted = work_root / "extracted"
        top_level = extract_verified_archive(
            package,
            extracted,
            progress=lambda done, total: _report_progress(
                progress,
                75 + int((done / total) * 15) if total else 90,
                "Updatepaket wird entpackt ...",
            ),
        )
        _report_progress(progress, 92, "Updatepaket wird kontrolliert ...")
        folded = {item.casefold() for item in top_level}
        if "data" in folded:
            raise UpdateError("Anwendungsupdate darf keinen data-Ordner enthalten.")
        if not REQUIRED_APPLICATION_PATHS.issubset(top_level):
            missing = sorted(REQUIRED_APPLICATION_PATHS - top_level)
            raise UpdateError("Anwendungsupdate ist unvollstaendig: " + ", ".join(missing))
        unexpected = top_level - APPLICATION_MANAGED_PATHS
        if unexpected:
            raise UpdateError("Anwendungsupdate enthaelt unbekannte Hauptpfade: " + ", ".join(sorted(unexpected)))
        managed = tuple(sorted(top_level))
        transaction = UpdateTransaction(install_root, extracted, managed)
        _report_progress(progress, 95, "Programmdateien werden ausgetauscht ...")
        transaction.apply()
        _report_progress(progress, 98, "Programmdateien wurden erfolgreich installiert.")
        return transaction, work_root
    except Exception:
        shutil.rmtree(work_root, ignore_errors=True)
        raise


def apply_application_update(
    manifest: ApplicationManifest,
    manifest_source: str | Path,
    install_root: Path,
    *,
    current_version: str,
    validator: Callable[[Path], None] | None = None,
    allow_downgrade: bool = False,
    progress: UpdateProgress | None = None,
) -> None:
    transaction, work_root = prepare_application_update(
        manifest,
        manifest_source,
        install_root,
        current_version=current_version,
        allow_downgrade=allow_downgrade,
        progress=progress,
    )
    try:
        if validator:
            validator(install_root.resolve())
        transaction.commit()
    except Exception:
        transaction.rollback()
        raise
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
