import sys
import re
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from collections.abc import Callable


@dataclass
class KositValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    report_html: str = ""


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


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


class KositValidator:
    """Adapter für den externen KoSIT-Java-Prozess."""

    def __init__(
        self,
        *,
        java_exe: Path | None = None,
        validator_jar: Path | None = None,
        scenarios_xml: Path | None = None,
        xrechnung_dir: Path | None = None,
        process_runner: Callable | None = None,
        timeout_seconds: int = 60,
    ):
        self.java_exe = Path(java_exe) if java_exe is not None else JAVA_EXE
        self.validator_jar = (
            Path(validator_jar) if validator_jar is not None else KOSIT_JAR
        )
        self.scenarios_xml = (
            Path(scenarios_xml) if scenarios_xml is not None else SCENARIOS_XML
        )
        self.xrechnung_dir = (
            Path(xrechnung_dir) if xrechnung_dir is not None else XRECHNUNG_DIR
        )
        self._process_runner = process_runner
        self.timeout_seconds = timeout_seconds

    def validate(self, xml_bytes: bytes) -> KositValidationResult:
        missing = (
            (self.java_exe, "Portable Java"),
            (self.validator_jar, "KoSIT Validator"),
            (self.scenarios_xml, "KoSIT scenarios.xml"),
            (self.xrechnung_dir, "KoSIT XRechnung-Konfiguration"),
        )
        for path, label in missing:
            if not path.exists():
                return KositValidationResult(
                    valid=False,
                    errors=[f"{label} nicht gefunden:\n{path}"],
                )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            xml_path = tmp_dir / "invoice.xml"
            report_dir = tmp_dir / "reports"
            report_dir.mkdir()
            xml_path.write_bytes(xml_bytes)

            command = [
                str(self.java_exe),
                "--enable-native-access=ALL-UNNAMED",
                "-jar",
                str(self.validator_jar),
                "-s",
                str(self.scenarios_xml),
                "-r",
                str(self.xrechnung_dir),
                "-o",
                str(report_dir),
                str(xml_path),
            ]
            runner = self._process_runner or subprocess.run

            try:
                process = runner(
                    command,
                    input="",
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(tmp_dir),
                    timeout=self.timeout_seconds,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except subprocess.TimeoutExpired:
                return KositValidationResult(
                    valid=False,
                    errors=[
                        "KoSIT/XRechnung-Validierung wurde nach "
                        f"{self.timeout_seconds} Sekunden abgebrochen.",
                        "Bitte Java, KoSIT-Konfiguration oder XML prüfen.",
                    ],
                )

            report_html = _read_current_html_report(report_dir)
            errors = []
            if process.returncode != 0:
                errors.append("KoSIT/XRechnung-Validierung fehlgeschlagen.")
                if process.stderr.strip():
                    errors.append(process.stderr.strip())
                if process.stdout.strip():
                    errors.append(process.stdout.strip())

            return KositValidationResult(
                valid=process.returncode == 0,
                errors=errors,
                report_html=report_html,
            )


def validate_with_kosit(xml_bytes: bytes) -> KositValidationResult:
    """Kompatible Funktionsfassade für bestehende Aufrufstellen."""
    return KositValidator().validate(xml_bytes)
