import hashlib
import json
import re
import unittest
from pathlib import Path

from packaging.version import Version
from lxml import etree

from app_info import APP_EXECUTABLE_NAME, APP_ID, APP_NAME, APP_VERSION
from build_support.generate_windows_version_info import (
    OUTPUT_PATH,
    _windows_version_tuple,
    generate,
)
from rechnungshelfer.services.validation_service import XSD_PATH
from version import __version__


class VersioningTests(unittest.TestCase):
    def test_version_has_one_canonical_source_and_is_semantic(self):
        parsed = Version(__version__)
        self.assertEqual(APP_VERSION, __version__)
        self.assertEqual(len(parsed.release), 3)
        self.assertFalse(parsed.is_devrelease)

    def test_technical_identifiers_are_windows_safe(self):
        self.assertEqual(APP_NAME, "Rechnungshelfer")
        self.assertEqual(APP_ID, "Rechnungshelfer")
        self.assertEqual(APP_EXECUTABLE_NAME, APP_ID)
        self.assertRegex(APP_ID, r"^[A-Za-z][A-Za-z0-9._-]*$")

    def test_windows_version_resource_is_generated_from_metadata(self):
        path = generate()
        content = path.read_text(encoding="utf-8")
        self.assertEqual(path, OUTPUT_PATH)
        self.assertIn(f"StringStruct('ProductName', {APP_NAME!r})", content)
        self.assertIn(f"StringStruct('ProductVersion', {APP_VERSION!r})", content)
        expected = _windows_version_tuple(APP_VERSION)
        self.assertIn(f"filevers={expected}", content)
        self.assertEqual(len(expected), 4)

    def test_example_update_manifest_is_structurally_valid(self):
        manifest_path = (
            Path(__file__).resolve().parent.parent
            / "updater"
            / "update-manifest.example.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["kind"], "application")
        Version(manifest["version"])
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", manifest["package"]["sha256"]))

    def test_onefolder_build_includes_component_registry(self):
        project_root = Path(__file__).resolve().parent.parent
        registry = project_root / "external" / "components.json"
        spec = (project_root / "Rechnungshelfer.spec").read_text(encoding="utf-8")
        data = json.loads(registry.read_text(encoding="utf-8"))

        self.assertIn('project_root / "external" / "components.json"', spec)
        self.assertEqual(data["schema_version"], 1)
        kosit_version = data["components"]["kosit-validator"]
        self.assertEqual(str(Version(kosit_version)), kosit_version)

    def test_local_xsd_uses_ubl_from_xrechnung_configuration(self):
        project_root = Path(__file__).resolve().parent.parent
        expected = (
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
        registry = json.loads(
            (project_root / "external" / "components.json").read_text(encoding="utf-8")
        )
        spec = (project_root / "Rechnungshelfer.spec").read_text(encoding="utf-8")

        self.assertEqual(XSD_PATH, expected)
        self.assertEqual(etree.parse(str(expected)).getroot().get("version"), "2.1")
        self.assertNotIn("ubl-schemas", registry["components"])
        self.assertNotIn('project_root / "external" / "ubl"', spec)
        self.assertFalse((project_root / "external" / "ubl").exists())

    def test_bundled_kosit_matches_locally_approved_digest(self):
        project_root = Path(__file__).resolve().parent.parent
        registry = json.loads(
            (project_root / "external" / "components.json").read_text(encoding="utf-8")
        )
        trusted = json.loads(
            (project_root / "build_support" / "kosit_trusted_releases.json").read_text(
                encoding="utf-8"
            )
        )
        version = registry["components"]["kosit-validator"]
        jar = project_root / "external" / "kosit" / "validator" / f"validator-{version}-standalone.jar"

        self.assertTrue(jar.is_file())
        self.assertEqual(hashlib.sha256(jar.read_bytes()).hexdigest(), trusted["releases"][version])

    def test_onefolder_build_hides_updater_below_internal(self):
        project_root = Path(__file__).resolve().parent.parent
        build_script = (project_root / "build.ps1").read_text(encoding="utf-8")
        update_service = (
            project_root / "rechnungshelfer" / "services" / "update_service.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"_internal\\Updater.exe"', build_script)
        self.assertIn('/ "_internal" / "Updater.exe"', update_service)

    def test_user_builds_explicitly_exclude_maintainer_tools(self):
        project_root = Path(__file__).resolve().parent.parent
        for name in ("Rechnungshelfer.spec", "Updater.spec"):
            spec = (project_root / name).read_text(encoding="utf-8")
            self.assertIn('"build_support"', spec)
            self.assertIn('"tests"', spec)
            self.assertIn('"updater.external_components_update"', spec)

    def test_babel_build_is_limited_to_the_explicit_german_locale(self):
        project_root = Path(__file__).resolve().parent.parent
        date_fields = (project_root / "rechnungshelfer" / "gui" / "date_fields.py").read_text(
            encoding="utf-8"
        )
        spec = (project_root / "Rechnungshelfer.spec").read_text(encoding="utf-8")
        hook = (
            project_root / "build_support" / "pyinstaller_hooks" / "hook-babel.py"
        ).read_text(encoding="utf-8")

        self.assertIn('locale="de_DE"', date_fields)
        self.assertIn('"build_support" / "pyinstaller_hooks"', spec)
        self.assertIn('(\"root.dat\", \"de.dat\", \"de_DE.dat\")', hook)
        self.assertNotIn("collect_data_files", hook)


if __name__ == "__main__":
    unittest.main()
