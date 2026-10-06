import json
import tempfile
import unittest
from pathlib import Path

from build_support.size_report import create_size_report, path_size, render_table, write_size_report


class SizeReportTests(unittest.TestCase):
    @staticmethod
    def _build(root: Path) -> Path:
        build = root / "dist" / "Rechnungshelfer"
        (build / "_internal" / "external" / "java" / "bin").mkdir(parents=True)
        (build / "_internal" / "external" / "kosit" / "xrechnung" / "resources" / "ubl").mkdir(
            parents=True
        )
        (build / "_internal" / "babel" / "locale-data").mkdir(parents=True)
        (build / "Rechnungshelfer.exe").write_bytes(b"a" * 11)
        (build / "_internal" / "python.dll").write_bytes(b"p" * 13)
        (build / "_internal" / "external" / "java" / "bin" / "java.exe").write_bytes(b"j" * 17)
        (build / "_internal" / "external" / "kosit" / "validator").mkdir()
        (build / "_internal" / "external" / "kosit" / "validator" / "validator.jar").write_bytes(b"k" * 19)
        (build / "_internal" / "external" / "kosit" / "xrechnung" / "resources" / "ubl" / "ubl.xsd").write_bytes(
            b"u" * 23
        )
        (build / "_internal" / "babel" / "locale-data" / "de.dat").write_bytes(b"b" * 7)
        return build

    def test_report_separates_external_runtimes_without_double_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = self._build(root)
            archive = root / "release.zip"
            archive.write_bytes(b"z" * 29)

            report = create_size_report(build, archive=archive)
            measurements = report["measurements"]

            self.assertEqual(measurements["release_build"]["bytes"], sum((11, 13, 17, 19, 23, 7)))
            self.assertEqual(measurements["java_runtime"]["bytes"], 17)
            self.assertEqual(measurements["kosit_bundle"]["bytes"], 42)
            self.assertEqual(measurements["kosit_validator"]["bytes"], 19)
            self.assertEqual(measurements["xrechnung_configuration"]["bytes"], 23)
            self.assertEqual(measurements["ubl_schemas"]["bytes"], 23)
            self.assertEqual(measurements["python_application"]["bytes"], 31)
            self.assertEqual(measurements["release_archive"]["bytes"], 29)
            self.assertEqual(path_size(build)[1], 6)

    def test_baseline_delta_and_json_output_are_reusable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = self._build(root)
            baseline = root / "baseline.json"
            baseline.write_text(json.dumps({
                "measurements": {"release_build": {"bytes": 80}},
            }), encoding="utf-8")

            report = create_size_report(build, baseline=baseline)
            output = root / "report.json"
            write_size_report(report, output)

            self.assertEqual(report["deltas"]["release_build"]["bytes"], 10)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["schema_version"], 1)
            self.assertIn("Veraenderung zur Ausgangsbasis", render_table(report))


if __name__ == "__main__":
    unittest.main()
