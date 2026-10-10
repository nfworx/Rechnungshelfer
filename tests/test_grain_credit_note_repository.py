import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from rechnungshelfer.application.grain_credit_note_service import (
    GrainCreditNoteApplicationService,
    GrainCreditNoteExistsError,
)
from rechnungshelfer.application.settlement_review_service import (
    SettlementReviewService,
)
from rechnungshelfer.domain.grain_credit_note import (
    GrainCreditNoteBuyer,
    GrainRuleCheck,
    GrainRuleDeviation,
    GrainSchemeReference,
)
from rechnungshelfer.repositories.database import Database
from rechnungshelfer.repositories.grain_credit_note_repository import (
    GrainCreditNoteRepository,
)
from rechnungshelfer.repositories.grain_credit_note_record import (
    grain_credit_note_from_data,
    grain_credit_note_to_data,
)
from rechnungshelfer.services.settlement_credit_note_parser import (
    SettlementCreditNoteParser,
)
from tests.test_settlement_credit_note_parser import (
    SETTLEMENT_TEXT,
    extraction_with,
)


def structured_note():
    draft = SettlementCreditNoteParser().parse(extraction_with(SETTLEMENT_TEXT))
    review_service = SettlementReviewService()
    note = review_service.create_credit_note(review_service.create_review(draft))
    return replace(
        note,
        buyer=GrainCreditNoteBuyer(
            name="Eigener Testbetrieb",
            street="Hofweg 1",
            postcode="12345",
            city="Teststadt",
            country="DE",
            leitweg_id="EIGENER-BETRIEB",
            email="betrieb@example.de",
            vat="DE123456789",
        ),
    )


class GrainCreditNoteRepositoryTests(unittest.TestCase):
    def test_complete_note_survives_database_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.db"
            database = Database(path)
            service = GrainCreditNoteApplicationService(
                database=database,
                repository=GrainCreditNoteRepository(database.connection),
                review_service=SettlementReviewService(),
            )
            expected = structured_note()
            service.save(expected)
            database.close()

            reopened = Database(path)
            try:
                loaded = GrainCreditNoteApplicationService(
                    database=reopened,
                    repository=GrainCreditNoteRepository(reopened.connection),
                    review_service=SettlementReviewService(),
                ).load(expected.credit_note_number)
            finally:
                reopened.close()

        self.assertEqual(loaded, expected)
        self.assertEqual(loaded.deliveries[0].details, expected.deliveries[0].details)
        self.assertEqual(loaded.advance_payment, expected.advance_payment)
        self.assertEqual(loaded.buyer, expected.buyer)

    def test_origin_rule_version_and_deviation_survive_database_restart(self):
        note = structured_note()
        reference = GrainSchemeReference(
            version_id=17,
            grain_type_code="oats",
            harvest_year=2025,
            revision=3,
            name="Hafer Testregeln",
        )
        first = note.deliveries[0]
        first_detail = replace(
            first.details[0],
            rule_deviation=GrainRuleDeviation(
                document_quantity_change_kg="-28",
                expected_quantity_change_kg="0",
            ),
        )
        note = replace(
            note,
            origin="pdf_import",
            deliveries=(
                replace(
                    first,
                    details=(first_detail, *first.details[1:]),
                    rule_check=GrainRuleCheck(
                        status="checked",
                        scheme=reference,
                    ),
                ),
                *note.deliveries[1:],
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.db"
            database = Database(path)
            GrainCreditNoteRepository(database.connection).save(note)
            database.close()
            reopened = Database(path)
            try:
                loaded = GrainCreditNoteRepository(reopened.connection).load(
                    note.credit_note_number
                )
            finally:
                reopened.close()

        self.assertEqual(loaded, note)

    def test_record_version_one_remains_readable_without_guessed_origin(self):
        data = grain_credit_note_to_data(structured_note())
        data["record_version"] = 1
        data.pop("origin")
        for delivery in data["deliveries"]:
            delivery.pop("rule_check")
            for detail in delivery["details"]:
                detail.pop("rule_deviation")

        loaded = grain_credit_note_from_data(data)

        self.assertEqual(loaded.origin, "unknown")
        self.assertTrue(
            all(
                delivery.rule_check.status == "not_requested"
                for delivery in loaded.deliveries
            )
        )

    def test_source_pdf_and_ocr_metadata_are_not_stored(self):
        database = Database(":memory:")
        try:
            repository = GrainCreditNoteRepository(database.connection)
            note = structured_note()
            repository.save(note)
            payload = database.connection.execute(
                "SELECT data FROM grain_credit_notes"
            ).fetchone()[0]
        finally:
            database.close()

        data = json.loads(payload)
        self.assertNotIn("source_file", payload)
        self.assertNotIn("raw_text", payload)
        self.assertNotIn("confidence", payload)
        self.assertEqual(data["record_version"], 2)
        self.assertEqual(data["origin"], "pdf_import")
        self.assertEqual(data["buyer"]["name"], "Eigener Testbetrieb")

    def test_existing_number_requires_explicit_overwrite(self):
        database = Database(":memory:")
        try:
            service = GrainCreditNoteApplicationService(
                database=database,
                repository=GrainCreditNoteRepository(database.connection),
                review_service=SettlementReviewService(),
            )
            note = structured_note()
            service.save(note)
            changed = replace(
                note,
                supplier=replace(note.supplier, name="Geänderter Musterhof"),
            )

            with self.assertRaises(GrainCreditNoteExistsError):
                service.save(changed)

            service.save(changed, overwrite=True)
            loaded = service.load(note.credit_note_number)
        finally:
            database.close()

        self.assertEqual(loaded.supplier.name, "Geänderter Musterhof")

    def test_summaries_are_read_without_deserializing_full_notes(self):
        database = Database(":memory:")
        try:
            repository = GrainCreditNoteRepository(database.connection)
            repository.save(structured_note())
            summaries = repository.list_summaries()
        finally:
            database.close()

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["credit_note_number"], "91001")
        self.assertEqual(summaries[0]["supplier_name"], "Musterhof Testlieferant")
        self.assertEqual(summaries[0]["credit_amount"], "2250.36")

    def test_changed_number_replaces_previous_record_without_orphan(self):
        database = Database(":memory:")
        try:
            service = GrainCreditNoteApplicationService(
                database=database,
                repository=GrainCreditNoteRepository(database.connection),
                review_service=SettlementReviewService(),
            )
            note = structured_note()
            service.save(note)
            renamed = replace(note, credit_note_number="91002")

            service.save(renamed, previous_number="91001")

            summaries = service.list_summaries()
        finally:
            database.close()

        self.assertEqual(
            [item["credit_note_number"] for item in summaries],
            ["91002"],
        )


if __name__ == "__main__":
    unittest.main()
