import sys
import re
import subprocess
import tempfile
import webbrowser
from pathlib import Path
from dataclasses import dataclass, field

from services.temp_report_service import create_temp_report


@dataclass
class KositValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    report_html: str = ""


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()

JAVA_EXE = BASE_DIR / "external" / "java" / "bin" / "java.exe"

KOSIT_DIR = BASE_DIR / "external" / "kosit"


def _find_validator_jar() -> Path:
    validator_dir = KOSIT_DIR / "validator"
    candidates = list(validator_dir.glob("validator-*-standalone.jar"))
    if not candidates:
        return validator_dir / "validator-1.6.3-standalone.jar"

    def version_key(path: Path):
        match = re.search(r"validator-(\d+)\.(\d+)\.(\d+)-standalone", path.name)
        return tuple(map(int, match.groups())) if match else (0, 0, 0)

    return max(candidates, key=version_key)


KOSIT_JAR = _find_validator_jar()

XRECHNUNG_DIR = KOSIT_DIR / "xrechnung"
SCENARIOS_XML = XRECHNUNG_DIR / "scenarios.xml"


def show_html_report(report_html: str) -> None:
    if not report_html or not report_html.strip():
        raise ValueError("Kein Prüfbericht vorhanden.")

    report_path = create_temp_report(report_html)
    webbrowser.open(report_path.as_uri())


def _read_current_html_report(report_dir: Path) -> str:
    """
    Liest den KoSIT invoice-report.xml und extrahiert daraus
    den eingebetteten HTML-Prüfbericht.
    """
    if not report_dir.exists():
        return ""

    report_xml = report_dir / "invoice-report.xml"

    if not report_xml.exists():
        return ""

    try:
        from lxml import etree

        parser = etree.XMLParser(recover=True)
        doc = etree.parse(str(report_xml), parser)

        html_nodes = doc.xpath(
            "//*[local-name()='explanation']/*[local-name()='html']"
        )

        if not html_nodes:
            return report_xml.read_text(
                encoding="utf-8",
                errors="replace",
            )

        return etree.tostring(
            html_nodes[0],
            encoding="unicode",
            method="html",
        )

    except Exception:
        return report_xml.read_text(
            encoding="utf-8",
            errors="replace",
        )


def validate_with_kosit(
    xml_bytes: bytes,
    open_report: bool = False,
) -> KositValidationResult:

    if not JAVA_EXE.exists():
        return KositValidationResult(
            valid=False,
            errors=[
                f"Portable Java nicht gefunden:\n{JAVA_EXE}"
            ],
        )

    if not KOSIT_JAR.exists():
        return KositValidationResult(
            valid=False,
            errors=[
                f"KoSIT Validator nicht gefunden:\n{KOSIT_JAR}"
            ],
        )

    if not SCENARIOS_XML.exists():
        return KositValidationResult(
            valid=False,
            errors=[
                f"KoSIT scenarios.xml nicht gefunden:\n{SCENARIOS_XML}"
            ],
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        xml_path = tmp_dir / "invoice.xml"
        report_dir = tmp_dir / "reports"
        report_dir.mkdir()
        xml_path.write_bytes(xml_bytes)

        cmd = [
            str(JAVA_EXE),
            "--enable-native-access=ALL-UNNAMED",
            "-jar",
            str(KOSIT_JAR),
            "-s",
            str(SCENARIOS_XML),
            "-r",
            str(XRECHNUNG_DIR),
            "-o",
            str(report_dir),
            str(xml_path),
        ]

        try:
            proc = subprocess.run(
                cmd,
                input="",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(tmp_dir),
                timeout=60,
                # Rechnungshelfer ist eine GUI-Anwendung. Java darf bei jeder
                # Validierung nicht kurz ein Konsolenfenster einblenden; seine
                # Ausgaben werden trotzdem ueber stdout/stderr erfasst.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

        except subprocess.TimeoutExpired:
            return KositValidationResult(
                valid=False,
                errors=[
                    "KoSIT/XRechnung-Validierung wurde nach 60 Sekunden abgebrochen.",
                    "Bitte Java, KoSIT-Konfiguration oder XML prüfen.",
                ],
            )

        report_html = _read_current_html_report(report_dir)

        if open_report and report_html:
            try:
                show_html_report(report_html)
            except Exception:
                pass

        errors = []

        if proc.returncode != 0:
            errors.append(
                "KoSIT/XRechnung-Validierung fehlgeschlagen."
            )

            if proc.stderr.strip():
                errors.append(proc.stderr.strip())

            if proc.stdout.strip():
                errors.append(proc.stdout.strip())

        return KositValidationResult(
            valid=proc.returncode == 0,
            errors=errors,
            report_html=report_html,
        )
