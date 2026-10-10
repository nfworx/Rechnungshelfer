import unittest
from decimal import Decimal
from unittest.mock import Mock

from rechnungshelfer.application.grain_rule_comparison import (
    compare_import_review,
)
from rechnungshelfer.application.settlement_review_service import (
    SettlementReviewService,
)
from rechnungshelfer.domain.grain_scheme_models import GrainSchemeVersionRecord
from rechnungshelfer.services.settlement_credit_note_parser import (
    SettlementCreditNoteParser,
)
from tests.test_settlement_credit_note_parser import (
    SETTLEMENT_TEXT,
    extraction_with,
)


def _active_oats_version():
    return GrainSchemeVersionRecord(
        id=17,
        grain_type_code="oats",
        harvest_year=2025,
        revision=3,
        name="Hafer Testregeln",
        activated_at="2025-01-01T00:00:00+00:00",
        payload={
            "format_version": 1,
            "name": "Hafer Testregeln",
            "features": [
                {
                    "code": "dockage",
                    "label": "Besatz",
                    "required": True,
                    "unit": "%",
                }
            ],
            "rules": [
                {
                    "code": "dockage-deduction",
                    "label": "Besatzabzug",
                    "kind": "excess_over_basis",
                    "feature_code": "dockage",
                    "quantity_reference": "gross_quantity",
                    "parameters": "basis_value=2; factor=1",
                    "tiers": "",
                    "order": 0,
                    "phase": "quantity_deduction",
                    "direction": "deduction",
                    "price_reference": "",
                    "enabled": True,
                }
            ],
        },
    )


class GrainRuleComparisonTests(unittest.TestCase):
    def setUp(self):
        draft = SettlementCreditNoteParser().parse(
            extraction_with(SETTLEMENT_TEXT)
        )
        self.service = SettlementReviewService()
        self.review = self.service.create_review(draft)

    def test_active_rule_version_adds_non_blocking_structured_deviation(self):
        repository = Mock()
        repository.list_versions.return_value = (_active_oats_version(),)

        compared = compare_import_review(self.review, repository)

        first = compared.deliveries[0]
        deviation = first.details[0].rule_deviation
        self.assertEqual(first.grain_type_code, "oats")
        self.assertEqual(first.rule_check.status, "checked")
        self.assertEqual(first.rule_check.scheme.display_version, "2025.3")
        self.assertEqual(
            deviation.document_quantity_change_kg,
            Decimal("-28"),
        )
        self.assertEqual(
            deviation.expected_quantity_change_kg,
            Decimal("0.000"),
        )
        result = self.service.validate(compared)
        self.assertTrue(result.is_valid)
        self.assertTrue(
            any(
                issue.severity == "warning"
                and "Beleg: -28 kg / Regelwerk: 0.000 kg" in issue.message
                for issue in result.issues
            )
        )

        note = self.service.create_credit_note(compared)
        self.assertEqual(note.origin, "pdf_import")
        self.assertEqual(note.deliveries[0].rule_check.scheme.version_id, 17)
        self.assertEqual(
            note.deliveries[0].details[0].rule_deviation,
            deviation,
        )

    def test_missing_rule_version_records_financial_only_check(self):
        repository = Mock()
        repository.list_versions.return_value = ()

        compared = compare_import_review(self.review, repository)
        result = self.service.validate(compared)

        self.assertTrue(result.is_valid)
        self.assertTrue(
            all(
                delivery.rule_check.status == "unavailable"
                for delivery in compared.deliveries
            )
        )
        self.assertTrue(
            any("nur die finanziellen Zusammenhänge" in issue.message for issue in result.issues)
        )

    def test_recheck_keeps_the_original_rule_version(self):
        repository = Mock()
        original = _active_oats_version()
        repository.list_versions.return_value = (original,)
        first_check = compare_import_review(self.review, repository)
        repository.reset_mock()
        repository.load_version.return_value = original

        second_check = compare_import_review(first_check, repository)

        repository.load_version.assert_called_with(original.id)
        repository.list_versions.assert_not_called()
        self.assertEqual(
            second_check.deliveries[0].rule_check.scheme.version_id,
            original.id,
        )


if __name__ == "__main__":
    unittest.main()
