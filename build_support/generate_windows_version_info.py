"""Erzeugt PyInstallers Windows-Versionsressource aus app_info.py."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packaging.version import Version

from app_info import (
    APP_DESCRIPTION,
    APP_EXECUTABLE_NAME,
    APP_NAME,
    APP_PUBLISHER,
    APP_VERSION,
)


OUTPUT_PATH = PROJECT_ROOT / "build" / "windows-version-info.txt"
UPDATER_OUTPUT_PATH = PROJECT_ROOT / "build" / "windows-updater-version-info.txt"


def _windows_version_tuple(version: str) -> tuple[int, int, int, int]:
    release = Version(version).release[:4]
    return (*release, *((0,) * (4 - len(release))))


def generate(
    output_path: Path = OUTPUT_PATH,
    executable_name: str = APP_EXECUTABLE_NAME,
    description: str = APP_DESCRIPTION,
) -> Path:
    numeric_version = _windows_version_tuple(APP_VERSION)
    version_tuple = ", ".join(str(part) for part in numeric_version)
    original_filename = f"{executable_name}.exe"

    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({version_tuple}),
    prodvers=({version_tuple}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040704B0',
        [
          StringStruct('CompanyName', {APP_PUBLISHER!r}),
          StringStruct('FileDescription', {description!r}),
          StringStruct('FileVersion', {APP_VERSION!r}),
          StringStruct('InternalName', {executable_name!r}),
          StringStruct('OriginalFilename', {original_filename!r}),
          StringStruct('ProductName', {APP_NAME!r}),
          StringStruct('ProductVersion', {APP_VERSION!r})
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1031, 1200])])
  ]
)
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def generate_updater() -> Path:
    return generate(
        output_path=UPDATER_OUTPUT_PATH,
        executable_name="Updater",
        description="Sicherer Updater fuer Rechnungshelfer",
    )


if __name__ == "__main__":
    print(generate())
    print(generate_updater())
