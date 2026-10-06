from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

from app_info import APP_EXECUTABLE_NAME


project_root = Path.cwd()
version_info_path = project_root / "build" / "windows-version-info.txt"
required_directories = (
    project_root / "assets",
    project_root / "external" / "java",
    project_root / "external" / "kosit",
)
component_registry = project_root / "external" / "components.json"
ubl_invoice_schema = (
    project_root
    / "external"
    / "kosit"
    / "xrechnung"
    / "resources"
    / "ubl"
    / "2.1"
    / "xsd"
    / "maindoc"
    / "UBL-Invoice-2.1.xsd"
)

missing = [str(path) for path in required_directories if not path.is_dir()]
missing.extend(
    str(path)
    for path in (component_registry, ubl_invoice_schema)
    if not path.is_file()
)
if missing:
    raise SystemExit(
        "Fuer den One-Folder-Build fehlen benoetigte Verzeichnisse:\n- "
        + "\n- ".join(missing)
    )

generated_reports = sorted(
    path
    for pattern in ("*-report.xml", "*-report.html")
    for path in (project_root / "external" / "kosit").rglob(pattern)
)
if generated_reports:
    raise SystemExit(
        "Erzeugte KoSIT-Pruefberichte duerfen nicht in den Build:\n- "
        + "\n- ".join(str(path) for path in generated_reports)
    )

if not version_info_path.is_file():
    raise SystemExit(
        "Windows-Versionsdatei fehlt. Zuerst ausfuehren: "
        "python build_support/generate_windows_version_info.py"
    )

datas = collect_data_files("customtkinter")
datas.extend(
    [
        (str(project_root / "assets"), "assets"),
        (str(project_root / "external" / "java"), "external/java"),
        (str(project_root / "external" / "kosit"), "external/kosit"),
        (str(component_registry), "external"),
    ]
)

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Herausgeberwerkzeuge und Tests duerfen nie Teil der Benutzeranwendung sein.
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
    [],
    exclude_binaries=True,
    name=APP_EXECUTABLE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    version=str(version_info_path),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_EXECUTABLE_NAME,
)
