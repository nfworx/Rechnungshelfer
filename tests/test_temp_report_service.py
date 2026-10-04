import tempfile
import unittest
from pathlib import Path

from services.temp_report_service import (
    LEGACY_REPORT_PREFIX,
    REPORT_PREFIX,
    cleanup_current_temp_reports,
    cleanup_stale_temp_reports,
    create_temp_report,
)


class TempReportServiceTests(unittest.TestCase):
    def tearDown(self):
        cleanup_current_temp_reports()

    def test_current_session_report_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = create_temp_report("<html>Bericht</html>", directory=Path(directory))
            self.assertTrue(path.is_file())
            self.assertTrue(path.name.startswith(REPORT_PREFIX))

            self.assertEqual(cleanup_current_temp_reports(), 1)
            self.assertFalse(path.exists())

    def test_stale_and_legacy_reports_are_removed_but_other_html_remains(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = root / f"{REPORT_PREFIX}alt.html"
            legacy = root / f"{LEGACY_REPORT_PREFIX}alt.html"
            unrelated = root / "anderer-bericht.html"
            for path in (stale, legacy, unrelated):
                path.write_text("test", encoding="utf-8")

            self.assertEqual(cleanup_stale_temp_reports(directory=root), 2)
            self.assertFalse(stale.exists())
            self.assertFalse(legacy.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
