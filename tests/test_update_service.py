import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from packaging.version import Version

from app_info import APP_VERSION
from rechnungshelfer.services.update_service import (
    _materialize_online_manifest,
    _updater_command,
    check_for_application_update,
)
from updater.core import ApplicationManifest, UpdateError, load_manifest


class UpdateServiceTests(unittest.TestCase):
    @staticmethod
    def _newer_version() -> str:
        current = Version(APP_VERSION)
        return f"{current.major}.{current.minor}.{current.micro + 1}"

    def _release_payloads(self, *, version=None, package_digest="a" * 64):
        version = version or self._newer_version()
        package_name = f"Rechnungshelfer-{version}-win64.zip"
        manifest_name = f"Rechnungshelfer-{version}-stable-manifest.json"
        manifest = {
            "schema_version": 1,
            "kind": "application",
            "channel": "stable",
            "version": version,
            "package": {"url": package_name, "size": 123456, "sha256": "a" * 64},
            "release_notes_url": "",
            "mandatory": False,
        }
        manifest_payload = (json.dumps(manifest) + "\n").encode("utf-8")
        prefix = f"https://github.com/nfworx/Rechnungshelfer/releases/download/v{version}/"
        release = {
            "tag_name": f"v{version}",
            "draft": False,
            "prerelease": False,
            "html_url": f"https://github.com/nfworx/Rechnungshelfer/releases/tag/v{version}",
            "assets": [
                {
                    "name": manifest_name,
                    "browser_download_url": prefix + manifest_name,
                    "size": len(manifest_payload),
                    "digest": "sha256:" + hashlib.sha256(manifest_payload).hexdigest(),
                },
                {
                    "name": package_name,
                    "browser_download_url": prefix + package_name,
                    "size": 123456,
                    "digest": "sha256:" + package_digest,
                },
            ],
        }
        return json.dumps(release).encode("utf-8"), manifest_payload

    def test_current_release_returns_no_update_without_loading_assets(self):
        release = {
            "tag_name": f"v{APP_VERSION}",
            "draft": False,
            "prerelease": False,
            "assets": [],
        }
        with patch("rechnungshelfer.services.update_service._request_bytes", return_value=json.dumps(release).encode()) as request:
            self.assertIsNone(check_for_application_update())
        request.assert_called_once()

    def test_new_release_is_verified_against_manifest_and_github_assets(self):
        expected_version = self._newer_version()
        metadata, manifest = self._release_payloads()
        with patch("rechnungshelfer.services.update_service._request_bytes", side_effect=[metadata, manifest]):
            update = check_for_application_update()
        self.assertIsNotNone(update)
        self.assertEqual(update.summary.manifest.version, Version(expected_version))
        self.assertTrue(
            update.package_url.endswith(f"Rechnungshelfer-{expected_version}-win64.zip")
        )

    def test_package_digest_mismatch_is_rejected(self):
        metadata, manifest = self._release_payloads(package_digest="b" * 64)
        with (
            patch("rechnungshelfer.services.update_service._request_bytes", side_effect=[metadata, manifest]),
            self.assertRaisesRegex(UpdateError, "Programm-ZIP stimmt nicht"),
        ):
            check_for_application_update()

    def test_online_manifest_is_pinned_locally_with_absolute_package_url(self):
        metadata, manifest = self._release_payloads()
        with patch("rechnungshelfer.services.update_service._request_bytes", side_effect=[metadata, manifest]):
            update = check_for_application_update()
        with tempfile.TemporaryDirectory() as directory:
            with patch("rechnungshelfer.services.update_service.tempfile.gettempdir", return_value=directory):
                path = _materialize_online_manifest(update)
            pinned = load_manifest(path)
        self.assertIsInstance(pinned, ApplicationManifest)
        self.assertEqual(pinned.package.url, update.package_url)

    def test_packaged_application_copies_internal_updater_to_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_root = root / "Rechnungshelfer"
            updater = install_root / "_internal" / "Updater.exe"
            updater.parent.mkdir(parents=True)
            updater.write_bytes(b"internal updater")
            temp_root = root / "temp"
            temp_root.mkdir()

            with (
                patch("rechnungshelfer.services.update_service.sys.frozen", True, create=True),
                patch("rechnungshelfer.services.update_service.application_install_root", return_value=install_root),
                patch("rechnungshelfer.services.update_service.tempfile.gettempdir", return_value=str(temp_root)),
            ):
                command, updater_temp = _updater_command()

            self.assertEqual(Path(command[0]), temp_root / "Rechnungshelfer-Updater" / "Updater.exe")
            self.assertEqual(Path(command[0]).read_bytes(), b"internal updater")
            self.assertEqual(updater_temp, temp_root / "Rechnungshelfer-Updater")


if __name__ == "__main__":
    unittest.main()
