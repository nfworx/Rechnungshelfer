from pathlib import Path


project_root = Path.cwd()
version_info_path = project_root / "build" / "windows-updater-version-info.txt"

if not version_info_path.is_file():
    raise SystemExit(
        "Windows-Versionsdatei fuer den Updater fehlt. Zuerst ausfuehren: "
        "python build_support/generate_windows_version_info.py"
    )

a = Analysis(
    ["updater/runner.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Updater.exe enthaelt nur den Programmupdater fuer Endnutzer.
    excludes=[
        "build_support",
        "tests",
        "updater.external_components_update",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Updater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    version=str(version_info_path),
)
