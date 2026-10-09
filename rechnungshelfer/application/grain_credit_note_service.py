"""Anwendungsfälle für bestätigte strukturierte Getreidegutschriften."""

from __future__ import annotations

import sqlite3


class GrainCreditNoteExistsError(ValueError):
    pass


class GrainCreditNoteApplicationService:
    def __init__(self, *, database, repository, review_service):
        self._database = database
        self._repository = repository
        self._review_service = review_service

    def save(self, note, *, overwrite=False, previous_number=None) -> None:
        review = self._review_service.create_review_from_credit_note(note)
        result = self._review_service.validate(review)
        errors = [
            issue.message
            for issue in result.issues
            if issue.severity == "error"
        ]
        for field, label in (
            ("name", "Name des eigenen Betriebs"),
            ("street", "Straße des eigenen Betriebs"),
            ("postcode", "PLZ des eigenen Betriebs"),
            ("city", "Ort des eigenen Betriebs"),
            ("country", "Land des eigenen Betriebs"),
            ("email", "E-Mail des eigenen Betriebs"),
        ):
            if not str(getattr(note.buyer, field) or "").strip():
                errors.append(f"{label} fehlt.")
        if errors:
            raise ValueError(
                "Die Getreidegutschrift kann noch nicht gespeichert werden:\n- "
                + "\n- ".join(errors)
            )
        previous = str(previous_number or "").strip()
        is_rename = previous and previous != note.credit_note_number
        if is_rename and self._repository.exists(note.credit_note_number):
            if not overwrite:
                raise GrainCreditNoteExistsError(
                    "Eine Getreidegutschrift mit dieser Nummer ist bereits "
                    "gespeichert."
                )
        try:
            with self._database.transaction():
                self._repository.save(
                    note,
                    overwrite=overwrite,
                    commit=False,
                )
                if is_rename:
                    self._repository.delete(previous, commit=False)
        except sqlite3.IntegrityError as exc:
            if self._repository.exists(note.credit_note_number):
                raise GrainCreditNoteExistsError(
                    "Eine Getreidegutschrift mit dieser Nummer ist bereits "
                    "gespeichert."
                ) from exc
            raise

    def load(self, credit_note_number: str):
        number = str(credit_note_number or "").strip()
        if not number:
            raise ValueError("Gutschriftnummer fehlt.")
        note = self._repository.load(number)
        if note is None:
            raise ValueError(f"Getreidegutschrift nicht gefunden: {number}")
        return note

    def exists(self, credit_note_number: str) -> bool:
        number = str(credit_note_number or "").strip()
        return bool(number) and self._repository.exists(number)

    def list_summaries(self):
        return self._repository.list_summaries()


__all__ = [
    "GrainCreditNoteApplicationService",
    "GrainCreditNoteExistsError",
]
