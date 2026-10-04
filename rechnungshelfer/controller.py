# rechnungshelfer/controller.py
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from services.xml_reader import read_xml_file, InvoiceParsingError
from services.pdf_service import create_pdf
from services.xml_service import create_xml
from rechnungshelfer.repositories.invoice_repository import InvoiceRepository
from rechnungshelfer.repositories.customer_repository import CustomerRepository
from rechnungshelfer.repositories.master_data_repository import MasterDataRepository
from rechnungshelfer.repositories.supplier_repository import SupplierRepository
from services.input_validation_service import (
    InputValidationError,
    is_valid_bic,
    is_valid_email,
    is_valid_iban,
    is_valid_phone,
    is_valid_vat_id,
    normalize_invoice_input,
)
from services.validation_service import validate_invoice, ExportValidationError

from rechnungshelfer.domain.models import (
    Seller, Buyer, Delivery, InvoiceInfo, Payment, Invoice, DocumentType,
    DEFAULT_BUYER_REFERENCE,
)

class InvoiceController:
    def __init__(self):
        self.repo = InvoiceRepository()
        self.customer_repo = CustomerRepository(connection=self.repo.conn)
        self.master_data_repository = MasterDataRepository()
        self.supplier_repo = SupplierRepository(connection=self.repo.conn)
        self.last_validation_result = None

    # ========================
    # Neueste Invoice laden
    # ========================
    def load_latest_invoice(self):
        return self.repo.load_latest()

    # ========================
    # Invoice erstellen
    # ========================
    def create_empty_invoice(self, document_type=DocumentType.INVOICE):
        from rechnungshelfer.domain.models import (
            Invoice,
            Seller,
            Buyer,
            Delivery,
            InvoiceInfo,
            Payment,
            InvoiceItem,
        )

        document_type = DocumentType.from_value(document_type)
        invoice = Invoice(
            seller=Seller(),
            buyer=Buyer(),
            delivery=Delivery(),
            info=InvoiceInfo(),
            payment=Payment(),
            items=[InvoiceItem()],
            document_type=document_type,
        )

        # 🔥 HIER Stammdaten anwenden
        self.master_data_repository.apply_to_invoice(invoice)

        if document_type is DocumentType.SELF_BILLED_INVOICE:
            own_company = invoice.seller
            invoice.buyer = self._seller_to_buyer(own_company)
            invoice.buyer.use_invoice_address_as_delivery = True
            invoice.delivery = Delivery(
                name=invoice.buyer.name,
                street=invoice.buyer.street,
                postcode=invoice.buyer.postcode,
                city=invoice.buyer.city,
                country=invoice.buyer.country,
            )
            invoice.seller = Seller(
                name="", street="", postcode="", city="", country="DE",
                phone="", email="", vat="", tax_number="",
                registry_number="", contact_name="",
                supplier_number=self.supplier_repo.next_supplier_number(),
            )
            invoice.seller.required_fields = [
                "name", "street", "postcode", "city", "country", "email"
            ]
            invoice.payment = Payment(
                iban="", bic="", account_holder="",
                payment_means_code="58",
                payment_terms="Der Auszahlungsbetrag wird auf das angegebene Konto überwiesen.",
            )
            invoice.payment.required_fields = [
                "iban", "bic", "account_holder", "payment_means_code"
            ]

        invoice.set_document_type(document_type)

        invoice.calculate(force=True)

        return invoice

    # ========================
    # Invoice speichern
    # ========================
    def save_invoice(self, invoice: Invoice, allow_customer_duplicate=False):
        try:
            normalize_invoice_input(invoice)
        except InputValidationError as e:
            raise ValueError(str(e))

        invoice.calculate(force=True)

        if not invoice.info.invoice_number:
            raise ValueError("Belegnummer fehlt")

        if not invoice.is_self_billed and invoice.buyer.customer_number and invoice.buyer.name:
            duplicates = self.customer_repo.find_duplicates(invoice.buyer)

            real_duplicates = [
                d for d in duplicates
                if d.customer_number != invoice.buyer.customer_number
            ]

            if real_duplicates and not allow_customer_duplicate:
                names = "\n".join(
                    f"- {d.customer_number} | {d.name}"
                    for d in real_duplicates
                )
                raise ValueError(
                    "CUSTOMER_DUPLICATE_FOUND\n"
                    f"{names}"
                )

        try:
            with self.repo.conn:
                if invoice.is_self_billed and invoice.seller.name:
                    self.supplier_repo.save(invoice.seller, invoice.payment, commit=False)

                self.repo.save(invoice, commit=False)

                if (
                    not invoice.is_self_billed
                    and invoice.buyer.customer_number
                    and invoice.buyer.name
                ):
                    self.customer_repo.save(invoice.buyer, commit=False)
        except Exception:
            self.repo.conn.rollback()
            raise
    # ========================
    # Prüfen ob Invoice vorhanden
    # ========================
    def invoice_exists(self, invoice_number: str) -> bool:
        if not invoice_number:
            return False
        return self.repo.exists(invoice_number)

    # ========================
    # Invoice laden aus DB
    # ========================
    def list_invoice_summaries(self):
        return self.repo.list_invoice_summaries()


    def load_invoice(self, invoice_number):
        invoice = self.repo.load(invoice_number)

        if invoice is None:
            raise ValueError(f"Rechnung nicht gefunden: {invoice_number}")

        invoice.calculate(force=True)
        return invoice

    # ========================
    # Invoice löschen
    # ========================
    def delete_invoice(self, invoice_number):
        if not invoice_number:
            raise ValueError("Keine Rechnungsnummer angegeben")
        self.repo.delete(invoice_number)

    # ========================
    # XML laden
    # ========================
    def load_from_xml(self, filepath):
        try:
            invoice = read_xml_file(filepath)
            return invoice
        except InvoiceParsingError as e:
            raise ValueError(f"XML Fehler: {e}")
        except Exception as e:
            raise RuntimeError(f"Fehler beim Laden: {e}")

    # ========================
    # PDF generieren
    # ========================
    def generate_pdf(self, invoice, filepath):
        try:
            normalize_invoice_input(invoice)
        except InputValidationError as e:
            raise ValueError(str(e))   # GUI kann das anzeigen

        missing = self.get_missing_required_fields(invoice, for_xml=False)
        if missing:
            raise ValueError(self.format_missing_fields(missing, "PDF"))

        invoice.calculate(force=True)
        create_pdf(invoice, filepath)

    # ========================
    # XML generieren
    # ========================
    def generate_xml(self, invoice, filepath):
        try:
            normalize_invoice_input(invoice)
        except InputValidationError as e:
            raise ValueError(str(e))

        self._ensure_self_billed_supplier_number(invoice)

        missing = self.get_missing_required_fields(invoice, for_xml=True)
        if missing:
            raise ValueError(self.format_missing_fields(missing, "XML"))

        xml_final = create_xml(
            invoice,
            output_filename=None,
            include_extensions=False,
        )

        validation_result = validate_invoice(
            xml_final,
            invoice,
            use_kosit=True,
        )

        self.last_validation_result = validation_result

        if validation_result.errors or validation_result.warnings:
            messages = []

            if validation_result.errors:
                messages.append("XSD-Fehler:")
                messages.extend(f"- {e}" for e in validation_result.errors)

            if validation_result.warnings:
                messages.append("")
                messages.append("Validierungswarnungen:")
                messages.extend(f"- {w}" for w in validation_result.warnings)

            raise ExportValidationError(
                "XML-Export wurde abgebrochen.\n\n"
                "Die Validierung ist fehlgeschlagen.",
                details="\n".join(messages),
                report_html=validation_result.report_html,
            )

        Path(filepath).write_bytes(xml_final)

        return xml_final

    # ========================
    # Pflichtfelder prüfen
    # ========================
    def is_required_field(self, invoice, section, attr, item_pos=None):
        """
        Prüft, ob ein Attribut Pflichtfeld ist.
        - section: Seller | Buyer | Delivery | Invoice | Payment | Item
        """
        if section == "Item":
            if item_pos is None:
                raise ValueError("Für 'Item' muss item_pos angegeben werden")
            item = next(
                (i for i in invoice.items if i.pos == item_pos),
                None
            )
            return bool(item and attr in item.required_fields)

        obj_map = {
            "Seller": invoice.seller,
            "Buyer": invoice.buyer,
            "Delivery": invoice.delivery,
            "Invoice": invoice.info,
            "Payment": invoice.payment
        }

        obj = obj_map.get(section)
        return bool(obj and attr in getattr(obj, "required_fields", []))

    def get_missing_required_fields(self, invoice, for_xml=True):
        """Liefert fehlende Pflichtfelder getrennt nach PDF- und XML-Export."""
        if for_xml and invoice.is_self_billed and hasattr(self, "supplier_repo"):
            self._ensure_self_billed_supplier_number(invoice)

        missing = []

        def check(section_name, obj, fields):
            for field in fields:
                value = getattr(obj, field, None)
                if value is None or (isinstance(value, str) and not value.strip()):
                    missing.append((section_name, obj, field))

        if invoice.is_self_billed:
            seller_required = ["name", "street", "postcode", "city", "country", "email"]
            buyer_required = ["name", "street", "postcode", "city", "country"]
            if for_xml:
                buyer_required.extend(["email", "leitweg_id"])
            payment_required = ["iban", "bic", "account_holder", "payment_means_code"]

            check("Lieferant", invoice.seller, seller_required)
            check("Eigener Betrieb", invoice.buyer, buyer_required)
            check("Auszahlung", invoice.payment, payment_required)

            if not (invoice.seller.vat or invoice.seller.tax_number):
                missing.append(("Lieferant", invoice.seller, "vat_or_tax_number"))

            sections = [("Invoice", invoice.info)]
        else:
            sections = [
                ("Seller", invoice.seller),
                ("Buyer", invoice.buyer),
                ("Invoice", invoice.info),
                ("Payment", invoice.payment),
            ]

        if not invoice.buyer.use_invoice_address_as_delivery:
            sections.append(("Delivery", invoice.delivery))

        for section_name, obj in sections:
            fields = list(getattr(obj, "required_fields", []))
            if for_xml and obj is invoice.buyer and "leitweg_id" not in fields:
                fields.append("leitweg_id")
            check(section_name, obj, fields)

        for item in invoice.items:
            check(
                f"Position {item.pos or 'unbekannt'}",
                item,
                getattr(item, "required_fields", []),
            )

            if item.qty is None or item.qty <= 0:
                missing.append((f"Position {item.pos or 'unbekannt'}", item, "qty"))

        if for_xml:
            self._add_xml_format_issues(invoice, missing)

        return missing

    @staticmethod
    def _add_xml_format_issues(invoice, missing):
        parties = [
            ("Lieferant" if invoice.is_self_billed else "Verkäufer", invoice.seller),
            ("Eigener Betrieb" if invoice.is_self_billed else "Kunde", invoice.buyer),
        ]
        for section, party in parties:
            if party.email and not is_valid_email(party.email):
                missing.append((section, party, "email_invalid"))
            if party.vat and not is_valid_vat_id(party.vat, party.country):
                missing.append((section, party, "vat_invalid"))

        seller_section = "Lieferant" if invoice.is_self_billed else "Verkäufer"
        if not invoice.seller.phone:
            missing.append((seller_section, invoice.seller, "phone"))
        elif not is_valid_phone(invoice.seller.phone):
            missing.append((seller_section, invoice.seller, "phone_invalid"))

        if invoice.payment.iban and not is_valid_iban(invoice.payment.iban):
            missing.append(("Auszahlung" if invoice.is_self_billed else "Zahlung", invoice.payment, "iban_invalid"))
        if invoice.payment.bic and not is_valid_bic(invoice.payment.bic):
            missing.append(("Auszahlung" if invoice.is_self_billed else "Zahlung", invoice.payment, "bic_invalid"))

        if not any(
            (
                invoice.seller.supplier_number,
                invoice.seller.registry_number,
                invoice.seller.vat,
            )
        ):
            missing.append((seller_section, invoice.seller, "seller_identifier"))

    def _ensure_self_billed_supplier_number(self, invoice):
        if invoice.is_self_billed and not invoice.seller.supplier_number:
            invoice.seller.supplier_number = self.supplier_repo.next_supplier_number()

    @staticmethod
    def format_missing_fields(missing, export_name):
        labels = {
            "vat_or_tax_number": "Steuernummer oder USt-ID",
            "leitweg_id": "Käuferreferenz (BT-10)",
            "email_invalid": "E-Mail-Adresse ist ungültig",
            "phone_invalid": "Telefonnummer muss mindestens drei Ziffern enthalten",
            "vat_invalid": "USt-ID benötigt ein Länderpräfix, z. B. DE123456789",
            "iban_invalid": "IBAN ist ungültig",
            "bic_invalid": "BIC ist ungültig",
            "seller_identifier": "Lieferantennummer, Handelsregisternummer oder USt-ID",
        }
        lines = []
        for section, obj, field in missing:
            label = labels.get(field)
            if label is None:
                label = obj.get_label(field) if hasattr(obj, "get_label") else field
            line = f"- {section}: {label}"
            if line not in lines:
                lines.append(line)
        return (
            f"{export_name}-Export nicht möglich. Angaben fehlen oder sind ungültig:\n\n"
            + "\n".join(lines)
        )

    def check_required_fields(self, invoice, for_xml=True):
        return not self.get_missing_required_fields(invoice, for_xml=for_xml)

    def check_pdf_required_fields(self, invoice):
        return self.check_required_fields(invoice, for_xml=False)

    def check_xml_required_fields(self, invoice):
        return self.check_required_fields(invoice, for_xml=True)

    def copy_invoice(self, invoice: Invoice) -> Invoice:
        copied = deepcopy(invoice)
        copied.info.invoice_number = ""
        copied.info.invoice_date = date.today().strftime("%d.%m.%Y")
        copied.info.delivery_date = ""
        copied.info.payment_due_date = (
            date.today() + timedelta(days=14)
        ).strftime("%d.%m.%Y")
        copied.calculate(force=True)
        return copied

    # ========================
    # Invoice Recalculate
    # ========================
    def recalculate(self, invoice, force=False):
        invoice.calculate(force=force)

    # ========================
    # Repository schließen
    # ========================
    def close(self):
        self.repo.close()

        if hasattr(self.customer_repo, "close"):
            self.customer_repo.close()

        self.supplier_repo.close()

    # ========================
    # Kunde speichern
    # ========================
    def save_customer(self, buyer: Buyer):
        if not buyer.customer_number:
            raise ValueError("Kundennummer fehlt. Kunde kann nicht gespeichert werden.")
        if not buyer.name:
            raise ValueError("Name des Kunden fehlt. Kunde kann nicht gespeichert werden.")

        self.customer_repo.save(buyer)

    # ========================
    # Kunde suchen (Autocomplete)
    # ========================
    def search_customers(self, field: str, query: str):
        """
        Sucht Kunden über die CustomerRepository-DB.
        """
        return self.customer_repo.search(field, query, limit=6)

    # ========================
    # Alle Kunden auflisten
    # ========================
    def list_customers(self):
        """
        Gibt alle Kunden zurück (CustomerRepository)
        """
        return self.customer_repo.list_customers()
    
    def delete_customer(self, customer_number):
        if not customer_number:
            raise ValueError("Keine Kundennummer angegeben")
        self.customer_repo.delete(customer_number)
    
    def load_master_data(self, seller, payment):
        return self.master_data_repository.load_into(seller, payment)


    def save_master_data(self, seller, payment):
        self.master_data_repository.save(seller, payment)

    def load_own_company_buyer(self):
        seller, _ = self.master_data_repository.load_into(Seller(), Payment())
        return self._seller_to_buyer(seller)


    def apply_master_data_to_invoice(self, invoice):
        return self.master_data_repository.apply_to_invoice(invoice)
    

    
    def migrate_customers_from_invoices_if_empty(self):
        if self.customer_repo.count() > 0:
            return

        invoices = self.repo.list_invoice_numbers()

        for invoice_number in invoices:
            invoice = self.repo.load(invoice_number)

            if not invoice:
                continue

            if invoice.is_self_billed:
                continue

            buyer = invoice.buyer

            if not buyer.name:
                continue

            # Falls alte Rechnungen keine Kundennummer haben
            if not buyer.customer_number:
                buyer.customer_number = self._generate_customer_number_from_invoice(buyer)

            self.customer_repo.save(buyer)


    def _generate_customer_number_from_invoice(self, buyer):
        return self.customer_repo.next_customer_number()
    
    def find_customer_duplicates(self, buyer: Buyer):
        return self.customer_repo.find_duplicates(buyer)

    def list_suppliers(self):
        return self.supplier_repo.list_suppliers()

    def save_supplier(self, seller: Seller, payment: Payment):
        return self.supplier_repo.save(seller, payment)

    def delete_supplier(self, supplier_number: str):
        self.supplier_repo.delete(supplier_number)

    @staticmethod
    def _seller_to_buyer(seller: Seller) -> Buyer:
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
