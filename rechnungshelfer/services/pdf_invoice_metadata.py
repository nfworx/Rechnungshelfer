"""Versionierte Rechnungsdaten fuer den verlustfreien PDF-Rueckimport."""

from __future__ import annotations

import json


METADATA_PREFIX = "Rechnungshelfer-Invoice-v1:"
MAX_METADATA_LENGTH = 200_000


def encode_invoice_metadata(invoice) -> str:
    payload = {
        "schema": 1,
        "invoice": invoice.to_dict(),
    }
    return METADATA_PREFIX + json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def decode_invoice_metadata(subject: str | None) -> dict | None:
    if not subject or not subject.startswith(METADATA_PREFIX):
        return None
    if len(subject) > MAX_METADATA_LENGTH:
        raise ValueError("Eingebettete Rechnungsdaten sind zu gross.")

    try:
        payload = json.loads(subject[len(METADATA_PREFIX):])
    except (TypeError, ValueError) as exc:
        raise ValueError("Eingebettete Rechnungsdaten sind ungueltig.") from exc

    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("Eingebettete Rechnungsdaten haben eine unbekannte Version.")
    invoice = payload.get("invoice")
    if not isinstance(invoice, dict):
        raise ValueError("Eingebettete Rechnungsdaten sind unvollstaendig.")
    return invoice


__all__ = ["decode_invoice_metadata", "encode_invoice_metadata"]
