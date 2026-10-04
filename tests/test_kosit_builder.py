import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from packaging.version import Version

from build_support.kosit_builder import (
    KositBuilderError,
    KositRelease,
    ReleaseAsset,
    _download_verified,
    _parse_release,
    check_and_update,
)


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        if size < 0:
            size = len(self.payload) - self.position
        chunk = self.payload[self.position:self.position + size]
        self.position += len(chunk)
        return chunk


class KositBuilderTests(unittest.TestCase):
    def _project(self, root: Path, version="1.6.2") -> Path:
        external = root / "external"
        external.mkdir()
        (external / "components.json").write_text(
            json.dumps({"schema_version": 1, "components": {"kosit-validator": version}}),
            encoding="utf-8",
        )
        return root

    def _release(self, version="1.6.3", payload=b"jar") -> KositRelease:
        return KositRelease(
            Version(version),
            f"https://github.com/itplr-kosit/validator/releases/tag/v{version}",
            ReleaseAsset(
                f"validator-{version}-standalone.jar",
                f"https://github.com/itplr-kosit/validator/releases/download/v{version}/validator-{version}-standalone.jar",
                len(payload),
                hashlib.sha256(payload).hexdigest(),
            ),
        )

    def test_official_release_asset_is_selected(self):
        digest = "a" * 64
        release = _parse_release({
            "tag_name": "v1.6.3",
            "draft": False,
            "prerelease": False,
            "html_url": "https://github.com/itplr-kosit/validator/releases/tag/v1.6.3",
            "assets": [{
                "name": "validator-1.6.3-standalone.jar",
                "browser_download_url": "https://github.com/itplr-kosit/validator/releases/download/v1.6.3/validator-1.6.3-standalone.jar",
                "size": 123,
                "digest": f"sha256:{digest}",
            }],
        })
        self.assertEqual(release.version, Version("1.6.3"))
        self.assertEqual(release.asset.sha256, digest)

    def test_release_without_vendor_digest_is_rejected(self):
        with self.assertRaisesRegex(KositBuilderError, "keinen SHA-256-Digest"):
            _parse_release({
                "tag_name": "v1.6.3",
                "draft": False,
                "prerelease": False,
                "assets": [{
                    "name": "validator-1.6.3-standalone.jar",
                    "browser_download_url": "https://github.com/itplr-kosit/validator/releases/download/v1.6.3/validator-1.6.3-standalone.jar",
                    "size": 123,
                    "digest": None,
                }],
            })

    def test_download_must_match_size_and_sha256(self):
        payload = b"verified jar"
        release = self._release(payload=payload)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / release.asset.name
            with patch("build_support.kosit_builder._open_url", return_value=_Response(payload)):
                _download_verified(release.asset, destination)
            self.assertEqual(destination.read_bytes(), payload)

    def test_current_version_causes_no_project_change(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory), "1.6.3")
            with patch("build_support.kosit_builder.fetch_latest_release", return_value=self._release()):
                self.assertFalse(check_and_update(project))

    def test_check_only_reports_newer_version_without_download(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            with (
                patch("build_support.kosit_builder.fetch_latest_release", return_value=self._release()),
                patch("build_support.kosit_builder._download_verified") as download,
            ):
                self.assertTrue(check_and_update(project, check_only=True))
            download.assert_not_called()

    def test_update_builds_package_and_invokes_maintainer_installer(self):
        payload = b"new jar"
        release = self._release(payload=payload)
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))

            def fake_download(_asset, destination):
                destination.write_bytes(payload)

            with (
                patch("build_support.kosit_builder.fetch_latest_release", return_value=release),
                patch("build_support.kosit_builder._download_verified", side_effect=fake_download),
                patch("build_support.kosit_builder.update_external_components") as install,
            ):
                self.assertTrue(check_and_update(project))
            install.assert_called_once()
            self.assertEqual(install.call_args.args[1], project.resolve())


if __name__ == "__main__":
    unittest.main()
