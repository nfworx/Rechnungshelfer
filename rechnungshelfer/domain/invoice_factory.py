"""Fachliche Erzeugung neuer Belege und Belegkopien."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Callable

from .models import (
    DEFAULT_BUYER_REFERENCE,
    Buyer,
    Delivery,
    DocumentType,
    Invoice,
    InvoiceInfo,
    InvoiceItem,
    Payment,
    Seller,
)


class InvoiceFactory:
    """Erzeugt Belege, ohne Datenbank, Dateisystem oder GUI zu kennen."""

    def __init__(self, today_provider: Callable[[], date] = date.today):
        self._today_provider = today_provider

    def create(
        self,
        document_type: DocumentType | str = DocumentType.INVOICE,
        *,
        own_company: Seller | None = None,
        own_payment: Payment | None = None,
        supplier_number: str = "",
    ) -> Invoice:
        document_type = DocumentType.from_value(document_type)
        own_company = deepcopy(own_company) if own_company is not None else Seller()
        own_payment = deepcopy(own_payment) if own_payment is not None else Payment()

        invoice = Invoice(
            seller=own_company,
            buyer=Buyer(),
            delivery=Delivery(),
            info=InvoiceInfo(),
            payment=own_payment,
            items=[InvoiceItem()],
            document_type=document_type,
        )

        if document_type is DocumentType.SELF_BILLED_INVOICE:
            invoice.buyer = self.seller_to_buyer(own_company)
            invoice.buyer.use_invoice_address_as_delivery = True
            invoice.delivery = Delivery(
                name=invoice.buyer.name,
                street=invoice.buyer.street,
                postcode=invoice.buyer.postcode,
                city=invoice.buyer.city,
                country=invoice.buyer.country,
            )
            invoice.seller = Seller(
                name="",
                street="",
                postcode="",
                city="",
                country="DE",
                phone="",
                email="",
                vat="",
                tax_number="",
                registry_number="",
                contact_name="",
                supplier_number=supplier_number,
                buyer_reference="",
            )
            invoice.payment = Payment(
                iban="",
                bic="",
                account_holder="",
                payment_means_code="58",
                payment_terms=(
                    "Der Auszahlungsbetrag wird auf das angegebene Konto überwiesen."
                ),
            )

        invoice.set_document_type(document_type)
        invoice.calculate(force=True)
        return invoice

    def copy(self, invoice: Invoice) -> Invoice:
        copied = deepcopy(invoice)
        today = self._today_provider()
        copied.info.invoice_number = ""
        copied.info.invoice_date = today.strftime("%d.%m.%Y")
        copied.info.delivery_date = ""
        copied.info.payment_due_date = (today + timedelta(days=14)).strftime(
            "%d.%m.%Y"
        )
        copied.calculate(force=True)
        return copied

    @staticmethod
    def seller_to_buyer(seller: Seller) -> Buyer:
        return Buyer(
            name=seller.name,
            street=seller.street,
            postcode=seller.postcode,
            city=seller.city,
            country=seller.country,
            leitweg_id=seller.buyer_reference or DEFAULT_BUYER_REFERENCE,
            email=seller.email,
            contact_name=seller.contact_name,
            phone=seller.phone,
            vat=seller.vat,
            tax_number=seller.tax_number,
            registry_number=seller.registry_number,
        )
