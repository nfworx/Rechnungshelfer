"""Sequenzielle, transaktionale Migrationen der SQLite-Datenbank."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from .invoice_record import invoice_summary_from_data


SCHEMA_VERSION = 2
Migration = Callable[[sqlite3.Connection], None]


class DatabaseMigrationError(RuntimeError):
    """Eine Schemamigration konnte nicht vollständig ausgeführt werden."""


class UnsupportedDatabaseVersion(DatabaseMigrationError):
    """Die Datenbank stammt aus einer neueren, nicht unterstützten Version."""


def _migration_0_to_1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_number TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            customer_number TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_number TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            seller_data TEXT NOT NULL,
            payment_data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _migration_1_to_2(connection: sqlite3.Connection) -> None:
    existing = {
        row[1] for row in connection.execute("PRAGMA table_info(invoices)").fetchall()
    }
    definitions = {
        "document_type": "TEXT NOT NULL DEFAULT 'invoice'",
        "counterparty_name": "TEXT NOT NULL DEFAULT ''",
        "buyer_name": "TEXT NOT NULL DEFAULT ''",
        "customer_number": "TEXT NOT NULL DEFAULT ''",
        "supplier_number": "TEXT NOT NULL DEFAULT ''",
        "invoice_date": "TEXT NOT NULL DEFAULT ''",
        "payable_amount": "TEXT NOT NULL DEFAULT '0.00'",
    }
    for column, definition in definitions.items():
        if column not in existing:
            connection.execute(
                f"ALTER TABLE invoices ADD COLUMN {column} {definition}"
            )

    rows = connection.execute("SELECT invoice_number, data FROM invoices").fetchall()
    for invoice_number, data_json in rows:
        summary = invoice_summary_from_data(json.loads(data_json))
        connection.execute(
            """
            UPDATE invoices SET
                document_type = ?, counterparty_name = ?, buyer_name = ?,
                customer_number = ?, supplier_number = ?, invoice_date = ?,
                payable_amount = ?
            WHERE invoice_number = ?
            """,
            (
                summary["document_type"],
                summary["counterparty_name"],
                summary["buyer_name"],
                summary["customer_number"],
                summary["supplier_number"],
                summary["invoice_date"],
                summary["payable_amount"],
                invoice_number,
            ),
        )


MIGRATIONS: dict[int, Migration] = {
    0: _migration_0_to_1,
    1: _migration_1_to_2,
}


def _current_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _has_user_tables(connection: sqlite3.Connection) -> bool:
    return connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        LIMIT 1
        """
    ).fetchone() is not None


def _database_path(connection: sqlite3.Connection) -> Path | None:
    row = connection.execute("PRAGMA database_list").fetchone()
    if not row or not row[2] or row[2] == ":memory:":
        return None
    return Path(row[2])


def backup_before_migration(
    connection: sqlite3.Connection,
    current_version: int,
) -> Path | None:
    if not _has_user_tables(connection):
        return None

    source = _database_path(connection)
    if source is None:
        return None

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = source.with_name(
        f"{source.stem}.backup-v{current_version}-{timestamp}{source.suffix}"
    )
    backup_connection = sqlite3.connect(backup)
    try:
        connection.backup(backup_connection)
    finally:
        backup_connection.close()
    return backup


def migrate_database(
    connection: sqlite3.Connection,
    *,
    migrations: Mapping[int, Migration] | None = None,
) -> Path | None:
    """Migriert in Einzelschritten bis zur unterstützten Schema-Version."""
    current_version = _current_version(connection)
    if current_version > SCHEMA_VERSION:
        raise UnsupportedDatabaseVersion(
            "Die Datenbank verwendet Schema-Version "
            f"{current_version}; dieses Programm unterstützt höchstens "
            f"Version {SCHEMA_VERSION}."
        )
    if current_version == SCHEMA_VERSION:
        return None

    registry = MIGRATIONS if migrations is None else migrations
    missing = [
        version
        for version in range(current_version, SCHEMA_VERSION)
        if version not in registry
    ]
    if missing:
        raise DatabaseMigrationError(
            f"Migrationsschritt ab Schema-Version {missing[0]} fehlt."
        )

    try:
        backup = backup_before_migration(connection, current_version)
    except Exception as exc:
        raise DatabaseMigrationError(
            "Vor der Datenbankmigration konnte keine Sicherung erstellt werden."
        ) from exc

    try:
        connection.execute("BEGIN IMMEDIATE")
        version = current_version
        while version < SCHEMA_VERSION:
            registry[version](connection)
            version += 1
            connection.execute(f"PRAGMA user_version={version}")
        connection.commit()
    except Exception as exc:
        connection.rollback()
        raise DatabaseMigrationError(
            f"Datenbankmigration ab Schema-Version {current_version} fehlgeschlagen."
        ) from exc

    return backup
