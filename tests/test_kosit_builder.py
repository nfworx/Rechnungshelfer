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
    install_release,
)


class _Response:
    def __init__(self, payload: bytes, final_url="https://github.com/download.jar"):
        self.payload = payload
        self.position = 0
        self.final_url = final_url

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

    def geturl(self):
        return self.final_url


class KositBuilderTests(unittest.TestCase):
    def _project(self, root: Path, version="1.6.2", trusted_payload=b"jar") -> Path:
        external = root / "external"
        external.mkdir()
        (external / "components.json").write_text(
            json.dumps({"schema_version": 1, "components": {"kosit-validator": version}}),
            encoding="utf-8",
        )
        trust_dir = root / "build_support"
        trust_dir.mkdir()
        (trust_dir / "kosit_trusted_releases.json").write_text(
            json.dumps({
                "schema_version": 1,
                "releases": {"1.6.3": hashlib.sha256(trusted_payload).hexdigest()},
            }),
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
            "immutable": True,
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
        self.assertTrue(release.immutable)

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

    def test_download_rejects_redirect_to_http(self):
        payload = b"verified jar"
        release = self._release(payload=payload)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / release.asset.name
            response = _Response(payload, "http://example.invalid/download.jar")
            with (
                patch("build_support.kosit_builder._open_url", return_value=response),
                self.assertRaisesRegex(KositBuilderError, "unsichere URL"),
            ):
                _download_verified(release.asset, destination)
            self.assertFalse(destination.exists())

    def test_install_requires_locally_approved_digest_and_execution(self):
        payload = b"verified jar"
        release = self._release(payload=payload)
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory), trusted_payload=b"different")
            with (
                patch("build_support.kosit_builder._running_elevated", return_value=False),
                patch("build_support.kosit_builder._download_verified", side_effect=lambda _a, p: p.write_bytes(payload)),
                patch("build_support.kosit_builder.update_external_components") as install,
                self.assertRaisesRegex(KositBuilderError, "Freigegebener SHA-256"),
            ):
                install_release(project, release, approve_execution=lambda _release: True)
            install.assert_not_called()

            trust_path = project / "build_support" / "kosit_trusted_releases.json"
            trust_path.write_text(json.dumps({
                "schema_version": 1,
                "releases": {"1.6.3": release.asset.sha256},
            }), encoding="utf-8")
            with (
                patch("build_support.kosit_builder._running_elevated", return_value=False),
                patch("build_support.kosit_builder._download_verified", side_effect=lambda _a, p: p.write_bytes(payload)),
                patch("build_support.kosit_builder.update_external_components") as install,
                self.assertRaisesRegex(KositBuilderError, "nicht freigegeben"),
            ):
                install_release(project, release, approve_execution=lambda _release: False)
            install.assert_not_called()

    def test_install_refuses_elevated_windows_process(self):
        release = self._release()
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            with (
                patch("build_support.kosit_builder._running_elevated", return_value=True),
                self.assertRaisesRegex(KositBuilderError, "Administrator"),
            ):
                install_release(project, release, approve_execution=lambda _release: True)

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
            project = self._project(Path(directory), trusted_payload=payload)

            def fake_download(_asset, destination):
                destination.write_bytes(payload)

            with (
                patch("build_support.kosit_builder.fetch_latest_release", return_value=release),
                patch("build_support.kosit_builder._download_verified", side_effect=fake_download),
                patch("build_support.kosit_builder.update_external_components") as install,
            ):
                self.assertTrue(check_and_update(project, approve_execution=lambda _release: True))
            install.assert_called_once()
            self.assertEqual(install.call_args.args[1], project.resolve())


if __name__ == "__main__":
    unittest.main()
