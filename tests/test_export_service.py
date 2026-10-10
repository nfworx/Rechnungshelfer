import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from rechnungshelfer.domain.models import Payment, Seller
from rechnungshelfer.services.export_service import (
    ExportValidationError,
    InvoiceExportService,
)
from rechnungshelfer.services.kosit_validation_service import KositValidationResult
from tests.validation_documents import (
    create_validator_invoice,
    create_validator_self_billed_invoice,
)


class StubValidator:
    def __init__(self, result: KositValidationResult):
        self.result = result
        self.payloads: list[bytes] = []

    def validate(self, xml_bytes: bytes) -> KositValidationResult:
        self.payloads.append(xml_bytes)
        return self.result


class InvoiceExportServiceTests(unittest.TestCase):
    def test_xml_export_returns_validation_result_and_writes_after_validation(self):
        validator = StubValidator(
            KositValidationResult(valid=True, report_html="<html>OK</html>")
        )
        service = InvoiceExportService(external_validator=validator)
        invoice = create_validator_invoice()

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "invoice.xml"
            result = service.export_xml(invoice, output)

            self.assertEqual(output.read_bytes(), result.xml_bytes)

        self.assertEqual(validator.payloads, [result.xml_bytes])
        self.assertTrue(result.validation_result.valid)
        self.assertEqual(
            result.validation_result.report_html,
            "<html>OK</html>",
        )

    def test_failed_external_validation_does_not_write_output(self):
        validator = StubValidator(
            KositValidationResult(
                valid=False,
                errors=["KoSIT-Testfehler"],
                report_html="<html>Fehler</html>",
            )
        )
        service = InvoiceExportService(external_validator=validator)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "invoice.xml"
            with self.assertRaises(ExportValidationError) as raised:
                service.export_xml(create_validator_invoice(), output)

            self.assertFalse(output.exists())

        self.assertIn("KoSIT-Testfehler", raised.exception.details)
        self.assertEqual(raised.exception.report_html, "<html>Fehler</html>")

    def test_self_billed_export_does_not_generate_supplier_number(self):
        validator = StubValidator(KositValidationResult(valid=True))
        service = InvoiceExportService(external_validator=validator)
        invoice = create_validator_self_billed_invoice()
        invoice.seller.supplier_number = ""

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                service.export_xml(invoice, Path(tmp) / "credit-note.xml")

        self.assertEqual(invoice.seller.supplier_number, "")

    def test_pdf_export_delegates_to_injected_renderer(self):
        renderer = MagicMock()
        service = InvoiceExportService(pdf_renderer=renderer)
        invoice = create_validator_invoice()

        service.export_pdf(invoice, "invoice.pdf")

        renderer.assert_called_once_with(invoice, "invoice.pdf")

    def test_pdf_export_passes_current_master_data_for_all_document_types(self):
        company = Seller(name="Aktuelle Firma GmbH")
        payment = Payment(
            iban="DE02120300000000202051",
            bic="BYLADEM1001",
        )
        cases = (
            ("invoice", create_validator_invoice(), {}),
            ("credit-note", create_validator_self_billed_invoice(), {}),
            (
                "grain-credit-note",
                create_validator_self_billed_invoice(),
                {
                    "document_kind": "grain_credit_note",
                    "grain_credit_note_data": {"deliveries": []},
                },
            ),
        )

        for label, invoice, export_options in cases:
            with self.subTest(document_type=label):
                renderer = MagicMock()
                provider = MagicMock(return_value=(company, payment))
                service = InvoiceExportService(
                    pdf_renderer=renderer,
                    pdf_footer_data_provider=provider,
                )

                service.export_pdf(invoice, f"{label}.pdf", **export_options)

                provider.assert_called_once()
                renderer.assert_called_once_with(
                    invoice,
                    f"{label}.pdf",
                    footer_company=company,
                    footer_payment=payment,
                    **export_options,
                )


if __name__ == "__main__":
    unittest.main()
