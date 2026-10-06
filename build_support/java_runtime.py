"""Validiert die lokale Java-Laufzeit gegen bewusst freigegebene Metadaten."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


TRUSTED_RELEASES_PATH = Path("build_support/java_trusted_releases.json")
REQUIRED_MODULES = frozenset({
    "java.base",
    "java.compiler",
    "java.desktop",
    "java.logging",
    "java.xml",
    "jdk.httpserver",
})


class JavaRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class JavaRuntime:
    version: str
    runtime_version: str
    implementor: str
    implementor_version: str
    image_type: str
    os_name: str
    os_arch: str
    jvm: str
    modules: frozenset[str]
    package_filename: str
    package_url: str
    package_size: int
    package_sha256: str


def _load_json_object(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JavaRuntimeError(f"Java-Metadaten konnten nicht gelesen werden: {path}") from exc
    if not isinstance(data, dict):
        raise JavaRuntimeError(f"Java-Metadaten sind ungueltig: {path}")
    return data


def _installed_component_version(project_root: Path) -> str:
    path = project_root / "external" / "components.json"
    data = _load_json_object(path)
    components = data.get("components")
    version = components.get("java-runtime") if isinstance(components, dict) else None
    if not isinstance(version, str) or not version:
        raise JavaRuntimeError(f"Java-Version fehlt im Komponentenregister: {path}")
    return version


def _release_metadata(project_root: Path) -> dict[str, str]:
    path = project_root / "external" / "java" / "release"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise JavaRuntimeError(f"Java-Releaseinformationen fehlen: {path}") from exc
    metadata = {}
    for line in lines:
        match = re.fullmatch(r'([A-Z][A-Z0-9_]*)="(.*)"', line.strip())
        if match:
            metadata[match.group(1)] = match.group(2)
    return metadata


def validate_installed_runtime(project_root: Path) -> JavaRuntime:
    """Prueft Herkunftsmetadaten und KoSIT-relevante Module der lokalen JRE."""
    version = _installed_component_version(project_root)
    trust_path = project_root / TRUSTED_RELEASES_PATH
    trust = _load_json_object(trust_path)
    releases = trust.get("releases")
    record = releases.get(version) if trust.get("schema_version") == 1 and isinstance(releases, dict) else None
    if not isinstance(record, dict):
        raise JavaRuntimeError(f"Java {version} ist nicht in {trust_path} freigegeben.")

    package = record.get("package")
    if not isinstance(package, dict):
        raise JavaRuntimeError(f"Paketangaben fuer Java {version} sind ungueltig.")
    filename = package.get("filename")
    url = package.get("url")
    size = package.get("size")
    sha256 = package.get("sha256")
    if not isinstance(filename, str) or not filename.endswith(".zip"):
        raise JavaRuntimeError(f"Java-Paketname fuer {version} ist ungueltig.")
    parsed_url = urlparse(url) if isinstance(url, str) else None
    if (
        parsed_url is None
        or parsed_url.scheme != "https"
        or parsed_url.hostname != "github.com"
        or not parsed_url.path.startswith("/adoptium/temurin21-binaries/releases/download/")
        or not url.endswith(filename)
    ):
        raise JavaRuntimeError(f"Java-Paket-URL fuer {version} ist ungueltig.")
    if not isinstance(size, int) or size <= 0:
        raise JavaRuntimeError(f"Java-Paketgroesse fuer {version} ist ungueltig.")
    if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise JavaRuntimeError(f"Java-Paket-SHA-256 fuer {version} ist ungueltig.")

    metadata = _release_metadata(project_root)
    expected = {
        "JAVA_VERSION": version,
        "JAVA_RUNTIME_VERSION": record.get("runtime_version"),
        "IMPLEMENTOR": record.get("implementor"),
        "IMPLEMENTOR_VERSION": record.get("implementor_version"),
        "IMAGE_TYPE": record.get("image_type"),
        "OS_NAME": record.get("os_name"),
        "OS_ARCH": record.get("os_arch"),
    }
    mismatches = [
        f"{key}: erwartet {value!r}, gefunden {metadata.get(key)!r}"
        for key, value in expected.items()
        if not isinstance(value, str) or metadata.get(key) != value
    ]
    if mismatches:
        raise JavaRuntimeError("Lokale Java-Laufzeit entspricht nicht der Freigabe: " + "; ".join(mismatches))
    jvm = record.get("jvm")
    if not isinstance(jvm, str) or metadata.get("JVM_VARIANT", "").casefold() != jvm.casefold():
        raise JavaRuntimeError(
            "Lokale Java-Laufzeit entspricht nicht der freigegebenen JVM: "
            f"erwartet {jvm!r}, gefunden {metadata.get('JVM_VARIANT')!r}"
        )

    modules = frozenset(metadata.get("MODULES", "").split())
    missing_modules = sorted(REQUIRED_MODULES - modules)
    if missing_modules:
        raise JavaRuntimeError(
            "Lokaler Java-Laufzeit fehlen KoSIT-Module: " + ", ".join(missing_modules)
        )
    java_exe = project_root / "external" / "java" / "bin" / "java.exe"
    if not java_exe.is_file():
        raise JavaRuntimeError(f"Java-Programm fehlt: {java_exe}")

    return JavaRuntime(
        version=version,
        runtime_version=metadata["JAVA_RUNTIME_VERSION"],
        implementor=metadata["IMPLEMENTOR"],
        implementor_version=metadata["IMPLEMENTOR_VERSION"],
        image_type=metadata["IMAGE_TYPE"],
        os_name=metadata["OS_NAME"],
        os_arch=metadata["OS_ARCH"],
        jvm=jvm,
        modules=modules,
        package_filename=filename,
        package_url=url,
        package_size=size,
        package_sha256=sha256,
    )
