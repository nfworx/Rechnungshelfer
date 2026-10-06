import argparse
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from packaging.version import Version

from build_support.component_docs import BEGIN, update_component_documentation
from build_support.kosit_builder import KositRelease, ReleaseAsset
from build_support.release_tool import Reporter, _run_tests, _verify_artifacts, run_command


class ReleaseToolTests(unittest.TestCase):
    def _project(self, root: Path) -> Path:
        (root / "external" / "java" / "bin").mkdir(parents=True)
        (root / "external" / "java" / "bin" / "java.exe").write_bytes(b"java")
        (root / "external" / "java" / "release").write_text(
            '\n'.join([
                'IMPLEMENTOR="Eclipse Adoptium"',
                'IMPLEMENTOR_VERSION="Temurin-21.0.12.1+1"',
                'JAVA_RUNTIME_VERSION="21.0.12.1+1-LTS"',
                'JAVA_VERSION="21.0.12.1"',
                'MODULES="java.base java.compiler java.desktop java.logging java.xml jdk.httpserver"',
                'OS_ARCH="x86_64"',
                'OS_NAME="Windows"',
                'JVM_VARIANT="Hotspot"',
                'IMAGE_TYPE="JRE"',
            ]) + '\n',
            encoding="utf-8",
        )
        (root / "external" / "kosit" / "validator").mkdir(parents=True)
        (root / "external" / "kosit" / "validator" / "validator-1.6.2-standalone.jar").write_bytes(b"old")
        (root / "external" / "components.json").write_text(json.dumps({
            "schema_version": 1,
            "components": {
                "java-runtime": "21.0.12.1",
                "kosit-validator": "1.6.2",
                "ubl-schemas": "2.1",
                "xrechnung-configuration": "2026.01.31",
            },
        }), encoding="utf-8")
        (root / "build.ps1").write_text("", encoding="utf-8")
        (root / "version.py").write_text(
            '"""Einzige Quelle fuer die Programmversion."""\n\n__version__ = "1.0.0"\n', encoding="utf-8"
        )
        (root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [Unreleased]\n\n## [1.0.1] - 2026-10-05\n\n- Patch\n\n"
            "## [1.0.0] - 2026-10-04\n\n- Erstes Release\n",
            encoding="utf-8",
        )
        (root / "readme.md").write_text("# Rechnungshelfer\n", encoding="utf-8")
        (root / "requirements.txt").write_text("packaging==26.2\n", encoding="utf-8")
        (root / "requirements-dev.txt").write_text("-r requirements.txt\n", encoding="utf-8")
        (root / "THIRD_PARTY_NOTICES.md").write_text("# Drittanbieter\n", encoding="utf-8")
        (root / "build_support").mkdir()
        (root / "build_support" / "kosit_trusted_releases.json").write_text(
            json.dumps({"schema_version": 1, "releases": {"1.6.3": "a" * 64}}),
            encoding="utf-8",
        )
        (root / "build_support" / "java_trusted_releases.json").write_text(
            json.dumps({
                "schema_version": 1,
                "releases": {
                    "21.0.12.1": {
                        "implementor": "Eclipse Adoptium",
                        "implementor_version": "Temurin-21.0.12.1+1",
                        "runtime_version": "21.0.12.1+1-LTS",
                        "image_type": "JRE",
                        "os_name": "Windows",
                        "os_arch": "x86_64",
                        "jvm": "hotspot",
                        "package": {
                            "filename": "runtime.zip",
                            "url": "https://github.com/adoptium/temurin21-binaries/releases/download/test/runtime.zip",
                            "size": 3,
                            "sha256": "b" * 64,
                        },
                    }
                },
            }),
            encoding="utf-8",
        )
        return root

    @staticmethod
    def _release(version="1.6.3") -> KositRelease:
        return KositRelease(
            Version(version),
            f"https://github.com/itplr-kosit/validator/releases/tag/v{version}",
            ReleaseAsset(
                f"validator-{version}-standalone.jar",
                f"https://github.com/itplr-kosit/validator/releases/download/v{version}/validator-{version}-standalone.jar",
                3,
                "a" * 64,
            ),
        )

    @staticmethod
    def _args(root: Path, command: str, **changes):
        values = {
            "project_root": root,
            "command": command,
            "with_tests": False,
            "yes": True,
            "version": "1.0.0",
            "channel": "test",
            "allow_dirty": True,
            "skip_git_check": True,
        }
        values.update(changes)
        return argparse.Namespace(**values)

    def test_documentation_block_is_generated_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            first = update_component_documentation(project)
            second = update_component_documentation(project)
            self.assertEqual(len(first), 2)
            self.assertEqual(second, [])
            self.assertEqual((project / "readme.md").read_text().count(BEGIN), 1)

    def test_reporter_writes_human_and_machine_readable_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            reporter = Reporter(Path(directory), "check")
            reporter.warning("TEST", "Eine Warnung")
            reporter.finish("success")
            self.assertIn("[WARNUNG] [TEST] Eine Warnung", reporter.log_path.read_text(encoding="utf-8"))
            report = json.loads(reporter.report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["details"]["command"], "check")

    def test_reporter_retries_short_windows_file_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            reporter = Reporter(Path(directory), "check")
            path_type = type(reporter.report_path)
            original_replace = path_type.replace
            attempts = 0

            def temporarily_locked(path, target):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError("simulierte kurze Windows-Dateisperre")
                return original_replace(path, target)

            with patch.object(path_type, "replace", new=temporarily_locked):
                reporter.warning("TEST", "Dateisperre wird wiederholt")
            reporter.finish("success")

            self.assertEqual(attempts, 3)
            self.assertFalse(list(reporter.log_dir.glob("release-report-*.tmp")))

    def test_test_runner_buffers_successful_simulation_output(self):
        with tempfile.TemporaryDirectory() as directory:
            reporter = Reporter(Path(directory), "check")
            invocation = {}

            def capture_process(step, command, cwd, **options):
                invocation.update(step=step, command=command, cwd=cwd, options=options)

            with patch.object(reporter, "run_process", new=capture_process):
                _run_tests(reporter, Path(directory))
            reporter.finish("success")

            self.assertEqual(invocation["step"], "TESTS")
            self.assertIn("-b", invocation["command"])
            self.assertTrue(invocation["options"]["quiet_success"])

    def test_successful_test_process_is_summarized_but_fully_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                reporter = Reporter(Path(directory), "check")
                reporter.run_process(
                    "TESTS",
                    [
                        sys.executable,
                        "-c",
                        (
                            "print('test_example (tests.Example) ... ok'); "
                            "print('Ran 82 tests in 1.234s'); print('OK')"
                        ),
                    ],
                    Path(directory),
                    quiet_success=True,
                )
                reporter.finish("success")

            console = output.getvalue()
            log = reporter.log_path.read_text(encoding="utf-8")
            self.assertNotIn("[AUSGABE] [TESTS] test_example", console)
            self.assertIn("82 Tests in 1.234s bestanden", console)
            self.assertIn("test_example", log)

    def test_check_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}

            def fake_process(reporter, step, _command, _cwd, **_options):
                reporter.ok(step, "Pruefung simuliert")

            with (
                patch("build_support.release_tool.fetch_latest_release", return_value=self._release()),
                patch.object(Reporter, "run_process", new=fake_process),
            ):
                result = run_command(self._args(project, "check"))

            self.assertEqual(result, 0)
            for path, content in before.items():
                self.assertEqual(path.read_bytes(), content)

    def test_component_update_does_not_change_program_version_or_changelog(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            original_version = (project / "version.py").read_bytes()
            original_changelog = (project / "CHANGELOG.md").read_bytes()

            def fake_install(_project, release, **_options):
                path = project / "external" / "components.json"
                data = json.loads(path.read_text())
                data["components"]["kosit-validator"] = str(release.version)
                path.write_text(json.dumps(data), encoding="utf-8")

            def fake_process(reporter, step, _command, _cwd, **_options):
                reporter.ok(step, "Tests simuliert")

            with (
                patch("build_support.release_tool.fetch_latest_release", return_value=self._release()),
                patch("build_support.release_tool.install_release", side_effect=fake_install),
                patch.object(Reporter, "run_process", new=fake_process),
            ):
                result = run_command(self._args(project, "update-components"))

            self.assertEqual(result, 0)
            self.assertEqual((project / "version.py").read_bytes(), original_version)
            self.assertEqual((project / "CHANGELOG.md").read_bytes(), original_changelog)
            self.assertIn("1.6.3", (project / "readme.md").read_text())

    def test_failed_component_tests_roll_back(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            original = (project / "external" / "components.json").read_bytes()

            def fake_install(_project, release, **_options):
                path = project / "external" / "components.json"
                data = json.loads(path.read_text())
                data["components"]["kosit-validator"] = str(release.version)
                path.write_text(json.dumps(data), encoding="utf-8")

            def fail_tests(_reporter, _step, _command, _cwd, **_options):
                raise OSError("Tests fehlgeschlagen")

            with (
                patch("build_support.release_tool.fetch_latest_release", return_value=self._release()),
                patch("build_support.release_tool.install_release", side_effect=fake_install),
                patch.object(Reporter, "run_process", new=fail_tests),
            ):
                result = run_command(self._args(project, "update-components"))

            self.assertEqual(result, 1)
            self.assertEqual((project / "external" / "components.json").read_bytes(), original)

    def test_prepare_syncs_version_without_editing_changelog_text(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            changelog = (project / "CHANGELOG.md").read_bytes()
            result = run_command(self._args(project, "prepare", version="1.0.1"))
            self.assertEqual(result, 0)
            self.assertIn('"1.0.1"', (project / "version.py").read_text())
            self.assertEqual((project / "CHANGELOG.md").read_bytes(), changelog)
            self.assertTrue((project / "build" / "release-notes-1.0.1.md").is_file())

    def test_build_does_not_edit_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            update_component_documentation(project)
            tracked = [project / "version.py", project / "CHANGELOG.md", project / "readme.md"]
            before = {path: path.read_bytes() for path in tracked}
            steps = []

            def fake_process(reporter, step, _command, _cwd, **_options):
                steps.append(step)
                reporter.ok(step, "Simuliert")

            with (
                patch.object(Reporter, "run_process", new=fake_process),
                patch("build_support.release_tool._verify_artifacts", return_value={"archive": "test.zip"}),
            ):
                result = run_command(self._args(project, "build"))

            self.assertEqual(result, 0)
            self.assertEqual(steps, ["SICHERHEIT", "TESTS", "BUILD"])
            for path, content in before.items():
                self.assertEqual(path.read_bytes(), content)

    def test_release_artifacts_are_verified_together(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            release_dir = project / "release"
            release_dir.mkdir()
            archive = release_dir / "Rechnungshelfer-1.0.1-win64.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("Rechnungshelfer.exe", b"app")
                package.writestr("_internal/Updater.exe", b"updater")
                package.writestr("_internal/runtime.dat", b"runtime")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            Path(str(archive) + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
            manifest = release_dir / "Rechnungshelfer-1.0.1-test-manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "kind": "application",
                "channel": "test",
                "version": "1.0.1",
                "package": {"url": archive.name, "size": archive.stat().st_size, "sha256": digest},
            }), encoding="utf-8")
            with patch("build_support.release_tool.platform.architecture", return_value=("64bit", "")):
                result = _verify_artifacts(project, Version("1.0.1"), "test")
            self.assertEqual(result["sha256"], digest)


if __name__ == "__main__":
    unittest.main()
