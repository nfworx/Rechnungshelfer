"""SQLite-Persistenz für bestätigte strukturierte Getreidegutschriften."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .grain_credit_note_record import (
    grain_credit_note_from_data,
    grain_credit_note_to_data,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GrainCreditNoteRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    def save(self, note, *, overwrite=False, commit=True) -> None:
        data = grain_credit_note_to_data(note)
        values = (
            note.credit_note_number,
            json.dumps(data, ensure_ascii=False),
            note.credit_note_date.isoformat(),
            note.supplier.supplier_number,
            note.supplier.name,
            str(note.credit_amount),
            _now(),
        )
        if overwrite:
            self.conn.execute(
                """
                INSERT INTO grain_credit_notes
                    (credit_note_number, data, credit_note_date, supplier_number,
                     supplier_name, credit_amount, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(credit_note_number) DO UPDATE SET
                    data = excluded.data,
                    credit_note_date = excluded.credit_note_date,
                    supplier_number = excluded.supplier_number,
                    supplier_name = excluded.supplier_name,
                    credit_amount = excluded.credit_amount,
                    updated_at = excluded.updated_at
                """,
                values,
            )
        else:
            self.conn.execute(
                """
                INSERT INTO grain_credit_notes
                    (credit_note_number, data, credit_note_date, supplier_number,
                     supplier_name, credit_amount, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        if commit:
            self.conn.commit()

    def load(self, credit_note_number: str):
        row = self.conn.execute(
            "SELECT data FROM grain_credit_notes WHERE credit_note_number = ?",
            (credit_note_number,),
        ).fetchone()
        if row is None:
            return None
        return grain_credit_note_from_data(json.loads(row[0]))

    def exists(self, credit_note_number: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM grain_credit_notes WHERE credit_note_number = ?",
            (str(credit_note_number or "").strip(),),
        ).fetchone() is not None

    def list_summaries(self) -> tuple[dict, ...]:
        rows = self.conn.execute(
            """
            SELECT credit_note_number, credit_note_date, supplier_number,
                   supplier_name, credit_amount, updated_at
            FROM grain_credit_notes
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return tuple(
            {
                "credit_note_number": row[0],
                "credit_note_date": row[1],
                "supplier_number": row[2],
                "supplier_name": row[3],
                "credit_amount": row[4],
                "updated_at": row[5],
            }
            for row in rows
        )

    def delete(self, credit_note_number: str, *, commit=True) -> None:
        self.conn.execute(
            "DELETE FROM grain_credit_notes WHERE credit_note_number = ?",
            (credit_note_number,),
        )
        if commit:
            self.conn.commit()


__all__ = ["GrainCreditNoteRepository"]
