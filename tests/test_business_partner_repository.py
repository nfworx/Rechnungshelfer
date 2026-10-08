import tempfile
import unittest
from pathlib import Path

from rechnungshelfer.domain.business_partner import (
    BusinessPartnerProfile,
    BusinessPartnerRole,
)
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

    def test_profile_can_add_supplier_role_to_existing_customer(self):
        self.repository.save_customer(
            Buyer(customer_number="0042", name="Musterhof", city="Altdorf")
        )
        profile = self.repository.load_partner("0042")
        profile.roles = frozenset(
            {BusinessPartnerRole.CUSTOMER, BusinessPartnerRole.SUPPLIER}
        )
        profile.payment.iban = "DE89370400440532013000"

        self.repository.save_partner(profile)

        loaded = self.repository.load_partner("0042")
        self.assertEqual(
            loaded.roles,
            frozenset(
                {BusinessPartnerRole.CUSTOMER, BusinessPartnerRole.SUPPLIER}
            ),
        )
        self.assertEqual(loaded.payment.iban, "DE89370400440532013000")
        self.assertEqual(len(self.repository.list_partners()), 1)

    def test_profile_can_remove_one_role_without_deleting_partner(self):
        self.repository.save_customer(Buyer(customer_number="42", name="Musterhof"))
        self.repository.save_supplier(
            Seller(supplier_number="42", name="Musterhof"),
            Payment(),
        )
        profile = self.repository.load_partner("42")
        profile.roles = frozenset({BusinessPartnerRole.SUPPLIER})

        self.repository.save_partner(profile)

        loaded = self.repository.load_partner("42")
        self.assertEqual(loaded.roles, frozenset({BusinessPartnerRole.SUPPLIER}))
        self.assertEqual(self.repository.list_customers(), [])
        self.assertEqual(len(self.repository.list_suppliers()), 1)

    def test_profile_requires_at_least_one_role(self):
        profile = BusinessPartnerProfile(
            buyer=Buyer(customer_number="42", name="Musterhof"),
            seller=Seller(supplier_number="42", name="Musterhof"),
            payment=Payment(),
            roles=frozenset(),
        )

        with self.assertRaisesRegex(ValueError, "mindestens eine Rolle"):
            self.repository.save_partner(profile)

        self.assertIsNone(self.repository.load_partner("42"))

    def test_partner_number_can_change_without_changing_internal_identity(self):
        self.repository.save_customer(Buyer(customer_number="42", name="Musterhof"))
        self.repository.save_supplier(
            Seller(
                supplier_number="42",
                name="Musterhof",
                buyer_reference="",
            ),
            Payment(),
        )
        profile = self.repository.load_partner("42")
        original_id = profile.partner_id
        profile.buyer.customer_number = "70042"

        self.repository.save_partner(profile)

        self.assertIsNone(self.repository.load_partner("42"))
        renamed = self.repository.load_partner("70042")
        self.assertEqual(renamed.partner_id, original_id)
        self.assertEqual(
            renamed.roles,
            frozenset(
                {BusinessPartnerRole.CUSTOMER, BusinessPartnerRole.SUPPLIER}
            ),
        )
        self.assertEqual(renamed.seller.buyer_reference, "70042")

    def test_partner_number_collision_is_rejected_transactionally(self):
        self.repository.save_customer(Buyer(customer_number="41", name="Hof Eins"))
        self.repository.save_customer(Buyer(customer_number="42", name="Hof Zwei"))
        profile = self.repository.load_partner("42")
        profile.buyer.customer_number = "41"

        with self.assertRaisesRegex(ValueError, "bereits vergeben"):
            self.repository.save_partner(profile)

        self.assertEqual(
            [partner.partner_number for partner in self.repository.list_partners()],
            ["41", "42"],
        )

    def test_blank_supplier_reference_defaults_to_partner_number(self):
        seller = Seller(
            supplier_number="42",
            name="Musterhof",
            buyer_reference="",
        )

        self.repository.save_supplier(seller, Payment())

        loaded, _ = self.repository.list_suppliers()[0]
        self.assertEqual(seller.buyer_reference, "42")
        self.assertEqual(loaded.buyer_reference, "42")


if __name__ == "__main__":
    unittest.main()
