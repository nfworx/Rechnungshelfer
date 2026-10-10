import tempfile
import unittest
from pathlib import Path

from rechnungshelfer.application.grain_scheme_service import (
    GrainSchemeApplicationService,
)
from rechnungshelfer.repositories.database import Database
from rechnungshelfer.repositories.grain_scheme_repository import (
    GrainSchemeRepository,
)


class GrainSchemeRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary_directory.name) / "schemes.db")
        self.repository = GrainSchemeRepository(self.database.connection)
        self.service = GrainSchemeApplicationService(
            database=self.database,
            repository=self.repository,
        )

    def tearDown(self):
        self.database.close()
        self.temporary_directory.cleanup()

    @staticmethod
    def _payload(factor: str):
        return {
            "format_version": 1,
            "name": "Weizen Standard",
            "features": [{"code": "moisture", "label": "Feuchtigkeit"}],
            "rules": [{"code": "shrink", "parameters": f"factor={factor}"}],
        }

    def test_draft_can_be_overwritten_without_creating_versions(self):
        self.service.save_drafts(2026, {"wheat": self._payload("1,3")})
        self.service.save_drafts(2026, {"wheat": self._payload("1,4")})

        drafts = self.service.load_drafts(2026)

        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].payload["rules"][0]["parameters"], "factor=1,4")
        self.assertEqual(self.service.list_versions("wheat", 2026), ())

    def test_each_activation_creates_an_immutable_revision_snapshot(self):
        first = self.service.activate("wheat", 2026, self._payload("1,3"))
        second = self.service.activate("wheat", 2026, self._payload("1,4"))

        versions = self.service.list_versions("wheat", 2026)

        self.assertEqual(first.display_version, "2026.1")
        self.assertEqual(second.display_version, "2026.2")
        self.assertEqual([version.revision for version in versions], [2, 1])
        self.assertEqual(
            versions[1].payload["rules"][0]["parameters"],
            "factor=1,3",
        )
        self.assertEqual(
            versions[0].payload["rules"][0]["parameters"],
            "factor=1,4",
        )
        self.assertEqual(self.repository.load_version(first.id), first)
        self.assertEqual(self.repository.load_version(second.id), second)

    def test_drafts_are_separated_by_grain_type_and_harvest_year(self):
        self.service.save_drafts(2026, {"wheat": self._payload("1,3")})
        self.service.save_drafts(2027, {"wheat": self._payload("1,5")})
        self.service.save_drafts(2026, {"barley": self._payload("1,2")})

        drafts_2026 = self.service.load_drafts(2026)
        drafts_2027 = self.service.load_drafts(2027)

        self.assertEqual(
            {draft.grain_type_code for draft in drafts_2026},
            {"wheat", "barley"},
        )
        self.assertEqual(len(drafts_2027), 1)
        self.assertEqual(drafts_2027[0].grain_type_code, "wheat")

    def test_invalid_harvest_year_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Erntejahr"):
            self.service.save_drafts(1999, {"wheat": self._payload("1,3")})


if __name__ == "__main__":
    unittest.main()
