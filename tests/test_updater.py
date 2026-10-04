import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from updater.core import (
    ApplicationManifest,
    ComponentsManifest,
    UpdateError,
    apply_application_update,
    apply_component_updates,
    load_manifest,
)
from updater.readiness import READY_ARGUMENT, READY_PREFIX, ready_file_from_argv, signal_ready
from updater.runner import run as run_updater
from build_support.create_update_manifest import create_component_package


class UpdaterTests(unittest.TestCase):
    def _zip(self, path: Path, files: dict[str, bytes | str]) -> tuple[int, str]:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                if isinstance(content, str):
                    content = content.encode("utf-8")
                archive.writestr(name, content)
        payload = path.read_bytes()
        return len(payload), hashlib.sha256(payload).hexdigest()

    def _manifest(self, path: Path, data: dict) -> Path:
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _component_manifest(self, root: Path, package: Path, version="1.6.3") -> Path:
        size = package.stat().st_size
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        return self._manifest(
            root / "components-manifest.json",
            {
                "schema_version": 1,
                "kind": "components",
                "channel": "test",
                "components": [
                    {
                        "id": "kosit-validator",
                        "version": version,
                        "package": {
                            "url": package.name,
                            "size": size,
                            "sha256": digest,
                        },
                    }
                ],
            },
        )

    def _app_manifest(self, root: Path, package: Path, version="1.0.1") -> Path:
        size = package.stat().st_size
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        return self._manifest(
            root / "application-manifest.json",
            {
                "schema_version": 1,
                "kind": "application",
                "channel": "test",
                "version": version,
                "package": {
                    "url": package.name,
                    "size": size,
                    "sha256": digest,
                },
            },
        )

    def test_component_update_replaces_only_managed_component(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            validator_dir = install / "external" / "kosit" / "validator"
            validator_dir.mkdir(parents=True)
            (validator_dir / "validator-1.6.2-standalone.jar").write_bytes(b"old")
            data = install / "data"
            data.mkdir()
            (data / "invoices.db").write_bytes(b"customer data")
            components = install / "external" / "components.json"
            components.write_text(
                json.dumps({"schema_version": 1, "components": {"kosit-validator": "1.6.2"}}),
                encoding="utf-8",
            )

            package = root / "kosit-1.6.3.zip"
            self._zip(
                package,
                {"external/kosit/validator/validator-1.6.3-standalone.jar": b"new"},
            )
            manifest_path = self._component_manifest(root, package)
            manifest = load_manifest(manifest_path)

            self.assertIsInstance(manifest, ComponentsManifest)
            versions = apply_component_updates(manifest, manifest_path, install)

            self.assertEqual(versions["kosit-validator"], "1.6.3")
            self.assertFalse((validator_dir / "validator-1.6.2-standalone.jar").exists())
            self.assertEqual(
                (validator_dir / "validator-1.6.3-standalone.jar").read_bytes(),
                b"new",
            )
            self.assertEqual((data / "invoices.db").read_bytes(), b"customer data")

    def test_local_manifest_string_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "component.zip"
            self._zip(package, {"external/kosit/validator/test.jar": b"test"})
            manifest_path = self._component_manifest(root, package)
            manifest = load_manifest(str(manifest_path))
            self.assertIsInstance(manifest, ComponentsManifest)

    def test_component_validation_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            validator_dir = install / "external" / "kosit" / "validator"
            validator_dir.mkdir(parents=True)
            old_jar = validator_dir / "validator-1.6.2-standalone.jar"
            old_jar.write_bytes(b"old")
            state = install / "external" / "components.json"
            state.write_text(
                json.dumps({"schema_version": 1, "components": {"kosit-validator": "1.6.2"}}),
                encoding="utf-8",
            )
            package = root / "kosit.zip"
            self._zip(package, {"external/kosit/validator/new.jar": b"broken"})
            manifest_path = self._component_manifest(root, package)
            manifest = load_manifest(manifest_path)

            def reject(component, install_root):
                raise UpdateError("smoke test failed")

            with self.assertRaisesRegex(UpdateError, "smoke test failed"):
                apply_component_updates(
                    manifest,
                    manifest_path,
                    install,
                    validator=reject,
                )

            self.assertEqual(old_jar.read_bytes(), b"old")
            self.assertFalse((validator_dir / "new.jar").exists())
            self.assertEqual(json.loads(state.read_text())["components"]["kosit-validator"], "1.6.2")

    def test_bad_checksum_does_not_touch_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            validator_dir = install / "external" / "kosit" / "validator"
            validator_dir.mkdir(parents=True)
            old_jar = validator_dir / "old.jar"
            old_jar.write_bytes(b"old")
            (install / "external" / "components.json").write_text(
                json.dumps({"schema_version": 1, "components": {"kosit-validator": "1.6.2"}}),
                encoding="utf-8",
            )
            package = root / "kosit.zip"
            self._zip(package, {"external/kosit/validator/new.jar": b"new"})
            manifest_path = self._component_manifest(root, package)
            content = json.loads(manifest_path.read_text())
            content["components"][0]["package"]["sha256"] = "0" * 64
            self._manifest(manifest_path, content)

            with self.assertRaisesRegex(UpdateError, "SHA-256"):
                apply_component_updates(load_manifest(manifest_path), manifest_path, install)
            self.assertEqual(old_jar.read_bytes(), b"old")

    def test_component_package_cannot_write_other_external_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            validator_dir = install / "external" / "kosit" / "validator"
            validator_dir.mkdir(parents=True)
            (validator_dir / "old.jar").write_bytes(b"old")
            (install / "external" / "components.json").write_text(
                json.dumps({"schema_version": 1, "components": {"kosit-validator": "1.6.2"}}),
                encoding="utf-8",
            )
            package = root / "bad-component.zip"
            self._zip(
                package,
                {
                    "external/kosit/validator/new.jar": b"new",
                    "external/java/bin/java.exe": b"unexpected",
                },
            )
            manifest_path = self._component_manifest(root, package)

            with self.assertRaisesRegex(UpdateError, "nicht freigegebene Dateien"):
                apply_component_updates(load_manifest(manifest_path), manifest_path, install)
            self.assertEqual((validator_dir / "old.jar").read_bytes(), b"old")
            self.assertFalse((install / "external" / "java").exists())

    def test_application_update_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            (install / "_internal").mkdir(parents=True)
            (install / "_internal" / "old.txt").write_text("old")
            (install / "Rechnungshelfer.exe").write_bytes(b"old exe")
            (install / "data").mkdir()
            (install / "data" / "invoices.db").write_bytes(b"customer data")
            package = root / "app.zip"
            self._zip(
                package,
                {
                    "Rechnungshelfer.exe": b"new exe",
                    "_internal/new.txt": "new",
                    "_internal/Updater.exe": b"new updater",
                },
            )
            manifest_path = self._app_manifest(root, package)
            manifest = load_manifest(manifest_path)

            self.assertIsInstance(manifest, ApplicationManifest)
            apply_application_update(
                manifest,
                manifest_path,
                install,
                current_version="1.0.0",
            )

            self.assertEqual((install / "Rechnungshelfer.exe").read_bytes(), b"new exe")
            self.assertTrue((install / "_internal" / "new.txt").exists())
            self.assertEqual((install / "_internal" / "Updater.exe").read_bytes(), b"new updater")
            self.assertFalse((install / "_internal" / "old.txt").exists())
            self.assertEqual((install / "data" / "invoices.db").read_bytes(), b"customer data")

    def test_application_package_with_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            (install / "_internal").mkdir(parents=True)
            (install / "Rechnungshelfer.exe").write_bytes(b"old")
            package = root / "app.zip"
            self._zip(
                package,
                {
                    "Rechnungshelfer.exe": b"new",
                    "_internal/new.txt": b"new",
                    "data/invoices.db": b"must not ship",
                },
            )
            manifest_path = self._app_manifest(root, package)

            with self.assertRaisesRegex(UpdateError, "data-Ordner"):
                apply_application_update(
                    load_manifest(manifest_path),
                    manifest_path,
                    install,
                    current_version="1.0.0",
                )
            self.assertEqual((install / "Rechnungshelfer.exe").read_bytes(), b"old")

    def test_application_validation_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            (install / "_internal").mkdir(parents=True)
            (install / "_internal" / "old.txt").write_text("old")
            (install / "Rechnungshelfer.exe").write_bytes(b"old")
            package = root / "app.zip"
            self._zip(
                package,
                {"Rechnungshelfer.exe": b"new", "_internal/new.txt": b"new"},
            )
            manifest_path = self._app_manifest(root, package)

            with self.assertRaisesRegex(UpdateError, "startup failed"):
                apply_application_update(
                    load_manifest(manifest_path),
                    manifest_path,
                    install,
                    current_version="1.0.0",
                    validator=lambda _: (_ for _ in ()).throw(UpdateError("startup failed")),
                )
            self.assertEqual((install / "Rechnungshelfer.exe").read_bytes(), b"old")
            self.assertTrue((install / "_internal" / "old.txt").exists())
            self.assertFalse((install / "_internal" / "new.txt").exists())

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            (install / "external" / "kosit" / "validator").mkdir(parents=True)
            (install / "external" / "components.json").write_text(
                json.dumps({"schema_version": 1, "components": {"kosit-validator": "1.6.2"}}),
                encoding="utf-8",
            )
            package = root / "bad.zip"
            self._zip(package, {"../outside.txt": b"bad"})
            manifest_path = self._component_manifest(root, package)

            with self.assertRaisesRegex(UpdateError, "Unsicherer Archivpfad"):
                apply_component_updates(load_manifest(manifest_path), manifest_path, install)
            self.assertFalse((root / "outside.txt").exists())

    def test_readiness_file_is_restricted_to_temp_directory(self):
        safe = Path(tempfile.gettempdir()) / f"{READY_PREFIX}unit-test.txt"
        safe.unlink(missing_ok=True)
        self.assertEqual(ready_file_from_argv([READY_ARGUMENT, str(safe)]), safe.resolve())
        self.assertTrue(signal_ready([READY_ARGUMENT, str(safe)]))
        self.assertEqual(safe.read_text(encoding="ascii"), "ready\n")
        safe.unlink()
        unsafe = Path(tempfile.gettempdir()).parent / f"{READY_PREFIX}unsafe.txt"
        self.assertIsNone(ready_file_from_argv([READY_ARGUMENT, str(unsafe)]))

    def test_component_package_generator_creates_loadable_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "validator"
            source.mkdir()
            (source / "validator-1.6.3-standalone.jar").write_bytes(b"jar")
            package, manifest_path = create_component_package(
                "kosit-validator",
                "1.6.3",
                source,
                root / "release",
                "test",
            )
            manifest = load_manifest(manifest_path)
            self.assertIsInstance(manifest, ComponentsManifest)
            self.assertTrue(package.is_file())
            with zipfile.ZipFile(package) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["external/kosit/validator/validator-1.6.3-standalone.jar"],
                )

    def test_runner_commits_application_after_start_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            (install / "_internal").mkdir(parents=True)
            (install / "_internal" / "old.txt").write_text("old")
            (install / "Rechnungshelfer.exe").write_bytes(b"old")
            (install / "data").mkdir()
            (install / "data" / "invoices.db").write_bytes(b"data")
            package = root / "app.zip"
            self._zip(
                package,
                {"Rechnungshelfer.exe": b"new", "_internal/new.txt": b"new"},
            )
            manifest = self._app_manifest(root, package)
            signal_code = (
                "import pathlib,sys; "
                "p=pathlib.Path(sys.argv[sys.argv.index('--update-ready-file')+1]); "
                "p.write_text('ready', encoding='ascii')"
            )

            result = run_updater(
                [
                    "--manifest", str(manifest),
                    "--install-root", str(install),
                    "--current-version", "1.0.0",
                    "--restart-command-json", json.dumps([sys.executable, "-c", signal_code]),
                    "--ready-timeout", "5",
                ]
            )

            self.assertEqual(result, 0)
            self.assertEqual((install / "Rechnungshelfer.exe").read_bytes(), b"new")
            self.assertTrue((install / "_internal" / "new.txt").exists())
            self.assertEqual((install / "data" / "invoices.db").read_bytes(), b"data")

    def test_runner_rolls_back_when_new_application_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            (install / "_internal").mkdir(parents=True)
            (install / "_internal" / "old.txt").write_text("old")
            (install / "Rechnungshelfer.exe").write_bytes(b"old")
            package = root / "app.zip"
            self._zip(
                package,
                {"Rechnungshelfer.exe": b"new", "_internal/new.txt": b"new"},
            )
            manifest = self._app_manifest(root, package)

            with self.assertRaisesRegex(UpdateError, "Startbestaetigung"):
                run_updater(
                    [
                        "--manifest", str(manifest),
                        "--install-root", str(install),
                        "--current-version", "1.0.0",
                        "--restart-command-json", json.dumps([sys.executable, "-c", "pass"]),
                        "--ready-timeout", "5",
                    ]
                )

            self.assertEqual((install / "Rechnungshelfer.exe").read_bytes(), b"old")
            self.assertTrue((install / "_internal" / "old.txt").exists())
            self.assertFalse((install / "_internal" / "new.txt").exists())

    def test_user_updater_rejects_component_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "Rechnungshelfer"
            install.mkdir()
            package = root / "component.zip"
            self._zip(package, {"external/kosit/validator/test.jar": b"jar"})
            manifest = self._component_manifest(root, package)

            with self.assertRaisesRegex(UpdateError, "nur Rechnungshelfer-Programmupdates"):
                run_updater([
                    "--manifest", str(manifest),
                    "--install-root", str(install),
                    "--no-restart",
                ])


if __name__ == "__main__":
    unittest.main()
