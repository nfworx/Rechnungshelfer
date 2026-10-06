param(
    [ValidateSet("stable", "test")]
    [string]$Channel = "stable"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$java = Join-Path $PSScriptRoot "external\java\bin\java.exe"

$generatedReports = Get-ChildItem `
    -LiteralPath (Join-Path $PSScriptRoot "external\kosit") `
    -Recurse `
    -File `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "*-report.xml" -or $_.Name -like "*-report.html" }

if ($generatedReports) {
    $paths = ($generatedReports.FullName | ForEach-Object { "- $_" }) -join "`n"
    throw "Erzeugte KoSIT-Pruefberichte duerfen nicht gebaut werden:`n$paths"
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtuelle Umgebung fehlt: $python"
}

if (-not (Test-Path -LiteralPath $java)) {
    throw "Portable Java-Laufzeit fehlt: $java"
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller fehlt. Installiere die Build-Abhaengigkeiten mit: .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt"
}

& $python build_support\generate_windows_version_info.py
if ($LASTEXITCODE -ne 0) {
    throw "Windows-Versionsinformationen konnten nicht erzeugt werden."
}

$metadataJson = & $python -c "import json; from app_info import APP_EXECUTABLE_NAME, APP_VERSION; print(json.dumps({'name': APP_EXECUTABLE_NAME, 'version': APP_VERSION}))"
if ($LASTEXITCODE -ne 0) {
    throw "Produktmetadaten konnten nicht gelesen werden."
}
$metadata = $metadataJson | ConvertFrom-Json

& $python -m PyInstaller --noconfirm --clean Rechnungshelfer.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller-Build fehlgeschlagen."
}

$buildDirectory = Join-Path $PSScriptRoot "dist\$($metadata.name)"
$executable = Join-Path $buildDirectory "$($metadata.name).exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "Erwartete Programmdatei fehlt: $executable"
}

$updaterDist = Join-Path $PSScriptRoot "build\updater-dist"
$updaterWork = Join-Path $PSScriptRoot "build\updater-work"
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $updaterDist `
    --workpath $updaterWork `
    Updater.spec
if ($LASTEXITCODE -ne 0) {
    throw "Updater-Build fehlgeschlagen."
}

$builtUpdater = Join-Path $updaterDist "Updater.exe"
if (-not (Test-Path -LiteralPath $builtUpdater)) {
    throw "Erwarteter Updater fehlt: $builtUpdater"
}
$updaterTarget = Join-Path $buildDirectory "_internal\Updater.exe"
Copy-Item -LiteralPath $builtUpdater -Destination $updaterTarget -Force

$forbiddenBuildFiles = Get-ChildItem `
    -LiteralPath $buildDirectory `
    -Recurse `
    -File |
    Where-Object {
        # Windows PowerShell 5.1 runs on .NET Framework, which does not provide
        # System.IO.Path.GetRelativePath(). Every item originates below the
        # absolute build directory, so removing that prefix is sufficient here.
        $relativePath = $_.FullName.Substring($buildDirectory.Length).TrimStart("\", "/").Replace("\", "/")
        $_.Name -ieq "master_data.json" -or
        $_.Extension -in ".db", ".sqlite", ".sqlite3" -or
        $_.Name -like "*-report.xml" -or
        $_.Name -like "*-report.html" -or
        $relativePath -match "(^|/)(build_support|tests)(/|$)" -or
        $_.Name -in "build.ps1", "Rechnungshelfer.spec", "Updater.spec", "release_builder.py", "release_tool.py", "kosit_builder.py", "update_external_components.py"
    }

if ($forbiddenBuildFiles) {
    $paths = ($forbiddenBuildFiles.FullName | ForEach-Object { "- $_" }) -join "`n"
    throw "Build enthaelt unzulaessige Benutzer-, Berichts- oder Herausgeberdateien:`n$paths"
}

$releaseDirectory = Join-Path $PSScriptRoot "release"
New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null
$architecture = & $python -c "import platform; print('win64' if platform.architecture()[0] == '64bit' else 'win32')"
$archiveName = "$($metadata.name)-$($metadata.version)-$architecture.zip"
$archivePath = Join-Path $releaseDirectory $archiveName

if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
Compress-Archive -Path (Join-Path $buildDirectory "*") -DestinationPath $archivePath -CompressionLevel Optimal

$hash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$archivePath.sha256" -Value "$hash  $archiveName" -Encoding ascii

& $python build_support\create_update_manifest.py `
    application `
    --package $archivePath `
    --version $metadata.version `
    --channel $Channel
if ($LASTEXITCODE -ne 0) {
    throw "Update-Manifest konnte nicht erzeugt werden."
}

$sizeReportPath = Join-Path $releaseDirectory "$($metadata.name)-$($metadata.version)-size-report.json"
& $python build_support\size_report.py `
    --build-dir $buildDirectory `
    --archive $archivePath `
    --output $sizeReportPath
if ($LASTEXITCODE -ne 0) {
    throw "Groessenbericht konnte nicht erzeugt werden."
}

Write-Host "Build erstellt: $executable"
Write-Host "Portabler Datenordner: $buildDirectory\data"
Write-Host "Release-Paket: $archivePath"
Write-Host "SHA-256: $hash"
Write-Host "Groessenbericht: $sizeReportPath"
