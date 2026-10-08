import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from rechnungshelfer.repositories.database import Database
from rechnungshelfer.repositories.migrations import (
    MIGRATIONS,
    SCHEMA_VERSION,
    DatabaseMigrationError,
    UnsupportedDatabaseVersion,
    migrate_database,
)


class DatabaseMigrationTests(unittest.TestCase):
    @staticmethod
    def _create_version_one_database(path: Path, payload: dict | None = None) -> None:
        connection = sqlite3.connect(path)
        try:
            MIGRATIONS[0](connection)
            if payload is not None:
                connection.execute(
                    "INSERT INTO invoices VALUES (?, ?, ?)",
                    ("ALT-1", json.dumps(payload), "2025-01-01T00:00:00+00:00"),
                )
            connection.execute("PRAGMA user_version=1")
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _legacy_invoice_payload() -> dict:
        return {
            "seller": {"name": "Lieferant", "supplier_number": "L0010"},
            "buyer": {"name": "Altkunde", "customer_number": "K0042"},
            "info": {"invoice_number": "ALT-1", "invoice_date": "01.01.2025"},
            "monetarytotal": {"payable_amount": "119.00"},
        }

    def test_fresh_database_runs_all_migrations_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fresh.db"
            database = Database(path)
            try:
                version = database.connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
                tables = {
                    row[0]
                    for row in database.connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            finally:
                database.close()

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertTrue(
                {
                    "invoices",
                    "customers",
                    "suppliers",
                    "grain_scheme_drafts",
                    "grain_scheme_versions",
                }
                <= tables
            )
            self.assertEqual(list(Path(tmp).glob("*.backup-*.db")), [])

    def test_version_one_is_migrated_and_summary_data_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.db"
            self._create_version_one_database(path, self._legacy_invoice_payload())

            database = Database(path)
            try:
                row = database.connection.execute(
                    """
                    SELECT document_type, counterparty_name, buyer_name,
                           customer_number, supplier_number, invoice_date,
                           payable_amount
                    FROM invoices WHERE invoice_number = 'ALT-1'
                    """
                ).fetchone()
                version = database.connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
            finally:
                database.close()

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertEqual(
                row,
                (
                    "invoice",
                    "Altkunde",
                    "Altkunde",
                    "K0042",
                    "L0010",
                    "01.01.2025",
                    "119.00",
                ),
            )
            self.assertEqual(len(list(Path(tmp).glob("legacy.backup-v1-*.db"))), 1)

    def test_version_zero_runs_each_intermediate_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "version-zero.db"
            self._create_version_one_database(path, self._legacy_invoice_payload())
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA user_version=0")
            connection.commit()
            connection.close()

            database = Database(path)
            try:
                row = database.connection.execute(
                    """
                    SELECT counterparty_name, payable_amount
                    FROM invoices WHERE invoice_number = 'ALT-1'
                    """
                ).fetchone()
                version = database.connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
            finally:
                database.close()

            self.assertEqual(row, ("Altkunde", "119.00"))
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertEqual(
                len(list(Path(tmp).glob("version-zero.backup-v0-*.db"))),
                1,
            )

    def test_current_database_is_reopened_without_another_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "current.db"
            database = Database(path)
            database.close()
            database = Database(path)
            database.close()

            self.assertEqual(list(Path(tmp).glob("current.backup-*.db")), [])

    def test_newer_database_version_is_rejected_without_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "future.db"
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA user_version=99")
            connection.commit()
            connection.close()

            with self.assertRaisesRegex(
                UnsupportedDatabaseVersion,
                "Schema-Version 99",
            ):
                Database(path)

            check = sqlite3.connect(path)
            try:
                self.assertEqual(
                    check.execute("PRAGMA user_version").fetchone()[0],
                    99,
                )
                self.assertEqual(
                    check.execute("PRAGMA journal_mode").fetchone()[0],
                    "delete",
                )
            finally:
                check.close()
            self.assertEqual(list(Path(tmp).glob("future.backup-*.db")), [])

    def test_failed_migration_rolls_back_schema_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.db"
            self._create_version_one_database(path)
            connection = sqlite3.connect(path)

            def failing_migration(active_connection: sqlite3.Connection) -> None:
                active_connection.execute(
                    "ALTER TABLE invoices ADD COLUMN must_disappear TEXT"
                )
                raise RuntimeError("simulierter Fehler")

            try:
                with self.assertRaisesRegex(
                    DatabaseMigrationError,
                    "Schema-Version 1",
                ):
                    migrate_database(
                        connection,
                        migrations={1: failing_migration, 2: MIGRATIONS[2]},
                    )

                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(invoices)"
                    ).fetchall()
                }
                version = connection.execute("PRAGMA user_version").fetchone()[0]
            finally:
                connection.close()

            self.assertNotIn("must_disappear", columns)
            self.assertEqual(version, 1)


if __name__ == "__main__":
    unittest.main()
