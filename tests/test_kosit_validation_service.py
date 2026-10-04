import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from rechnungshelfer.services.kosit_validation_service import (
    KositValidator,
    validate_with_kosit,
)


class KositValidationProcessTests(unittest.TestCase):
    def test_java_process_is_started_without_console_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            java = root / "java.exe"
            jar = root / "validator.jar"
            scenarios = root / "scenarios.xml"
            xrechnung = root / "xrechnung"
            java.write_bytes(b"java")
            jar.write_bytes(b"jar")
            scenarios.write_text("<scenarios/>", encoding="utf-8")
            xrechnung.mkdir()

            completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
            with (
                patch("rechnungshelfer.services.kosit_validation_service.JAVA_EXE", java),
                patch("rechnungshelfer.services.kosit_validation_service.KOSIT_JAR", jar),
                patch("rechnungshelfer.services.kosit_validation_service.SCENARIOS_XML", scenarios),
                patch("rechnungshelfer.services.kosit_validation_service.XRECHNUNG_DIR", xrechnung),
                patch("rechnungshelfer.services.kosit_validation_service.subprocess.run", return_value=completed) as run,
            ):
                result = validate_with_kosit(b"<Invoice/>")

            self.assertTrue(result.valid)
            self.assertEqual(
                run.call_args.kwargs["creationflags"],
                getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.assertEqual(run.call_args.kwargs["input"], "")
            self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_injected_adapter_reports_timeout_without_starting_ui(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            java = root / "java.exe"
            jar = root / "validator.jar"
            scenarios = root / "scenarios.xml"
            xrechnung = root / "xrechnung"
            java.write_bytes(b"java")
            jar.write_bytes(b"jar")
            scenarios.write_text("<scenarios/>", encoding="utf-8")
            xrechnung.mkdir()
            runner = MagicMock(
                side_effect=subprocess.TimeoutExpired("java", 3)
            )
            validator = KositValidator(
                java_exe=java,
                validator_jar=jar,
                scenarios_xml=scenarios,
                xrechnung_dir=xrechnung,
                process_runner=runner,
                timeout_seconds=3,
            )

            result = validator.validate(b"<Invoice/>")

        self.assertFalse(result.valid)
        self.assertIn("3 Sekunden", result.errors[0])
        runner.assert_called_once()

    def test_missing_resource_is_reported_before_process_start(self):
        runner = MagicMock()
        validator = KositValidator(
            java_exe=Path("missing-java.exe"),
            validator_jar=Path("missing-validator.jar"),
            scenarios_xml=Path("missing-scenarios.xml"),
            xrechnung_dir=Path("missing-xrechnung"),
            process_runner=runner,
        )

        result = validator.validate(b"<Invoice/>")

        self.assertFalse(result.valid)
        self.assertIn("Portable Java", result.errors[0])
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
