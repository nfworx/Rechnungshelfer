#invoice_repository.py
import sqlite3
import json
import os
from datetime import datetime, timezone
from models import Invoice, Buyer
import sys
from pathlib import Path

from app_info import DATA_DIR_ENV


SCHEMA_VERSION = 2

def get_exe_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    data_dir = Path(override) if override else get_exe_dir() / "data"

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path() -> Path:
    return get_data_dir() / "invoices.db"

class InvoiceRepository:
    def __init__(
        self,
        db_path: Path | None = None,
        connection: sqlite3.Connection | None = None,
    ):
        if db_path is None:
            db_path = get_db_path()

        self._owns_connection = connection is None
        self.conn = connection or sqlite3.connect(db_path, timeout=10)
        self.conn.execute("PRAGMA busy_timeout=10000;")
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self._create_table()
        self.buyers: list[Buyer] = []

    def _create_table(self):
        current_version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version < SCHEMA_VERSION:
            self._backup_before_migration(current_version)

        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_number TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                document_type TEXT NOT NULL DEFAULT 'invoice',
                counterparty_name TEXT NOT NULL DEFAULT '',
                buyer_name TEXT NOT NULL DEFAULT '',
                customer_number TEXT NOT NULL DEFAULT '',
                supplier_number TEXT NOT NULL DEFAULT '',
                invoice_date TEXT NOT NULL DEFAULT '',
                payable_amount TEXT NOT NULL DEFAULT '0.00'
            );
            CREATE TABLE IF NOT EXISTS customers (
                customer_number TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS suppliers (
                supplier_number TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                seller_data TEXT NOT NULL,
                payment_data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        self._ensure_summary_columns()
        if current_version < 2:
            self._backfill_invoice_summaries()
        self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.conn.commit()

    def _ensure_summary_columns(self) -> None:
        existing = {
            row[1] for row in self.conn.execute("PRAGMA table_info(invoices)").fetchall()
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
                self.conn.execute(
                    f"ALTER TABLE invoices ADD COLUMN {column} {definition}"
                )

    @staticmethod
    def _summary_from_data(data: dict) -> dict:
        buyer = data.get("buyer", {})
        seller = data.get("seller", {})
        info = data.get("info", {})
        monetarytotal = data.get("monetarytotal", {})
        invoice_type_code = str(info.get("invoice_type_code", "380"))
        document_type = data.get("document_type") or (
            "self_billed_invoice" if invoice_type_code == "389" else "invoice"
        )
        counterparty = seller if document_type == "self_billed_invoice" else buyer
        return {
            "document_type": document_type,
            "counterparty_name": counterparty.get("name", ""),
            "buyer_name": buyer.get("name", ""),
            "customer_number": buyer.get("customer_number", ""),
            "supplier_number": seller.get("supplier_number", ""),
            "invoice_date": info.get("invoice_date", ""),
            "payable_amount": monetarytotal.get("payable_amount") or "0.00",
        }

    def _backfill_invoice_summaries(self) -> None:
        rows = self.conn.execute("SELECT invoice_number, data FROM invoices").fetchall()
        for invoice_number, data_json in rows:
            summary = self._summary_from_data(json.loads(data_json))
            self.conn.execute(
                """
                UPDATE invoices SET
                    document_type = ?, counterparty_name = ?, buyer_name = ?,
                    customer_number = ?, supplier_number = ?, invoice_date = ?,
                    payable_amount = ?
                WHERE invoice_number = ?
                """,
                (*summary.values(), invoice_number),
            )

    def _backup_before_migration(self, current_version: int) -> None:
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
        ).fetchone()
        if row is None:
            return

        db_row = self.conn.execute("PRAGMA database_list").fetchone()
        if not db_row or not db_row[2] or db_row[2] == ":memory:":
            return

        source = Path(db_row[2])
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = source.with_name(
            f"{source.stem}.backup-v{current_version}-{timestamp}{source.suffix}"
        )
        backup_conn = sqlite3.connect(backup)
        try:
            self.conn.backup(backup_conn)
        finally:
            backup_conn.close()

    def save(self, invoice: Invoice, commit: bool = True):
        invoice_number = invoice.info.invoice_number
        if not invoice_number:
            raise ValueError("Invoice number fehlt")

        invoice_data = invoice.to_dict()
        data_json = json.dumps(invoice_data, ensure_ascii=False)
        summary = self._summary_from_data(invoice_data)

        self.conn.execute("""
            INSERT INTO invoices
            (invoice_number, data, created_at, document_type, counterparty_name,
             buyer_name, customer_number, supplier_number, invoice_date, payable_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(invoice_number) DO UPDATE SET
                data = excluded.data,
                created_at = excluded.created_at,
                document_type = excluded.document_type,
                counterparty_name = excluded.counterparty_name,
                buyer_name = excluded.buyer_name,
                customer_number = excluded.customer_number,
                supplier_number = excluded.supplier_number,
                invoice_date = excluded.invoice_date,
                payable_amount = excluded.payable_amount
            """, (
            invoice_number,
            data_json,
            datetime.now(timezone.utc).isoformat(),
            summary["document_type"],
            summary["counterparty_name"],
            summary["buyer_name"],
            summary["customer_number"],
            summary["supplier_number"],
            summary["invoice_date"],
            summary["payable_amount"],
        ))
        if commit:
            self.conn.commit()

    def load(self, invoice_number: str) -> Invoice | None:
        cursor = self.conn.execute(
            "SELECT data FROM invoices WHERE invoice_number = ?",
            (invoice_number,)
        )
        row = cursor.fetchone()
        if row is None:
            return None

        data = json.loads(row[0])
        return Invoice.from_dict(data)

    def list_invoice_numbers(self):
        cursor = self.conn.execute(
            "SELECT invoice_number FROM invoices ORDER BY created_at DESC"
        )
        return [row[0] for row in cursor.fetchall()]
    
    def delete(self, invoice_number: str):
        invoice_number = invoice_number.strip()
        cur = self.conn.cursor()
        cur.execute(
            "DELETE FROM invoices WHERE invoice_number = ?",
            (invoice_number,)
        )
        if cur.rowcount == 0:
            raise KeyError(f"Rechnung nicht gefunden: {invoice_number}")
        self.conn.commit()

    def exists(self, invoice_number: str) -> bool:
        invoice_number = invoice_number.strip()
        cur = self.conn.execute(
            "SELECT 1 FROM invoices WHERE invoice_number = ?",
            (invoice_number,)
        )
        return cur.fetchone() is not None
    
    def close(self):
        if self._owns_connection:
            self.conn.close()

    def load_latest(self) -> Invoice | None:
        cur = self.conn.execute(
            """
            SELECT data
            FROM invoices
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row is None:
            return None

        data = json.loads(row[0])
        return Invoice.from_dict(data)
    
    def add_customer(self, buyer: Buyer):
        # Prüfen, ob Kunde schon existiert (z.B. über leitweg_id oder name)
        if not any(b.leitweg_id == buyer.leitweg_id for b in self.buyers):
            self.buyers.append(buyer)

    def list_customers(self):
        return self.buyers

    # Optional: Kunden aus gespeicherten Rechnungen laden
    def load_customers_from_invoices(self):
        cursor = self.conn.execute("SELECT data FROM invoices")
        for row in cursor.fetchall():
            invoice_data = json.loads(row[0])
            buyer_data = invoice_data.get("buyer", {})
            buyer_params = {k: buyer_data.get(k) for k in Buyer.__init__.__code__.co_varnames[1:]}
            buyer = Buyer(**buyer_params)
            self.add_customer(buyer)

    def list_invoice_summaries(self):
        """
        Gibt eine schnelle Liste von Rechnungszusammenfassungen zurück.
        Verwendet die gespeicherten payable_amount Werte direkt, ohne neu zu berechnen.
        """
        cursor = self.conn.execute(
            """
            SELECT invoice_number, document_type, counterparty_name, buyer_name,
                   customer_number, supplier_number, invoice_date, created_at,
                   payable_amount
            FROM invoices
            ORDER BY created_at DESC
            """
        )

        summaries = []

        for row in cursor.fetchall():
            (
                invoice_number, document_type, counterparty_name, buyer_name,
                customer_number, supplier_number, invoice_date, created_at,
                payable_amount,
            ) = row
            summaries.append({
                "invoice_number": invoice_number,
                "buyer_name": buyer_name,
                "counterparty_name": counterparty_name,
                "customer_number": customer_number,
                "supplier_number": supplier_number,
                "document_type": document_type,
                "invoice_date": invoice_date,
                "created_at": created_at,
                "payable_amount": payable_amount,
            })

        return summaries
