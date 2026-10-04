# rechnungshelfer/repositories/invoice_repository.py
import sqlite3
import json
from datetime import datetime, timezone
from rechnungshelfer.domain.models import Invoice
from pathlib import Path

from rechnungshelfer.repositories.database import (
    get_data_dir,
    get_db_path,
    get_exe_dir,
    open_database,
)
from rechnungshelfer.repositories.invoice_record import invoice_summary_from_data
from rechnungshelfer.repositories.migrations import SCHEMA_VERSION

class InvoiceRepository:
    def __init__(
        self,
        db_path: Path | None = None,
        connection: sqlite3.Connection | None = None,
    ):
        self._owns_connection = connection is None
        self.conn = connection or open_database(db_path)

    def save(self, invoice: Invoice, commit: bool = True):
        invoice_number = invoice.info.invoice_number
        if not invoice_number:
            raise ValueError("Invoice number fehlt")

        invoice_data = invoice.to_dict()
        data_json = json.dumps(invoice_data, ensure_ascii=False)
        summary = invoice_summary_from_data(invoice_data)

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
