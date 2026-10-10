"""Gemeinsame Persistenz fuer Kunden- und Lieferantenrollen."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rechnungshelfer.domain.business_partner import (
    BusinessPartnerProfile,
    BusinessPartnerRole,
    COMMON_PARTY_FIELDS,
    CUSTOMER_ROLE_FIELDS,
    SUPPLIER_ROLE_FIELDS,
    normalize_partner_number,
)
from rechnungshelfer.domain.models import Buyer, Payment, Seller
from rechnungshelfer.repositories.database import open_database


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
        partner_id = self._save_partner(number, buyer)
        self._save_role(
            partner_id,
            BusinessPartnerRole.CUSTOMER,
            {field: getattr(buyer, field) for field in CUSTOMER_ROLE_FIELDS},
        )
        buyer.customer_number = number
        return number

    def ensure_customer(self, buyer: Buyer, *, commit: bool = True) -> str:
        """Legt eine fehlende Kundenrolle an, ohne Stammdaten zu aktualisieren."""

        if commit:
            with self.conn:
                return self.ensure_customer(buyer, commit=False)
        number = normalize_partner_number(buyer.customer_number)
        profile = self.load_partner(number)
        if profile is None:
            return self.save_customer(buyer, commit=False)
        if BusinessPartnerRole.CUSTOMER not in profile.roles:
            self._save_role(
                self._partner_id(number),
                BusinessPartnerRole.CUSTOMER,
                {field: getattr(buyer, field) for field in CUSTOMER_ROLE_FIELDS},
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
        partner_id = self._save_partner(number, seller)
        if not str(seller.buyer_reference or "").strip():
            seller.buyer_reference = number
        role_data = {
            field: getattr(seller, field) for field in SUPPLIER_ROLE_FIELDS
        }
        role_data["payment"] = dict(payment.__dict__)
        self._save_role(partner_id, BusinessPartnerRole.SUPPLIER, role_data)
        seller.supplier_number = number
        return number

    def ensure_supplier(
        self,
        seller: Seller,
        payment: Payment,
        *,
        commit: bool = True,
    ) -> str:
        """Legt eine fehlende Lieferantenrolle an, ohne Stammdaten zu aktualisieren."""

        if commit:
            with self.conn:
                return self.ensure_supplier(seller, payment, commit=False)
        number = normalize_partner_number(seller.supplier_number)
        if not str(seller.buyer_reference or "").strip():
            seller.buyer_reference = number
        profile = self.load_partner(number)
        if profile is None:
            return self.save_supplier(seller, payment, commit=False)
        if BusinessPartnerRole.SUPPLIER not in profile.roles:
            role_data = {
                field: getattr(seller, field) for field in SUPPLIER_ROLE_FIELDS
            }
            role_data["payment"] = dict(payment.__dict__)
            self._save_role(
                self._partner_id(number),
                BusinessPartnerRole.SUPPLIER,
                role_data,
            )
        seller.supplier_number = number
        return number

    def _save_partner(self, number: str, party) -> int:
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
        return self._partner_id(number)

    def _partner_id(self, number: str) -> int:
        row = self.conn.execute(
            "SELECT id FROM business_partners WHERE partner_number = ?",
            (number,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Geschäftspartner nicht gefunden: {number}")
        return int(row[0])

    def _merged_common_data(self, number: str, party) -> dict:
        row = self.conn.execute(
            "SELECT common_data FROM business_partners WHERE partner_number = ?",
            (number,),
        ).fetchone()
        common = json.loads(row[0]) if row else {}
        for field in COMMON_PARTY_FIELDS:
            value = getattr(party, field, "")
            # Das automatische Speichern eines Belegs darf bereits gepflegte
            # Partnerdaten nicht durch in diesem Formular ausgeblendete Leerwerte
            # loeschen. Bewusstes Leeren erfolgt spaeter im Partnereditor.
            if value not in (None, "") or field not in common:
                common[field] = value
        return common

    def _save_role(
        self,
        partner_id: int,
        role: BusinessPartnerRole,
        role_data: dict,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO business_partner_roles
                (partner_id, role, role_data, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(partner_id, role) DO UPDATE SET
                role_data = excluded.role_data,
                updated_at = excluded.updated_at
            """,
            (
                partner_id,
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

    def list_partners(self) -> list[BusinessPartnerProfile]:
        rows = self.conn.execute(
            """
            SELECT id, partner_number, common_data
            FROM business_partners
            ORDER BY name COLLATE NOCASE, partner_number
            """
        ).fetchall()
        return [self._profile_from_row(*row) for row in rows]

    def load_partner(self, partner_number: str) -> BusinessPartnerProfile | None:
        number = normalize_partner_number(partner_number)
        row = self.conn.execute(
            """
            SELECT id, partner_number, common_data
            FROM business_partners
            WHERE partner_number = ?
            """,
            (number,),
        ).fetchone()
        if row is None:
            return None
        return self._profile_from_row(*row)

    def _profile_from_row(
        self,
        partner_id: int,
        number: str,
        common_json: str,
    ) -> BusinessPartnerProfile:
        common = json.loads(common_json)
        role_rows = self.conn.execute(
            """
            SELECT role, role_data
            FROM business_partner_roles
            WHERE partner_id = ?
            """,
            (partner_id,),
        ).fetchall()
        role_payloads = {role: json.loads(payload) for role, payload in role_rows}
        roles = frozenset(BusinessPartnerRole(role) for role in role_payloads)

        customer_values = dict(common)
        customer_values.update(role_payloads.get(BusinessPartnerRole.CUSTOMER.value, {}))
        customer_values["customer_number"] = number

        supplier_payload = role_payloads.get(BusinessPartnerRole.SUPPLIER.value, {})
        supplier_values = dict(common)
        supplier_values["buyer_reference"] = supplier_payload.get(
            "buyer_reference",
            "",
        )
        supplier_values["supplier_number"] = number
        payment_values = supplier_payload.get("payment", {})
        if BusinessPartnerRole.SUPPLIER not in roles:
            payment_values = {
                "iban": "",
                "bic": "",
                "account_holder": "",
                "payment_means_code": "58",
                "payment_terms": "",
            }

        return BusinessPartnerProfile(
            buyer=Buyer(**_constructor_values(Buyer, customer_values)),
            seller=Seller(**_constructor_values(Seller, supplier_values)),
            payment=Payment(**_constructor_values(Payment, payment_values)),
            roles=roles,
            partner_id=partner_id,
        )

    def save_partner(
        self,
        profile: BusinessPartnerProfile,
        *,
        commit: bool = True,
    ) -> str:
        if commit:
            with self.conn:
                return self.save_partner(profile, commit=False)
        if not profile.roles:
            raise ValueError("Ein Geschäftspartner benötigt mindestens eine Rolle.")

        number = normalize_partner_number(profile.partner_number)
        name = str(profile.buyer.name or profile.seller.name or "").strip()
        if not name:
            raise ValueError("Name des Geschäftspartners fehlt.")

        profile.buyer.customer_number = number
        profile.seller.supplier_number = number
        common_data = {
            field: getattr(profile.buyer, field, getattr(profile.seller, field, ""))
            for field in COMMON_PARTY_FIELDS
        }
        common_data["name"] = name
        now = datetime.now(timezone.utc).isoformat()
        previous_number = None
        if profile.partner_id is not None:
            previous_row = self.conn.execute(
                "SELECT partner_number FROM business_partners WHERE id = ?",
                (profile.partner_id,),
            ).fetchone()
            if previous_row is None:
                raise KeyError(
                    f"Geschäftspartner nicht gefunden: {profile.partner_id}"
                )
            previous_number = previous_row[0]
        try:
            if profile.partner_id is None:
                cursor = self.conn.execute(
                    """
                    INSERT INTO business_partners
                        (partner_number, name, common_data, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        number,
                        name,
                        json.dumps(common_data, ensure_ascii=False),
                        now,
                    ),
                )
                profile.partner_id = int(cursor.lastrowid)
            else:
                updated = self.conn.execute(
                    """
                    UPDATE business_partners SET
                        partner_number = ?, name = ?, common_data = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        number,
                        name,
                        json.dumps(common_data, ensure_ascii=False),
                        now,
                        profile.partner_id,
                    ),
                ).rowcount
                if not updated:
                    raise KeyError(
                        f"Geschäftspartner nicht gefunden: {profile.partner_id}"
                    )
        except sqlite3.IntegrityError as exc:
            if "partner_number" in str(exc):
                raise ValueError(
                    f"Geschäftspartnernummer {number} ist bereits vergeben."
                ) from exc
            raise

        partner_id = profile.partner_id

        selected_roles = {role.value for role in profile.roles}
        placeholders = ", ".join("?" for _ in selected_roles)
        self.conn.execute(
            f"""
            DELETE FROM business_partner_roles
            WHERE partner_id = ? AND role NOT IN ({placeholders})
            """,
            (partner_id, *sorted(selected_roles)),
        )
        if BusinessPartnerRole.CUSTOMER in profile.roles:
            self._save_role(
                partner_id,
                BusinessPartnerRole.CUSTOMER,
                {
                    field: getattr(profile.buyer, field)
                    for field in CUSTOMER_ROLE_FIELDS
                },
            )
        if BusinessPartnerRole.SUPPLIER in profile.roles:
            buyer_reference = str(profile.seller.buyer_reference or "").strip()
            if not buyer_reference or buyer_reference == previous_number:
                profile.seller.buyer_reference = number
            supplier_role_data = {
                field: getattr(profile.seller, field)
                for field in SUPPLIER_ROLE_FIELDS
            }
            supplier_role_data["payment"] = dict(profile.payment.__dict__)
            self._save_role(
                partner_id,
                BusinessPartnerRole.SUPPLIER,
                supplier_role_data,
            )
        return number

    def delete_partner(self, partner_number: str) -> None:
        number = normalize_partner_number(partner_number)
        with self.conn:
            deleted = self.conn.execute(
                "DELETE FROM business_partners WHERE partner_number = ?",
                (number,),
            ).rowcount
            if not deleted:
                raise KeyError(f"Geschäftspartner nicht gefunden: {number}")

    def _role_rows(self, role: BusinessPartnerRole):
        return self.conn.execute(
            """
            SELECT p.partner_number, p.common_data, r.role_data
            FROM business_partners AS p
            JOIN business_partner_roles AS r
              ON r.partner_id = p.id
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
        values.update(
            {
                field: role_data.get(field, "")
                for field in SUPPLIER_ROLE_FIELDS
            }
        )
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
            partner_id = self._partner_id(number)
            self.conn.execute(
                "DELETE FROM business_partner_roles WHERE partner_id = ? AND role = ?",
                (partner_id, role.value),
            )
            self.conn.execute(
                """
                DELETE FROM business_partners
                WHERE partner_number = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM business_partner_roles
                      WHERE partner_id = ?
                  )
                """,
                (number, partner_id),
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
