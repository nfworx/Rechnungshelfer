"""SQLite-Persistenz fuer Getreide-Regelentwuerfe und Freigaben."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from rechnungshelfer.domain.grain_scheme_models import (
    GrainSchemeDraft,
    GrainSchemeVersionRecord,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GrainSchemeRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    def save_draft(self, draft: GrainSchemeDraft, *, commit: bool = True) -> None:
        updated_at = draft.updated_at or _now()
        self.conn.execute(
            """
            INSERT INTO grain_scheme_drafts
                (grain_type_code, harvest_year, name, payload, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(grain_type_code, harvest_year) DO UPDATE SET
                name = excluded.name,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (
                draft.grain_type_code,
                draft.harvest_year,
                draft.name,
                json.dumps(draft.payload, ensure_ascii=False),
                updated_at,
            ),
        )
        if commit:
            self.conn.commit()

    def load_draft(
        self,
        grain_type_code: str,
        harvest_year: int,
    ) -> GrainSchemeDraft | None:
        row = self.conn.execute(
            """
            SELECT name, payload, updated_at
            FROM grain_scheme_drafts
            WHERE grain_type_code = ? AND harvest_year = ?
            """,
            (grain_type_code, harvest_year),
        ).fetchone()
        if row is None:
            return None
        return GrainSchemeDraft(
            grain_type_code=grain_type_code,
            harvest_year=harvest_year,
            name=row[0],
            payload=json.loads(row[1]),
            updated_at=row[2],
        )

    def list_drafts(self, harvest_year: int) -> tuple[GrainSchemeDraft, ...]:
        rows = self.conn.execute(
            """
            SELECT grain_type_code, name, payload, updated_at
            FROM grain_scheme_drafts
            WHERE harvest_year = ?
            ORDER BY grain_type_code
            """,
            (harvest_year,),
        ).fetchall()
        return tuple(
            GrainSchemeDraft(
                grain_type_code=row[0],
                harvest_year=harvest_year,
                name=row[1],
                payload=json.loads(row[2]),
                updated_at=row[3],
            )
            for row in rows
        )

    def activate(
        self,
        draft: GrainSchemeDraft,
        *,
        commit: bool = True,
    ) -> GrainSchemeVersionRecord:
        revision = self.conn.execute(
            """
            SELECT COALESCE(MAX(revision), 0) + 1
            FROM grain_scheme_versions
            WHERE grain_type_code = ? AND harvest_year = ?
            """,
            (draft.grain_type_code, draft.harvest_year),
        ).fetchone()[0]
        activated_at = _now()
        cursor = self.conn.execute(
            """
            INSERT INTO grain_scheme_versions
                (grain_type_code, harvest_year, revision, name, payload, activated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                draft.grain_type_code,
                draft.harvest_year,
                revision,
                draft.name,
                json.dumps(draft.payload, ensure_ascii=False),
                activated_at,
            ),
        )
        if commit:
            self.conn.commit()
        return GrainSchemeVersionRecord(
            id=cursor.lastrowid,
            grain_type_code=draft.grain_type_code,
            harvest_year=draft.harvest_year,
            revision=revision,
            name=draft.name,
            payload=dict(draft.payload),
            activated_at=activated_at,
        )

    def list_versions(
        self,
        grain_type_code: str,
        harvest_year: int,
    ) -> tuple[GrainSchemeVersionRecord, ...]:
        rows = self.conn.execute(
            """
            SELECT id, revision, name, payload, activated_at
            FROM grain_scheme_versions
            WHERE grain_type_code = ? AND harvest_year = ?
            ORDER BY revision DESC
            """,
            (grain_type_code, harvest_year),
        ).fetchall()
        return tuple(
            GrainSchemeVersionRecord(
                id=row[0],
                grain_type_code=grain_type_code,
                harvest_year=harvest_year,
                revision=row[1],
                name=row[2],
                payload=json.loads(row[3]),
                activated_at=row[4],
            )
            for row in rows
        )
