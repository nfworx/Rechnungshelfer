import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rechnungshelfer.domain.models import Payment, Seller
from repositories.invoice_repository import get_db_path


class SupplierRepository:
    def __init__(
        self,
        db_path: Path | None = None,
        connection: sqlite3.Connection | None = None,
    ):
        self._owns_connection = connection is None
        self.conn = connection or sqlite3.connect(db_path or get_db_path(), timeout=10)
        self.conn.execute("PRAGMA busy_timeout=10000;")
        self._create_table()

    def _create_table(self):
        self.conn.execute(
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
        self.conn.commit()

    def next_supplier_number(self) -> str:
        rows = self.conn.execute(
            "SELECT supplier_number FROM suppliers WHERE supplier_number GLOB 'L[0-9]*'"
        ).fetchall()
        numbers = [
            int(row[0][1:])
            for row in rows
            if row[0][1:].isdigit()
        ]
        return f"L{(max(numbers, default=0) + 1):04d}"

    def save(self, seller: Seller, payment: Payment, commit: bool = True):
        if not seller.name:
            raise ValueError("Name des Lieferanten fehlt.")
        if not seller.supplier_number:
            seller.supplier_number = self.next_supplier_number()

        self.conn.execute(
            """
            INSERT INTO suppliers
            (supplier_number, name, seller_data, payment_data, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(supplier_number) DO UPDATE SET
                name = excluded.name,
                seller_data = excluded.seller_data,
                payment_data = excluded.payment_data,
                updated_at = excluded.updated_at
            """,
            (
                seller.supplier_number,
                seller.name,
                json.dumps(seller.__dict__, ensure_ascii=False),
                json.dumps(payment.__dict__, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        if commit:
            self.conn.commit()
        return seller.supplier_number

    def list_suppliers(self):
        rows = self.conn.execute(
            "SELECT seller_data, payment_data FROM suppliers ORDER BY name"
        ).fetchall()
        return [self._row_to_models(row) for row in rows]

    def delete(self, supplier_number: str):
        self.conn.execute(
            "DELETE FROM suppliers WHERE supplier_number = ?",
            (supplier_number,),
        )
        self.conn.commit()

    @staticmethod
    def _row_to_models(row):
        seller_data = json.loads(row[0])
        payment_data = json.loads(row[1])
        seller_fields = Seller.__init__.__code__.co_varnames[1:Seller.__init__.__code__.co_argcount]
        payment_fields = Payment.__init__.__code__.co_varnames[1:Payment.__init__.__code__.co_argcount]
        seller = Seller(**{key: seller_data[key] for key in seller_fields if key in seller_data})
        payment = Payment(**{key: payment_data[key] for key in payment_fields if key in payment_data})
        return seller, payment

    def close(self):
        if self._owns_connection:
            self.conn.close()
