import io
import json
import unittest
from unittest.mock import patch

from packaging.version import Version

from build_support.tesseract_release import (
    TesseractReleaseError,
    _parse_release,
    fetch_latest_release,
)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class TesseractReleaseTests(unittest.TestCase):
    @staticmethod
    def _payload(**changes):
        payload = {
            "tag_name": "5.5.3",
            "html_url": "https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.3",
            "draft": False,
            "prerelease": False,
            "immutable": False,
            "assets": [{
                "name": "tesseract-ocr-w64-setup-5.5.3.20260724.exe",
                "browser_download_url": (
                    "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/"
                    "tesseract-ocr-w64-setup-5.5.3.20260724.exe"
                ),
                "size": 51_000_000,
                "digest": "sha256:" + "a" * 64,
            }],
        }
        payload.update(changes)
        return payload

    def test_official_windows_installer_is_reported_without_download(self):
        release = _parse_release(self._payload())

        self.assertEqual(release.version, Version("5.5.3"))
        self.assertEqual(release.package_version, Version("5.5.3.20260724"))
        self.assertEqual(release.github_sha256, "a" * 64)
        self.assertIn("w64-setup", release.installer_name)

    def test_missing_github_digest_is_allowed_for_manual_approval(self):
        payload = self._payload()
        payload["assets"][0]["digest"] = None

        release = _parse_release(payload)

        self.assertIsNone(release.github_sha256)

    def test_unofficial_download_url_is_rejected(self):
        payload = self._payload()
        payload["assets"][0]["browser_download_url"] = "https://example.invalid/tesseract.exe"

        with self.assertRaisesRegex(TesseractReleaseError, "Downloadadresse"):
            _parse_release(payload)

    def test_fetch_reads_only_the_release_metadata(self):
        encoded = json.dumps(self._payload()).encode("utf-8")
        with patch("build_support.tesseract_release._open_url", return_value=_Response(encoded)) as opener:
            release = fetch_latest_release()

        opener.assert_called_once()
        self.assertEqual(release.version, Version("5.5.3"))


if __name__ == "__main__":
    unittest.main()
