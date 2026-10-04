import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from models import Buyer
from repositories.invoice_repository import get_db_path



class CustomerRepository:
    def __init__(
        self,
        db_path: Path | None = None,
        connection: sqlite3.Connection | None = None,
    ):
        if db_path is None:
            db_path = get_db_path()  # Standard DB-Pfad
        self._owns_connection = connection is None
        self.conn = connection or sqlite3.connect(db_path, timeout=10)
        self.conn.execute("PRAGMA busy_timeout=10000;")
        self._create_table()

    def count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM customers")
        return cur.fetchone()[0]

    def next_customer_number(self) -> str:
        rows = self.conn.execute(
            "SELECT customer_number FROM customers WHERE customer_number GLOB 'K[0-9]*'"
        ).fetchall()
        numbers = [
            int(row[0][1:])
            for row in rows
            if row[0][1:].isdigit()
        ]
        return f"K{(max(numbers, default=0) + 1):04d}"

    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_number TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    # -----------------------
    # Kunden speichern
    # -----------------------
    def save(self, buyer: Buyer, commit: bool = True):
        """
        Speichert den kompletten Buyer als JSON in der Datenbank.
        """
        buyer_fields = Buyer.__init__.__code__.co_varnames[1:Buyer.__init__.__code__.co_argcount]
        data_json = json.dumps(
            {field: getattr(buyer, field) for field in buyer_fields},
            ensure_ascii=False,
        )

        self.conn.execute("""
            INSERT INTO customers
            (customer_number, name, data, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(customer_number) DO UPDATE SET
                name = excluded.name,
                data = excluded.data,
                updated_at = excluded.updated_at
        """, (
            buyer.customer_number,
            buyer.name,
            data_json,
            datetime.now(timezone.utc).isoformat()
        ))
        if commit:
            self.conn.commit()

    # -----------------------
    # Kunden suchen
    # -----------------------
    def search_by_name(self, query: str, limit=10):
        cur = self.conn.execute(
            """
            SELECT data
            FROM customers
            WHERE name LIKE ?
            ORDER BY name
            LIMIT ?
            """,
            (f"%{query}%", limit)
        )
        return [self._row_to_buyer(row) for row in cur.fetchall()]

    def search(self, field: str, query: str, limit: int = 10):
        query = str(query or "").strip()
        if not query:
            return []

        direct_columns = {
            "name": "name",
            "customer_number": "customer_number",
        }
        json_fields = {
            "city", "postcode", "email", "leitweg_id", "contact_name",
            "phone", "vat", "tax_number", "registry_number",
        }
        pattern = f"%{query}%"

        if field in direct_columns:
            column = direct_columns[field]
            cur = self.conn.execute(
                f"SELECT data FROM customers WHERE {column} LIKE ? ORDER BY name LIMIT ?",
                (pattern, limit),
            )
        elif field in json_fields:
            cur = self.conn.execute(
                """
                SELECT data FROM customers
                WHERE json_extract(data, ?) LIKE ?
                ORDER BY name
                LIMIT ?
                """,
                (f"$.{field}", pattern, limit),
            )
        else:
            return []

        return [self._row_to_buyer(row) for row in cur.fetchall()]

    # -----------------------
    # Alle Kunden auflisten
    # -----------------------
    def list_customers(self):
        cur = self.conn.execute("SELECT data FROM customers ORDER BY name ASC")
        return [self._row_to_buyer(row) for row in cur.fetchall()]
    
    # -----------------------
    # Kunde löschen
    # -----------------------
    def delete(self, customer_number: str):
        self.conn.execute(
            "DELETE FROM customers WHERE customer_number = ?",
            (customer_number,),
        )
        self.conn.commit()

    # -----------------------
    # Helfer: JSON zu Buyer
    # -----------------------
    def _row_to_buyer(self, row):
        data = json.loads(row[0])
        buyer_fields = Buyer.__init__.__code__.co_varnames[1:Buyer.__init__.__code__.co_argcount]
        return Buyer(**{field: data[field] for field in buyer_fields if field in data})

    # -----------------------
    # DB schließen
    # -----------------------
    def close(self):
        if self._owns_connection:
            self.conn.close()

    def find_duplicates(self, buyer: Buyer):
        cur = self.conn.execute("SELECT data FROM customers")
        duplicates = []

        for row in cur.fetchall():
            existing = self._row_to_buyer(row)

            same_number = (
                buyer.customer_number
                and existing.customer_number == buyer.customer_number
            )

            same_email = (
                buyer.email
                and existing.email
                and existing.email.lower() == buyer.email.lower()
            )

            same_leitweg = (
                buyer.leitweg_id
                and existing.leitweg_id
                and existing.leitweg_id == buyer.leitweg_id
            )

            same_name_city = (
                buyer.name
                and existing.name
                and buyer.city
                and existing.city
                and existing.name.lower() == buyer.name.lower()
                and existing.city.lower() == buyer.city.lower()
            )

            if same_number or same_email or same_leitweg or same_name_city:
                duplicates.append(existing)

        return duplicates
