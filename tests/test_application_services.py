import tempfile
import unittest
from pathlib import Path

from rechnungshelfer.application.party_service import PartyApplicationService
from rechnungshelfer.repositories.customer_repository import CustomerRepository
from rechnungshelfer.repositories.database import Database
from rechnungshelfer.repositories.invoice_repository import InvoiceRepository
from rechnungshelfer.repositories.master_data_repository import MasterDataRepository
from rechnungshelfer.repositories.supplier_repository import SupplierRepository
from tests.validation_documents import create_validator_invoice


class PartyApplicationServiceTests(unittest.TestCase):
    def test_legacy_customers_are_migrated_once_in_one_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = Database(root / "application.db")
            invoices = InvoiceRepository(connection=database.connection)
            customers = CustomerRepository(connection=database.connection)
            suppliers = SupplierRepository(connection=database.connection)
            service = PartyApplicationService(
                database=database,
                invoice_repository=invoices,
                customer_repository=customers,
                supplier_repository=suppliers,
                master_data_repository=MasterDataRepository(root / "master.json"),
            )
            invoice = create_validator_invoice()
            invoice.info.invoice_number = "LEGACY-1"
            invoice.buyer.customer_number = ""
            invoices.save(invoice)

            try:
                migrated = service.migrate_customers_from_invoices_if_empty()
                migrated_again = service.migrate_customers_from_invoices_if_empty()
                stored = customers.list_customers()
            finally:
                database.close()

        self.assertEqual(migrated, 1)
        self.assertEqual(migrated_again, 0)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].customer_number, "K0001")


if __name__ == "__main__":
    unittest.main()
