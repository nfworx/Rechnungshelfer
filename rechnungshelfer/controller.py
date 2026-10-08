"""Stabile GUI-Fassade für die Anwendungsfälle des Rechnungshelfers."""

from rechnungshelfer.application.invoice_service import InvoiceApplicationService
from rechnungshelfer.application.grain_scheme_service import (
    GrainSchemeApplicationService,
)
from rechnungshelfer.application.party_service import PartyApplicationService
from rechnungshelfer.domain.invoice_factory import InvoiceFactory
from rechnungshelfer.domain.models import (
    Buyer,
    DocumentType,
    Invoice,
    Payment,
    Seller,
)
from rechnungshelfer.repositories.customer_repository import CustomerRepository
from rechnungshelfer.repositories.database import Database
from rechnungshelfer.repositories.invoice_repository import InvoiceRepository
from rechnungshelfer.repositories.grain_scheme_repository import (
    GrainSchemeRepository,
)
from rechnungshelfer.repositories.master_data_repository import MasterDataRepository
from rechnungshelfer.repositories.supplier_repository import SupplierRepository
from rechnungshelfer.services.export_service import InvoiceExportService
from rechnungshelfer.services.kosit_validation_service import KositValidator


class InvoiceController:
    def __init__(self):
        self.database = Database()
        self.repo = InvoiceRepository(connection=self.database.connection)
        self.customer_repo = CustomerRepository(connection=self.database.connection)
        self.master_data_repository = MasterDataRepository()
        self.supplier_repo = SupplierRepository(connection=self.database.connection)
        self.grain_scheme_repo = GrainSchemeRepository(self.database.connection)
        self.invoice_factory = InvoiceFactory()
        self.invoice_service = self._create_invoice_service()
        self.party_service = self._create_party_service()
        self.export_service = self._create_export_service()
        self.grain_scheme_service = GrainSchemeApplicationService(
            database=self.database,
            repository=self.grain_scheme_repo,
        )

    def _create_invoice_service(self):
        return InvoiceApplicationService(
            database=self.database,
            invoice_repository=self.repo,
            customer_repository=self.customer_repo,
            supplier_repository=self.supplier_repo,
            master_data_repository=self.master_data_repository,
            invoice_factory=getattr(self, "invoice_factory", InvoiceFactory()),
        )

    def _get_invoice_service(self):
        if not hasattr(self, "invoice_service"):
            self.invoice_service = self._create_invoice_service()
        return self.invoice_service

    def _create_party_service(self):
        return PartyApplicationService(
            database=self.database,
            invoice_repository=self.repo,
            customer_repository=self.customer_repo,
            supplier_repository=self.supplier_repo,
            master_data_repository=self.master_data_repository,
        )

    def _get_party_service(self):
        if not hasattr(self, "party_service"):
            self.party_service = self._create_party_service()
        return self.party_service

    def _create_export_service(self):
        supplier_number_provider = (
            self.supplier_repo.next_supplier_number
            if hasattr(self, "supplier_repo")
            else None
        )
        return InvoiceExportService(
            external_validator=KositValidator(),
            supplier_number_provider=supplier_number_provider,
        )

    def _get_export_service(self):
        if not hasattr(self, "export_service"):
            self.export_service = self._create_export_service()
        return self.export_service

    # Belege
    def load_latest_invoice(self):
        return self._get_invoice_service().load_latest_invoice()

    def create_empty_invoice(self, document_type=DocumentType.INVOICE):
        return self._get_invoice_service().create_empty_invoice(document_type)

    def save_invoice(self, invoice: Invoice, allow_customer_duplicate=False):
        return self._get_invoice_service().save_invoice(
            invoice,
            allow_customer_duplicate=allow_customer_duplicate,
        )

    def invoice_exists(self, invoice_number: str) -> bool:
        return self._get_invoice_service().invoice_exists(invoice_number)

    def list_invoice_summaries(self):
        return self._get_invoice_service().list_invoice_summaries()

    def load_invoice(self, invoice_number):
        return self._get_invoice_service().load_invoice(invoice_number)

    def delete_invoice(self, invoice_number):
        return self._get_invoice_service().delete_invoice(invoice_number)

    def load_from_xml(self, filepath):
        return self._get_invoice_service().load_from_xml(filepath)

    def load_from_pdf(self, filepath, *, password=None):
        return self._get_invoice_service().load_from_pdf(
            filepath,
            password=password,
        )

    def analyze_pdf(self, filepath, *, password=None):
        return self._get_invoice_service().analyze_pdf(
            filepath,
            password=password,
        )

    def create_invoice_from_pdf_analysis(self, analysis):
        return self._get_invoice_service().create_invoice_from_pdf_analysis(analysis)

    # Getreide-Regelwerke
    def load_grain_scheme_drafts(self, harvest_year: int):
        return self.grain_scheme_service.load_drafts(harvest_year)

    def save_grain_scheme_drafts(self, harvest_year: int, drafts: dict):
        return self.grain_scheme_service.save_drafts(harvest_year, drafts)

    def activate_grain_scheme(
        self,
        grain_type_code: str,
        harvest_year: int,
        payload: dict,
    ):
        return self.grain_scheme_service.activate(
            grain_type_code,
            harvest_year,
            payload,
        )

    def list_grain_scheme_versions(
        self,
        grain_type_code: str,
        harvest_year: int,
    ):
        return self.grain_scheme_service.list_versions(
            grain_type_code,
            harvest_year,
        )

    def copy_invoice(self, invoice: Invoice) -> Invoice:
        return self._get_invoice_service().copy_invoice(invoice)

    def recalculate(self, invoice, force=False):
        return self._get_invoice_service().recalculate(invoice, force=force)

    # Export und Exportvorprüfung
    def generate_pdf(self, invoice, filepath):
        return self._get_export_service().export_pdf(invoice, filepath)

    def generate_xml(self, invoice, filepath):
        return self._get_export_service().export_xml(invoice, filepath)

    def is_required_field(self, invoice, section, attr, item_pos=None):
        return self._get_export_service().is_required_field(
            invoice,
            section,
            attr,
            item_pos=item_pos,
        )

    def get_missing_required_fields(self, invoice, for_xml=True):
        return self._get_export_service().get_missing_required_fields(
            invoice,
            for_xml=for_xml,
        )

    @staticmethod
    def format_missing_fields(missing, export_name):
        return InvoiceExportService.format_missing_fields(missing, export_name)

    def check_required_fields(self, invoice, for_xml=True):
        return self._get_export_service().check_required_fields(
            invoice,
            for_xml=for_xml,
        )

    def check_pdf_required_fields(self, invoice):
        return self.check_required_fields(invoice, for_xml=False)

    def check_xml_required_fields(self, invoice):
        return self.check_required_fields(invoice, for_xml=True)

    # Kunden, Lieferanten und Stammdaten
    def save_customer(self, buyer: Buyer):
        return self._get_party_service().save_customer(buyer)

    def search_customers(self, field: str, query: str):
        return self._get_party_service().search_customers(field, query)

    def list_customers(self):
        return self._get_party_service().list_customers()

    def delete_customer(self, customer_number):
        return self._get_party_service().delete_customer(customer_number)

    def load_master_data(self, seller, payment):
        return self._get_party_service().load_master_data(seller, payment)

    def save_master_data(self, seller, payment):
        return self._get_party_service().save_master_data(seller, payment)

    def load_own_company_buyer(self):
        return self._get_party_service().load_own_company_buyer()

    def apply_master_data_to_invoice(self, invoice):
        return self._get_party_service().apply_master_data_to_invoice(invoice)

    def migrate_customers_from_invoices_if_empty(self):
        return self._get_party_service().migrate_customers_from_invoices_if_empty()

    def find_customer_duplicates(self, buyer: Buyer):
        return self._get_party_service().find_customer_duplicates(buyer)

    def list_suppliers(self):
        return self._get_party_service().list_suppliers()

    def save_supplier(self, seller: Seller, payment: Payment):
        return self._get_party_service().save_supplier(seller, payment)

    def delete_supplier(self, supplier_number: str):
        return self._get_party_service().delete_supplier(supplier_number)

    @staticmethod
    def _seller_to_buyer(seller: Seller) -> Buyer:
        return InvoiceFactory.seller_to_buyer(seller)

    def close(self):
        if hasattr(self, "database"):
            self.database.close()
            return

        # Kompatibilität für gezielt ohne __init__ erzeugte Test-Controller.
        self.repo.close()
        if hasattr(self.customer_repo, "close"):
            self.customer_repo.close()
        self.supplier_repo.close()
