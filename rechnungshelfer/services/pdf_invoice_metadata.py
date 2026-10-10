"""Versionierte Rechnungsdaten fuer den verlustfreien PDF-Rueckimport."""

from __future__ import annotations

import json
from dataclasses import dataclass


METADATA_PREFIX = "Rechnungshelfer-Invoice-v1:"
MAX_METADATA_LENGTH = 20_000_000
DOCUMENT_KIND_INVOICE = "invoice"
DOCUMENT_KIND_SELF_BILLED_INVOICE = "self_billed_invoice"
DOCUMENT_KIND_GRAIN_CREDIT_NOTE = "grain_credit_note"
_DOCUMENT_KINDS = {
    DOCUMENT_KIND_INVOICE,
    DOCUMENT_KIND_SELF_BILLED_INVOICE,
    DOCUMENT_KIND_GRAIN_CREDIT_NOTE,
}


@dataclass(frozen=True)
class PdfDocumentMetadata:
    document_kind: str
    invoice: dict
    grain_credit_note: dict | None = None


def encode_invoice_metadata(
    invoice,
    *,
    document_kind: str | None = None,
    grain_credit_note_data: dict | None = None,
) -> str:
    inferred_kind = (
        DOCUMENT_KIND_SELF_BILLED_INVOICE
        if invoice.is_self_billed
        else DOCUMENT_KIND_INVOICE
    )
    document_kind = document_kind or inferred_kind
    if document_kind not in _DOCUMENT_KINDS:
        raise ValueError("Unbekannter eingebetteter Belegtyp.")
    if document_kind == DOCUMENT_KIND_INVOICE and invoice.is_self_billed:
        raise ValueError("Eingebetteter Belegtyp widerspricht der Rechnung.")
    if (
        document_kind in {
            DOCUMENT_KIND_SELF_BILLED_INVOICE,
            DOCUMENT_KIND_GRAIN_CREDIT_NOTE,
        }
        and not invoice.is_self_billed
    ):
        raise ValueError("Eingebetteter Belegtyp widerspricht der Gutschrift.")
    if document_kind == DOCUMENT_KIND_GRAIN_CREDIT_NOTE:
        if not isinstance(grain_credit_note_data, dict):
            raise ValueError("Strukturierte Getreidegutschriftdaten fehlen.")
    elif grain_credit_note_data is not None:
        raise ValueError("Getreidegutschriftdaten passen nicht zum Belegtyp.")

    payload = {
        "schema": 2,
        "document_kind": document_kind,
        "invoice": invoice.to_dict(),
    }
    if grain_credit_note_data is not None:
        payload["grain_credit_note"] = grain_credit_note_data
    result = METADATA_PREFIX + json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(result) > MAX_METADATA_LENGTH:
        raise ValueError("Eingebettete Rechnungsdaten sind zu gross.")
    return result


def decode_pdf_metadata(subject: str | None) -> PdfDocumentMetadata | None:
    if not subject or not subject.startswith(METADATA_PREFIX):
        return None
    if len(subject) > MAX_METADATA_LENGTH:
        raise ValueError("Eingebettete Rechnungsdaten sind zu gross.")
    try:
        payload = json.loads(subject[len(METADATA_PREFIX):])
    except (TypeError, ValueError) as exc:
        raise ValueError("Eingebettete Rechnungsdaten sind ungueltig.") from exc

    if not isinstance(payload, dict) or payload.get("schema") not in {1, 2}:
        raise ValueError("Eingebettete Rechnungsdaten haben eine unbekannte Version.")
    invoice = payload.get("invoice")
    if not isinstance(invoice, dict):
        raise ValueError("Eingebettete Rechnungsdaten sind unvollstaendig.")
    if payload["schema"] == 1:
        document_kind = str(invoice.get("document_type") or "")
        if document_kind not in {
            DOCUMENT_KIND_INVOICE,
            DOCUMENT_KIND_SELF_BILLED_INVOICE,
        }:
            raise ValueError(
                "Eingebettete Rechnungsdaten enthalten keinen gueltigen Belegtyp."
            )
        return PdfDocumentMetadata(document_kind=document_kind, invoice=invoice)

    document_kind = payload.get("document_kind")
    if document_kind not in _DOCUMENT_KINDS:
        raise ValueError(
            "Eingebettete Rechnungsdaten enthalten keinen gueltigen Belegtyp."
        )
    grain_credit_note = payload.get("grain_credit_note")
    if document_kind == DOCUMENT_KIND_GRAIN_CREDIT_NOTE:
        if not isinstance(grain_credit_note, dict):
            raise ValueError(
                "Eingebettete Getreidegutschriftdaten sind unvollstaendig."
            )
    elif grain_credit_note is not None:
        raise ValueError("Eingebettete Getreidegutschriftdaten passen nicht zum Belegtyp.")
    return PdfDocumentMetadata(
        document_kind=document_kind,
        invoice=invoice,
        grain_credit_note=grain_credit_note,
    )


def decode_invoice_metadata(subject: str | None) -> dict | None:
    metadata = decode_pdf_metadata(subject)
    return metadata.invoice if metadata is not None else None


__all__ = [
    "DOCUMENT_KIND_GRAIN_CREDIT_NOTE",
    "DOCUMENT_KIND_INVOICE",
    "DOCUMENT_KIND_SELF_BILLED_INVOICE",
    "PdfDocumentMetadata",
    "decode_invoice_metadata",
    "decode_pdf_metadata",
    "encode_invoice_metadata",
]
