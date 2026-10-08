"""Anwendungsfälle für Kunden, Lieferanten und eigene Stammdaten."""

from rechnungshelfer.domain.invoice_factory import InvoiceFactory
from rechnungshelfer.domain.models import Buyer, Payment, Seller


class PartyApplicationService:
    def __init__(
        self,
        *,
        business_partner_repository,
        master_data_repository,
    ):
        self._partners = business_partner_repository
        self._master_data = master_data_repository

    def save_customer(self, buyer: Buyer) -> None:
        if not buyer.customer_number:
            raise ValueError(
                "GeschÃ¤ftspartnernummer fehlt. Kunde kann nicht gespeichert werden."
            )
        if not buyer.name:
            raise ValueError("Name des Kunden fehlt. Kunde kann nicht gespeichert werden.")
        self._partners.save_customer(buyer)

    def search_customers(self, field: str, query: str):
        return self._partners.search_customers(field, query, limit=6)

    def list_customers(self):
        return self._partners.list_customers()

    def delete_customer(self, customer_number: str) -> None:
        if not customer_number:
            raise ValueError("Keine GeschÃ¤ftspartnernummer angegeben")
        self._partners.delete_customer(customer_number)

    def load_master_data(self, seller: Seller, payment: Payment):
        return self._master_data.load_into(seller, payment)

    def save_master_data(self, seller: Seller, payment: Payment) -> None:
        self._master_data.save(seller, payment)

    def load_own_company_buyer(self) -> Buyer:
        seller, _ = self._master_data.load_into(Seller(), Payment())
        return InvoiceFactory.seller_to_buyer(seller)

    def apply_master_data_to_invoice(self, invoice):
        return self._master_data.apply_to_invoice(invoice)

    def find_customer_duplicates(self, buyer: Buyer):
        return self._partners.find_customer_duplicates(buyer)

    def list_suppliers(self):
        return self._partners.list_suppliers()

    def save_supplier(self, seller: Seller, payment: Payment):
        return self._partners.save_supplier(seller, payment)

    def delete_supplier(self, supplier_number: str) -> None:
        self._partners.delete_supplier(supplier_number)
