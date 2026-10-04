"""Kompatible Namen fuer die gemeinsam genutzten Beispieldokumente."""

from rechnungshelfer.services.sample_document_service import (
    create_sample_invoice as create_validator_invoice,
    create_sample_self_billed_invoice as create_validator_self_billed_invoice,
)


__all__ = [
    "create_validator_invoice",
    "create_validator_self_billed_invoice",
]
