import tempfile
import unittest
from pathlib import Path

from rechnungshelfer.domain.models import Buyer, Payment, Seller
from rechnungshelfer.repositories.business_partner_repository import (
    BusinessPartnerRepository,
)
from rechnungshelfer.repositories.database import Database


class BusinessPartnerRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Database(
            Path(self.temporary_directory.name) / "business-partners.db"
        )
        self.repository = BusinessPartnerRepository(
            connection=self.database.connection
        )

    def tearDown(self):
        self.database.close()
        self.temporary_directory.cleanup()

    def test_customer_and_supplier_share_one_partner(self):
        self.repository.save_customer(
            Buyer(
                customer_number="0042",
                name="Musterhof",
                city="Altdorf",
                email="hof@example.de",
                leitweg_id="LEITWEG-1",
            )
        )
        self.repository.save_supplier(
            Seller(
                supplier_number="0042",
                name="Musterhof",
                city="Altdorf",
                phone="01234 5678",
            ),
            Payment(iban="DE89370400440532013000"),
        )

        partner_count = self.database.connection.execute(
            "SELECT COUNT(*) FROM business_partners"
        ).fetchone()[0]
        roles = self.database.connection.execute(
            "SELECT role FROM business_partner_roles ORDER BY role"
        ).fetchall()
        customer = self.repository.list_customers()[0]
        seller, payment = self.repository.list_suppliers()[0]

        self.assertEqual(partner_count, 1)
        self.assertEqual(roles, [("customer",), ("supplier",)])
        self.assertEqual(customer.customer_number, "0042")
        self.assertEqual(customer.phone, "01234 5678")
        self.assertEqual(customer.leitweg_id, "LEITWEG-1")
        self.assertEqual(seller.supplier_number, "0042")
        self.assertEqual(payment.iban, "DE89370400440532013000")

    def test_deleting_one_role_keeps_partner_and_other_role(self):
        self.repository.save_customer(Buyer(customer_number="42", name="Musterhof"))
        self.repository.save_supplier(
            Seller(supplier_number="42", name="Musterhof"),
            Payment(),
        )

        self.repository.delete_customer("42")

        self.assertEqual(self.repository.list_customers(), [])
        self.assertEqual(len(self.repository.list_suppliers()), 1)
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM business_partners"
            ).fetchone()[0],
            1,
        )

    def test_prefixed_number_is_rejected_without_partial_record(self):
        with self.assertRaisesRegex(ValueError, "nur aus Ziffern"):
            self.repository.save_customer(
                Buyer(customer_number="K0042", name="Musterhof")
            )

        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM business_partners"
            ).fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
