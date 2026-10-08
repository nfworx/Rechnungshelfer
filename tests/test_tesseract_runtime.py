import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_support.tesseract_runtime import (
    TesseractRuntimeError,
    runtime_digest,
    runtime_files,
    validate_installed_runtime,
)


class TesseractRuntimeTests(unittest.TestCase):
    def _runtime(self, root: Path):
        runtime = root / "external" / "tesseract"
        (runtime / "tessdata" / "configs").mkdir(parents=True)
        (runtime / "tesseract.exe").write_bytes(b"exe")
        (runtime / "runtime.dll").write_bytes(b"dll")
        (runtime / "training.exe").write_bytes(b"not shipped")
        (runtime / "manual.html").write_text("not shipped", encoding="utf-8")
        (runtime / "tessdata" / "deu.traineddata").write_bytes(b"deu")
        (runtime / "tessdata" / "eng.traineddata").write_bytes(b"eng")
        (runtime / "tessdata" / "configs" / "tsv").write_text("tsv", encoding="utf-8")
        return runtime

    def _metadata(self, root: Path, digest: str):
        path = root / "trusted.json"
        path.write_text(
            json.dumps(
                {
                    "releases": [
                        {
                            "version": "5.5.3.20260724",
                            "release_tag": "5.5.3",
                            "installer_filename": "tesseract-installer.exe",
                            "installer_sha256": "a" * 64,
                            "runtime_sha256": digest,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_runtime_selection_excludes_training_tools_and_manuals(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._runtime(Path(tmp))

            selected = {path.name for path in runtime_files(runtime)}

        self.assertIn("tesseract.exe", selected)
        self.assertIn("runtime.dll", selected)
        self.assertIn("deu.traineddata", selected)
        self.assertIn("tsv", selected)
        self.assertNotIn("training.exe", selected)
        self.assertNotIn("manual.html", selected)

    def test_validation_checks_version_languages_and_aggregate_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self._runtime(root)
            metadata = self._metadata(root, runtime_digest(runtime))
            results = [
                subprocess.CompletedProcess([], 0, b"tesseract v5.5.3.20260724\n", b""),
                subprocess.CompletedProcess([], 0, b"List of available languages (2):\ndeu\neng\n", b""),
            ]

            with patch("build_support.tesseract_runtime.subprocess.run", side_effect=results):
                info = validate_installed_runtime(root, trusted_releases=metadata)

        self.assertEqual(info.version, "5.5.3.20260724")
        self.assertEqual(info.release_tag, "5.5.3")
        self.assertEqual(info.languages, ("deu", "eng"))

    def test_tampered_runtime_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = self._runtime(root)
            metadata = self._metadata(root, runtime_digest(runtime))
            (runtime / "runtime.dll").write_bytes(b"changed")
            results = [
                subprocess.CompletedProcess([], 0, b"tesseract v5.5.3.20260724\n", b""),
                subprocess.CompletedProcess([], 0, b"List of available languages (1):\ndeu\n", b""),
            ]

            with (
                patch("build_support.tesseract_runtime.subprocess.run", side_effect=results),
                self.assertRaisesRegex(TesseractRuntimeError, "weicht"),
            ):
                validate_installed_runtime(root, trusted_releases=metadata)


if __name__ == "__main__":
    unittest.main()
