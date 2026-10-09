"""Sequenzielle, transaktionale Migrationen der SQLite-Datenbank."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from .invoice_record import invoice_summary_from_data


SCHEMA_VERSION = 6
Migration = Callable[[sqlite3.Connection], None]


class DatabaseMigrationError(RuntimeError):
    """Eine Schemamigration konnte nicht vollständig ausgeführt werden."""

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        backup_path: Path | None = None,
    ):
        super().__init__(message)
        self.user_message = user_message or message
        self.backup_path = backup_path


class UnsupportedDatabaseVersion(DatabaseMigrationError):
    """Die Datenbank stammt aus einer neueren, nicht unterstützten Version."""


class MigrationDataConflict(ValueError):
    """Bestandsdaten lassen sich nicht ohne Benutzerentscheidung migrieren."""

    def __init__(self, technical_message: str, user_message: str):
        super().__init__(technical_message)
        self.user_message = user_message


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


def _migration_2_to_3(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE grain_scheme_drafts (
            grain_type_code TEXT NOT NULL,
            harvest_year INTEGER NOT NULL,
            name TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (grain_type_code, harvest_year)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE grain_scheme_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grain_type_code TEXT NOT NULL,
            harvest_year INTEGER NOT NULL,
            revision INTEGER NOT NULL,
            name TEXT NOT NULL,
            payload TEXT NOT NULL,
            activated_at TEXT NOT NULL,
            UNIQUE (grain_type_code, harvest_year, revision)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_grain_scheme_versions_lookup
        ON grain_scheme_versions (grain_type_code, harvest_year, revision DESC)
        """
    )


_PARTNER_COMMON_FIELDS = (
    "name",
    "street",
    "postcode",
    "city",
    "country",
    "phone",
    "email",
    "vat",
    "tax_number",
    "registry_number",
    "contact_name",
)


def _migration_3_to_4(connection: sqlite3.Connection) -> None:
    """Fuehrt Kunden und Lieferanten ohne Praefix-Aliase zusammen."""

    connection.execute(
        """
        CREATE TABLE business_partners (
            partner_number TEXT PRIMARY KEY
                CHECK (
                    partner_number <> ''
                    AND partner_number NOT GLOB '*[^0-9]*'
                ),
            name TEXT NOT NULL,
            common_data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE business_partner_roles (
            partner_number TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('customer', 'supplier')),
            role_data TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (partner_number, role),
            FOREIGN KEY (partner_number)
                REFERENCES business_partners(partner_number)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_business_partner_roles_role
        ON business_partner_roles (role, partner_number)
        """
    )

    for number, data_json, updated_at in connection.execute(
        "SELECT customer_number, data, updated_at FROM customers"
    ).fetchall():
        data = json.loads(data_json)
        _migrate_partner_role(
            connection,
            number=number,
            common_data=data,
            role="customer",
            role_data={
                "leitweg_id": data.get("leitweg_id", ""),
                "use_invoice_address_as_delivery": data.get(
                    "use_invoice_address_as_delivery",
                    False,
                ),
            },
            updated_at=updated_at,
        )

    for number, seller_json, payment_json, updated_at in connection.execute(
        """
        SELECT supplier_number, seller_data, payment_data, updated_at
        FROM suppliers
        """
    ).fetchall():
        seller_data = json.loads(seller_json)
        _migrate_partner_role(
            connection,
            number=number,
            common_data=seller_data,
            role="supplier",
            role_data={
                "buyer_reference": seller_data.get("buyer_reference", ""),
                "payment": json.loads(payment_json),
            },
            updated_at=updated_at,
        )

    connection.execute("DROP TABLE customers")
    connection.execute("DROP TABLE suppliers")


def _migrate_partner_role(
    connection: sqlite3.Connection,
    *,
    number,
    common_data: dict,
    role: str,
    role_data: dict,
    updated_at: str,
) -> None:
    number = _normalize_migrated_partner_number(number)

    incoming = {
        field: common_data.get(field, "")
        for field in _PARTNER_COMMON_FIELDS
    }
    existing_row = connection.execute(
        "SELECT common_data FROM business_partners WHERE partner_number = ?",
        (number,),
    ).fetchone()
    if existing_row:
        existing = json.loads(existing_row[0])
        conflicts = [
            field
            for field in _PARTNER_COMMON_FIELDS
            if existing.get(field) not in (None, "")
            and incoming.get(field) not in (None, "")
            and existing[field] != incoming[field]
        ]
        if conflicts:
            raise MigrationDataConflict(
                f"Kunde und Lieferant {number} besitzen widersprüchliche "
                "Stammdaten.",
                f"Geschäftspartnernummer {number} ist mehrfach mit "
                "unterschiedlichen Stammdaten belegt. Bitte korrigieren Sie "
                "die betreffenden Kunden/Lieferanten vor dem Update.",
            )
        common = {
            field: incoming.get(field) or existing.get(field, "")
            for field in _PARTNER_COMMON_FIELDS
        }
    else:
        common = incoming

    connection.execute(
        """
        INSERT INTO business_partners
            (partner_number, name, common_data, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(partner_number) DO UPDATE SET
            name = excluded.name,
            common_data = excluded.common_data,
            updated_at = excluded.updated_at
        """,
        (
            number,
            common.get("name", ""),
            json.dumps(common, ensure_ascii=False),
            updated_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO business_partner_roles
            (partner_number, role, role_data, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            number,
            role,
            json.dumps(role_data, ensure_ascii=False),
            updated_at,
        ),
    )


def _normalize_migrated_partner_number(value) -> str:
    """Normalisiert ausschliesslich die frueher automatisch erzeugten Praefixe."""

    number = str(value or "").strip()
    if number and number.isascii() and number.isdigit():
        return number
    if len(number) > 1 and number[0] in ("K", "L"):
        numeric_part = number[1:]
        if numeric_part.startswith("-"):
            numeric_part = numeric_part[1:]
        if numeric_part and numeric_part.isascii() and numeric_part.isdigit():
            return numeric_part
    shown_number = number or "<leer>"
    raise MigrationDataConflict(
        "Geschäftspartnernummer ist nicht eindeutig migrierbar: "
        f"{shown_number}",
        f"Die Geschäftspartnernummer {shown_number} kann nicht automatisch "
        "in eine rein numerische Nummer umgewandelt werden. Bitte korrigieren "
        "Sie diesen Kunden/Lieferanten vor dem Update.",
    )


def _migration_4_to_5(connection: sqlite3.Connection) -> None:
    """Entkoppelt die interne Partneridentität von der sichtbaren Nummer."""

    connection.execute(
        """
        CREATE TABLE business_partners_v5 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_number TEXT NOT NULL UNIQUE
                CHECK (
                    partner_number <> ''
                    AND partner_number NOT GLOB '*[^0-9]*'
                ),
            name TEXT NOT NULL,
            common_data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE business_partner_roles_v5 (
            partner_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('customer', 'supplier')),
            role_data TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (partner_id, role),
            FOREIGN KEY (partner_id)
                REFERENCES business_partners_v5(id)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        INSERT INTO business_partners_v5
            (partner_number, name, common_data, updated_at)
        SELECT partner_number, name, common_data, updated_at
        FROM business_partners
        ORDER BY partner_number
        """
    )
    connection.execute(
        """
        INSERT INTO business_partner_roles_v5
            (partner_id, role, role_data, updated_at)
        SELECT p.id, r.role, r.role_data, r.updated_at
        FROM business_partner_roles AS r
        JOIN business_partners_v5 AS p
          ON p.partner_number = r.partner_number
        """
    )
    for partner_id, partner_number, role_data_json in connection.execute(
        """
        SELECT r.partner_id, p.partner_number, r.role_data
        FROM business_partner_roles_v5 AS r
        JOIN business_partners_v5 AS p ON p.id = r.partner_id
        WHERE r.role = 'supplier'
        """
    ).fetchall():
        role_data = json.loads(role_data_json)
        if str(role_data.get("buyer_reference") or "").strip().upper() in (
            "",
            "BUCHHALTUNG",
        ):
            role_data["buyer_reference"] = partner_number
            connection.execute(
                """
                UPDATE business_partner_roles_v5
                SET role_data = ?
                WHERE partner_id = ? AND role = 'supplier'
                """,
                (json.dumps(role_data, ensure_ascii=False), partner_id),
            )
    connection.execute("DROP TABLE business_partner_roles")
    connection.execute("DROP TABLE business_partners")
    connection.execute(
        "ALTER TABLE business_partners_v5 RENAME TO business_partners"
    )
    connection.execute(
        "ALTER TABLE business_partner_roles_v5 RENAME TO business_partner_roles"
    )
    connection.execute(
        """
        CREATE INDEX idx_business_partner_roles_role
        ON business_partner_roles (role, partner_id)
        """
    )


def _migration_5_to_6(connection: sqlite3.Connection) -> None:
    """Speichert ausschließlich bestätigte strukturierte Getreidebelege."""

    connection.execute(
        """
        CREATE TABLE grain_credit_notes (
            credit_note_number TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            credit_note_date TEXT NOT NULL,
            supplier_number TEXT NOT NULL DEFAULT '',
            supplier_name TEXT NOT NULL DEFAULT '',
            credit_amount TEXT NOT NULL DEFAULT '0.00',
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_grain_credit_notes_updated
        ON grain_credit_notes (updated_at DESC)
        """
    )


MIGRATIONS: dict[int, Migration] = {
    0: _migration_0_to_1,
    1: _migration_1_to_2,
    2: _migration_2_to_3,
    3: _migration_3_to_4,
    4: _migration_4_to_5,
    5: _migration_5_to_6,
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
        error = DatabaseMigrationError(
            f"Datenbankmigration ab Schema-Version {current_version} fehlgeschlagen: "
            f"{exc}",
            user_message=getattr(exc, "user_message", None),
            backup_path=backup,
        )
        raise error from exc

    return backup
