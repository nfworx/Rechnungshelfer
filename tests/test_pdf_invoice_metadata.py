import unittest

from rechnungshelfer.domain.models import InvoiceItem
from rechnungshelfer.services.pdf_invoice_metadata import (
    METADATA_PREFIX,
    decode_invoice_metadata,
    encode_invoice_metadata,
)
from rechnungshelfer.services.sample_document_service import create_sample_invoice


class PdfInvoiceMetadataTests(unittest.TestCase):
    def test_metadata_roundtrips_large_invoice(self):
        invoice = create_sample_invoice()
        invoice.items = [
            InvoiceItem(
                pos=index,
                name=f"Position {index}",
                description="Ausführliche Positionsbeschreibung " * 5,
                qty="1",
                price_without_discount="1",
                vat="19",
            )
            for index in range(1, 1001)
        ]
        invoice.calculate(force=True)

        encoded = encode_invoice_metadata(invoice)
        decoded = decode_invoice_metadata(encoded)

        self.assertTrue(encoded.startswith(METADATA_PREFIX))
        self.assertEqual(decoded, invoice.to_dict())


if __name__ == "__main__":
    unittest.main()
