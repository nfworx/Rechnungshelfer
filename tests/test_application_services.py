import tempfile
import unittest
from pathlib import Path

from rechnungshelfer.application.party_service import PartyApplicationService
from rechnungshelfer.domain.models import Buyer, Payment, Seller
from rechnungshelfer.repositories.business_partner_repository import (
    BusinessPartnerRepository,
)
from rechnungshelfer.repositories.database import Database
from rechnungshelfer.repositories.master_data_repository import MasterDataRepository


class PartyApplicationServiceTests(unittest.TestCase):
    def test_same_number_can_have_customer_and_supplier_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = Database(root / "application.db")
            partners = BusinessPartnerRepository(connection=database.connection)
            service = PartyApplicationService(
                business_partner_repository=partners,
                master_data_repository=MasterDataRepository(root / "master.json"),
            )

            try:
                service.save_customer(
                    Buyer(
                        customer_number="0042",
                        name="Musterhof",
                        city="Dorf",
                        email="hof@example.de",
                    )
                )
                service.save_supplier(
                    Seller(
                        supplier_number="0042",
                        name="Musterhof",
                        city="Dorf",
                    ),
                    Payment(iban="DE89370400440532013000"),
                )
                customers = service.list_customers()
                suppliers = service.list_suppliers()
            finally:
                database.close()

        self.assertEqual([item.customer_number for item in customers], ["0042"])
        self.assertEqual([item[0].supplier_number for item in suppliers], ["0042"])
        self.assertEqual(suppliers[0][1].iban, "DE89370400440532013000")


if __name__ == "__main__":
    unittest.main()
