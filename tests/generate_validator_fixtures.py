"""Erzeugt die eingecheckten XML-Belege aus den Python-Testfixtures neu."""

from pathlib import Path

from rechnungshelfer.services.xml_service import create_xml
from tests.validation_documents import (
    create_validator_invoice,
    create_validator_self_billed_invoice,
)


OUTPUT_DIR = Path(__file__).parent / "fixtures" / "validator"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    documents = {
        "test-rechnung.xml": create_validator_invoice(),
        "test-gutschrift.xml": create_validator_self_billed_invoice(),
    }
    for filename, invoice in documents.items():
        (OUTPUT_DIR / filename).write_bytes(create_xml(invoice))


if __name__ == "__main__":
    main()
