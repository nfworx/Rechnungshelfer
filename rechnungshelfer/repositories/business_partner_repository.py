"""Gemeinsame Persistenz fuer Kunden- und Lieferantenrollen."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rechnungshelfer.domain.business_partner import (
    BusinessPartnerRole,
    normalize_partner_number,
)
from rechnungshelfer.domain.models import Buyer, Payment, Seller
from rechnungshelfer.repositories.database import open_database


COMMON_FIELDS = (
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
CUSTOMER_FIELDS = ("leitweg_id", "use_invoice_address_as_delivery")
SUPPLIER_FIELDS = ("buyer_reference",)


class BusinessPartnerRepository:
    def __init__(
        self,
        db_path: Path | None = None,
        connection: sqlite3.Connection | None = None,
    ):
        self._owns_connection = connection is None
        self.conn = connection or open_database(db_path)

    def save_customer(self, buyer: Buyer, *, commit: bool = True) -> str:
        if commit:
            with self.conn:
                return self.save_customer(buyer, commit=False)
        number = normalize_partner_number(buyer.customer_number)
        self._save_partner(number, buyer)
        self._save_role(
            number,
            BusinessPartnerRole.CUSTOMER,
            {field: getattr(buyer, field) for field in CUSTOMER_FIELDS},
        )
        buyer.customer_number = number
        return number

    def save_supplier(
        self,
        seller: Seller,
        payment: Payment,
        *,
        commit: bool = True,
    ) -> str:
        if commit:
            with self.conn:
                return self.save_supplier(seller, payment, commit=False)
        number = normalize_partner_number(seller.supplier_number)
        self._save_partner(number, seller)
        role_data = {field: getattr(seller, field) for field in SUPPLIER_FIELDS}
        role_data["payment"] = dict(payment.__dict__)
        self._save_role(number, BusinessPartnerRole.SUPPLIER, role_data)
        seller.supplier_number = number
        return number

    def _save_partner(self, number: str, party) -> None:
        if not str(getattr(party, "name", "") or "").strip():
            raise ValueError("Name des Geschaeftspartners fehlt.")

        common_data = self._merged_common_data(number, party)
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
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
                common_data["name"],
                json.dumps(common_data, ensure_ascii=False),
                now,
            ),
        )

    def _merged_common_data(self, number: str, party) -> dict:
        row = self.conn.execute(
            "SELECT common_data FROM business_partners WHERE partner_number = ?",
            (number,),
        ).fetchone()
        common = json.loads(row[0]) if row else {}
        for field in COMMON_FIELDS:
            value = getattr(party, field, "")
            # Das automatische Speichern eines Belegs darf bereits gepflegte
            # Partnerdaten nicht durch in diesem Formular ausgeblendete Leerwerte
            # loeschen. Bewusstes Leeren erfolgt spaeter im Partnereditor.
            if value not in (None, "") or field not in common:
                common[field] = value
        return common

    def _save_role(
        self,
        number: str,
        role: BusinessPartnerRole,
        role_data: dict,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO business_partner_roles
                (partner_number, role, role_data, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(partner_number, role) DO UPDATE SET
                role_data = excluded.role_data,
                updated_at = excluded.updated_at
            """,
            (
                number,
                role.value,
                json.dumps(role_data, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def list_customers(self) -> list[Buyer]:
        return [
            self._row_to_customer(row)
            for row in self._role_rows(BusinessPartnerRole.CUSTOMER)
        ]

    def list_suppliers(self) -> list[tuple[Seller, Payment]]:
        return [
            self._row_to_supplier(row)
            for row in self._role_rows(BusinessPartnerRole.SUPPLIER)
        ]

    def _role_rows(self, role: BusinessPartnerRole):
        return self.conn.execute(
            """
            SELECT p.partner_number, p.common_data, r.role_data
            FROM business_partners AS p
            JOIN business_partner_roles AS r
              ON r.partner_number = p.partner_number
            WHERE r.role = ?
            ORDER BY p.name COLLATE NOCASE, p.partner_number
            """,
            (role.value,),
        ).fetchall()

    @staticmethod
    def _row_to_customer(row) -> Buyer:
        number, common_json, role_json = row
        values = json.loads(common_json)
        values.update(json.loads(role_json))
        values["customer_number"] = number
        return Buyer(**_constructor_values(Buyer, values))

    @staticmethod
    def _row_to_supplier(row) -> tuple[Seller, Payment]:
        number, common_json, role_json = row
        values = json.loads(common_json)
        role_data = json.loads(role_json)
        values.update({field: role_data.get(field, "") for field in SUPPLIER_FIELDS})
        values["supplier_number"] = number
        payment_data = role_data.get("payment", {})
        return (
            Seller(**_constructor_values(Seller, values)),
            Payment(**_constructor_values(Payment, payment_data)),
        )

    def search_customers(self, field: str, query: str, *, limit: int = 10):
        query = str(query or "").strip().casefold()
        if not query:
            return []
        allowed = {
            "name",
            "customer_number",
            "city",
            "postcode",
            "email",
            "leitweg_id",
            "contact_name",
            "phone",
            "vat",
            "tax_number",
            "registry_number",
        }
        if field not in allowed:
            return []
        return [
            customer
            for customer in self.list_customers()
            if query in str(getattr(customer, field, "") or "").casefold()
        ][:limit]

    def find_customer_duplicates(self, buyer: Buyer) -> list[Buyer]:
        duplicates = []
        for existing in self.list_customers():
            same_number = bool(
                buyer.customer_number
                and existing.customer_number == buyer.customer_number
            )
            same_email = _same_nonempty(buyer.email, existing.email)
            same_leitweg = _same_nonempty(buyer.leitweg_id, existing.leitweg_id)
            same_name_city = (
                _same_nonempty(buyer.name, existing.name)
                and _same_nonempty(buyer.city, existing.city)
            )
            if same_number or same_email or same_leitweg or same_name_city:
                duplicates.append(existing)
        return duplicates

    def delete_customer(self, partner_number: str) -> None:
        self._delete_role(partner_number, BusinessPartnerRole.CUSTOMER)

    def delete_supplier(self, partner_number: str) -> None:
        self._delete_role(partner_number, BusinessPartnerRole.SUPPLIER)

    def _delete_role(self, partner_number: str, role: BusinessPartnerRole) -> None:
        number = normalize_partner_number(partner_number)
        with self.conn:
            self.conn.execute(
                "DELETE FROM business_partner_roles WHERE partner_number = ? AND role = ?",
                (number, role.value),
            )
            self.conn.execute(
                """
                DELETE FROM business_partners
                WHERE partner_number = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM business_partner_roles
                      WHERE partner_number = ?
                  )
                """,
                (number, number),
            )

    def close(self) -> None:
        if self._owns_connection:
            self.conn.close()


def _constructor_values(model_type, values: dict) -> dict:
    code = model_type.__init__.__code__
    fields = code.co_varnames[1 : code.co_argcount]
    return {field: values[field] for field in fields if field in values}


def _same_nonempty(first, second) -> bool:
    return bool(
        first
        and second
        and str(first).strip().casefold() == str(second).strip().casefold()
    )
