import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from rechnungshelfer.services.pdf_import_service import (
    ExtractionMethod,
    PdfImportResult,
    PdfImportService,
    PdfPageResult,
)
from rechnungshelfer.services.settlement_credit_note_parser import (
    SettlementCreditNoteParser,
)
from rechnungshelfer.services.tesseract_ocr_service import TesseractOcrEngine
from rechnungshelfer.services.sample_settlement_pdf_service import (
    create_test_settlement_pdf,
)


SETTLEMENT_TEXT = """SAMMEL - FINAL - GUTSCHRIFT
Nr.: 91001 vom 30.11.2025
Analysewerte Bezeichnung Menge Preis EUR je t Betrag EUR
Lieferschein-Nr.: T1001 vom 09.08.2025
Hafer lose 2.815 160,00
1,00 % Besatz -28
40,00 % HL-Gewicht -15,50
Hafer lose 2.787 144,50 402,72
Lieferschein-Nr.: T1002 vom 10.08.2025
Hafer lose 3.765 160,00
1,00 % Besatz -37
41,00 % HL-Gewicht -15,50
Hafer lose 3.728 144,50 538,70
Lieferschein-Nr.: T1003 vom 14.08.2025
Hafer lose 6.352 160,00
1,00 % Besatz -63
41,00 % HL-Gewicht -15,50
Hafer lose 6.289 144,50 908,76
Lieferschein-Nr.: T1004 vom 15.08.2025
Hafer lose 1.645 160,00
1,00 % Besatz -16
42,70 % HL-Gewicht -14,30
Hafer lose 1.629 145,70 237,35
2.087,53
7,8 % Mehrwertsteuer EUR 162,83
Gesamtbetrag 2.250,36
Abschlagszahlung 0,00
Gutschriftbetrag in EUR 2.250,36
"""


def extraction_with(text: str) -> PdfImportResult:
    return PdfImportResult(
        source_file=Path("testabrechnung.pdf"),
        page_count=1,
        pages=(
            PdfPageResult(
                page_number=1,
                text=text,
                method=ExtractionMethod.DIGITAL,
            ),
        ),
    )


class SettlementCreditNoteParserTests(unittest.TestCase):
    def test_parses_complete_test_settlement(self):
        draft = SettlementCreditNoteParser().parse(extraction_with(SETTLEMENT_TEXT))

        self.assertIsNotNone(draft)
        self.assertEqual(draft.credit_note_number.value, "91001")
        self.assertEqual(draft.credit_note_date.value, date(2025, 11, 30))
        self.assertEqual(len(draft.deliveries), 4)
        self.assertEqual(
            [delivery.ticket_number.value for delivery in draft.deliveries],
            ["T1001", "T1002", "T1003", "T1004"],
        )

        first = draft.deliveries[0]
        self.assertEqual(first.grain_name.value, "Hafer lose")
        self.assertEqual(first.gross_quantity_kg.value, Decimal("2815"))
        self.assertEqual(first.settlement_quantity_kg.value, Decimal("2787"))
        self.assertEqual(first.base_price_per_tonne.value, Decimal("160.00"))
        self.assertEqual(first.settlement_price_per_tonne.value, Decimal("144.50"))
        self.assertEqual(first.net_amount.value, Decimal("402.72"))
        self.assertEqual(len(first.details), 2)
        self.assertEqual(first.details[0].analysis_value.value, Decimal("1.00"))
        self.assertEqual(first.details[0].quantity_change_kg.value, Decimal("-28"))
        self.assertEqual(first.details[1].analysis_value.value, Decimal("40.00"))
        self.assertEqual(
            first.details[1].price_change_per_tonne.value,
            Decimal("-15.50"),
        )

        self.assertEqual(draft.vat_rate.value, Decimal("7.8"))
        self.assertEqual(draft.net_amount.value, Decimal("2087.53"))
        self.assertEqual(draft.vat_amount.value, Decimal("162.83"))
        self.assertEqual(draft.total_amount.value, Decimal("2250.36"))
        self.assertEqual(draft.advance_payment.value, Decimal("0.00"))
        self.assertEqual(draft.credit_amount.value, Decimal("2250.36"))
        self.assertEqual(draft.warnings, ())

    def test_rejects_ordinary_credit_note(self):
        draft = SettlementCreditNoteParser().parse(
            extraction_with(
                "Gutschrift\nGutschriftsnummer: GS-55\nGesamtbetrag 100,00"
            )
        )

        self.assertIsNone(draft)

    def test_incomplete_delivery_is_kept_with_warning(self):
        text = """SAMMEL-FINAL-GUTSCHRIFT
Nr.: 12 vom 01.02.2026
Bezeichnung Menge Preis Betrag
Lieferschein-Nr.: L-1 vom 31.01.2026
1,00 % Besatz -10
"""

        draft = SettlementCreditNoteParser().parse(extraction_with(text))

        self.assertIsNotNone(draft)
        self.assertEqual(len(draft.deliveries), 1)
        self.assertTrue(any("keine Produktzeile" in item for item in draft.warnings))
        self.assertTrue(any("Nettosumme" in item for item in draft.warnings))

    def test_rasterized_document_reaches_parser_through_real_ocr(self):
        engine = TesseractOcrEngine()
        if not engine.is_available:
            self.skipTest("Die portable Tesseract-Laufzeit ist nicht verfügbar.")

        with tempfile.TemporaryDirectory() as tmp:
            path = create_test_settlement_pdf(Path(tmp) / "testabrechnung.pdf")
            extraction = PdfImportService(ocr_engine=engine).extract(path)

        draft = SettlementCreditNoteParser().parse(extraction)

        self.assertIsNotNone(draft)
        self.assertEqual(draft.credit_note_number.value, "91001")
        self.assertEqual(len(draft.deliveries), 4)
        self.assertEqual(draft.vat_rate.value, Decimal("7.8"))
        self.assertEqual(draft.credit_amount.value, Decimal("2250.36"))
        self.assertIsNotNone(draft.credit_note_number.bounds)
        self.assertLess(draft.credit_note_number.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
