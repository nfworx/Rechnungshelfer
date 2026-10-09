import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from rechnungshelfer.services.pdf_import_service import (
    ExtractionMethod,
    PdfImportService,
)
from tests.settlement_test_document import (
    EXPECTED_TEST_SETTLEMENT,
    create_test_settlement_pdf,
)


class TestSettlementDocumentTests(unittest.TestCase):
    def test_expected_values_are_internally_consistent(self):
        document = EXPECTED_TEST_SETTLEMENT

        self.assertEqual(len(document.deliveries), 4)
        self.assertEqual(
            document.net_amount,
            sum(
                (delivery.net_amount for delivery in document.deliveries),
                Decimal("0"),
            ),
        )
        self.assertEqual(document.net_amount, Decimal("2087.53"))
        self.assertEqual(document.vat_amount, Decimal("162.83"))
        self.assertEqual(document.credit_amount, Decimal("2250.36"))

        for delivery in document.deliveries:
            self.assertEqual(
                delivery.settlement_quantity_kg,
                delivery.gross_quantity_kg - delivery.quantity_deduction_kg,
            )
            self.assertEqual(
                delivery.settlement_price_per_tonne,
                delivery.base_price_per_tonne
                - delivery.price_deduction_per_tonne,
            )

    def test_generated_pdf_is_raster_only_and_uses_ocr_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "testabrechnung.pdf"
            create_test_settlement_pdf(path)

            original_bytes = path.read_bytes()
            result = PdfImportService(ocr_engine=None).extract(path)

            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 0)
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertEqual(result.page_count, 1)
            self.assertEqual(result.full_text, "")
            self.assertEqual(result.pages[0].method, ExtractionMethod.NONE)
            self.assertTrue(result.pages[0].needs_ocr)


if __name__ == "__main__":
    unittest.main()
