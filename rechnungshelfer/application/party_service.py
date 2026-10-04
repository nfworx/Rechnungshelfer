"""Anwendungsfälle für Kunden, Lieferanten und eigene Stammdaten."""

from rechnungshelfer.domain.invoice_factory import InvoiceFactory
from rechnungshelfer.domain.models import Buyer, Payment, Seller


class PartyApplicationService:
    def __init__(
        self,
        *,
        database,
        invoice_repository,
        customer_repository,
        supplier_repository,
        master_data_repository,
    ):
        self._database = database
        self._invoices = invoice_repository
        self._customers = customer_repository
        self._suppliers = supplier_repository
        self._master_data = master_data_repository

    def save_customer(self, buyer: Buyer) -> None:
        if not buyer.customer_number:
            raise ValueError("Kundennummer fehlt. Kunde kann nicht gespeichert werden.")
        if not buyer.name:
            raise ValueError("Name des Kunden fehlt. Kunde kann nicht gespeichert werden.")
        self._customers.save(buyer)

    def search_customers(self, field: str, query: str):
        return self._customers.search(field, query, limit=6)

    def list_customers(self):
        return self._customers.list_customers()

    def delete_customer(self, customer_number: str) -> None:
        if not customer_number:
            raise ValueError("Keine Kundennummer angegeben")
        self._customers.delete(customer_number)

    def load_master_data(self, seller: Seller, payment: Payment):
        return self._master_data.load_into(seller, payment)

    def save_master_data(self, seller: Seller, payment: Payment) -> None:
        self._master_data.save(seller, payment)

    def load_own_company_buyer(self) -> Buyer:
        seller, _ = self._master_data.load_into(Seller(), Payment())
        return InvoiceFactory.seller_to_buyer(seller)

    def apply_master_data_to_invoice(self, invoice):
        return self._master_data.apply_to_invoice(invoice)

    def migrate_customers_from_invoices_if_empty(self) -> int:
        if self._customers.count() > 0:
            return 0

        migrated = 0
        with self._database.transaction():
            for invoice_number in self._invoices.list_invoice_numbers():
                invoice = self._invoices.load(invoice_number)
                if not invoice or invoice.is_self_billed or not invoice.buyer.name:
                    continue

                buyer = invoice.buyer
                if not buyer.customer_number:
                    buyer.customer_number = self._customers.next_customer_number()
                self._customers.save(buyer, commit=False)
                migrated += 1
        return migrated

    def find_customer_duplicates(self, buyer: Buyer):
        return self._customers.find_duplicates(buyer)

    def list_suppliers(self):
        return self._suppliers.list_suppliers()

    def save_supplier(self, seller: Seller, payment: Payment):
        return self._suppliers.save(seller, payment)

    def delete_supplier(self, supplier_number: str) -> None:
        self._suppliers.delete(supplier_number)
