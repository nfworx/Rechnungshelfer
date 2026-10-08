"""Vollstaendig ausgefuellte Beispieldokumente fuer Anwendung und Tests."""


from rechnungshelfer.domain.models import (
    Buyer,
    Delivery,
    DocumentType,
    Invoice,
    InvoiceInfo,
    InvoiceItem,
    Payment,
    Seller,
)


def _sample_items(prefix: str) -> list[InvoiceItem]:
    return [
        InvoiceItem(pos=1, name=f"{prefix} Beratungsleistung", description="Zwei Stunden Fachberatung mit Positionsrabatt", qty="2", unit="HUR", price_without_discount="125.00", discount="5.00", vat="19.00"),
        InvoiceItem(pos=2, name=f"{prefix} Fachbuch", description="Gedrucktes Fachbuch zum ermaessigten Steuersatz", qty="3", unit="C62", price_without_discount="25.00", vat="7.00"),
        InvoiceItem(pos=3, name=f"{prefix} Agrarerzeugnis", description="Gewichtsbasierte Position mit landwirtschaftlichem Steuersatz", qty="1.25", unit="TNE", price_without_discount="800.00", discount="25.00", vat="7.80"),
        InvoiceItem(pos=4, name=f"{prefix} steuerfreie Testposition", description="Technischer Test der Steuerkategorie Z mit 0 Prozent", qty="4", unit="LTR", price_without_discount="12.50", vat="0.00", tax_category="Z"),
    ]


def create_sample_invoice() -> Invoice:
    """Erstellt eine neue, maximal ausgefuellte Testrechnung."""
    seller = Seller(
        name="Beispiel Software GmbH", street="Testallee 10", postcode="10115",
        city="Berlin", country="DE", phone="+49 30 12345670",
        email="rechnung@example.org", vat="DE136695976",
        tax_number="30/123/45678", registry_number="HRB 123456 B",
        contact_name="Erika Beispiel", supplier_number="1000",
        buyer_reference="BUCHHALTUNG",
    )
    buyer = Buyer(
        name="Musterkunde AG", street="Pruefstrasse 20", postcode="20095",
        city="Hamburg", country="DE", leitweg_id="04011000-12345-67",
        email="e-rechnung@example.net", contact_name="Max Mustermann",
        customer_number="2000", use_invoice_address_as_delivery=False,
        phone="+49 40 76543210", vat="DE122119035",
        tax_number="22/456/78901", registry_number="HRB 654321",
    )
    delivery = Delivery(
        name="Musterkunde AG, Warenannahme", street="Lagerweg 5",
        postcode="20457", city="Hamburg", country="DE",
    )
    delivery.update_required_fields(buyer)

    invoice = Invoice(
        seller=seller,
        buyer=buyer,
        delivery=delivery,
        info=InvoiceInfo(
            invoice_number="80001",
            invoice_date="01.10.2026",
            delivery_date="30.09.2026",
            payment_due_date="15.10.2026",
            invoice_type_code="380",
            delivery_note="LS-2026-0042",
            delivery_instruction="Anlieferung werktags von 08:00 bis 16:00 Uhr",
        ),
        payment=Payment(
            iban="DE89370400440532013000", bic="COBADEFFXXX",
            account_holder="Beispiel Software GmbH", payment_means_code="58",
            payment_terms="Zahlbar innerhalb von 14 Tagen ohne Abzug.",
        ),
        items=_sample_items("Rechnung"),
        document_type=DocumentType.INVOICE,
    )
    invoice.calculate(force=True)
    return invoice


def create_sample_self_billed_invoice() -> Invoice:
    """Erstellt eine neue, maximal ausgefuellte Testgutschrift."""
    supplier = Seller(
        name="Landwirtschaft Musterhof", street="Feldweg 7", postcode="29690",
        city="Schwarmstedt", country="DE", phone="+49 5071 123456",
        email="abrechnung@example.com", vat="", tax_number="24/111/22222",
        registry_number="", contact_name="Luise Landwirtin",
        supplier_number="3000", buyer_reference="BUCHHALTUNG",
    )
    buyer = Buyer(
        name="Abrechnung Handel GmbH", street="Kontorstrasse 12",
        postcode="28195", city="Bremen", country="DE",
        leitweg_id="BUCHHALTUNG", email="buchhaltung@example.de",
        contact_name="Einkauf", customer_number="",
        use_invoice_address_as_delivery=True, phone="+49 421 987654",
        vat="DE811110555", tax_number="60/333/44444",
        registry_number="HRB 10000 HB",
    )
    invoice = Invoice(
        seller=supplier,
        buyer=buyer,
        delivery=Delivery(),
        info=InvoiceInfo(
            invoice_number="80002",
            invoice_date="02.10.2026",
            delivery_date="",
            payment_due_date="16.10.2026",
            invoice_type_code="389",
            delivery_note="",
        ),
        payment=Payment(
            iban="DE75512108001245126199", bic="SOGEDEFFXXX",
            account_holder="Landwirtschaft Musterhof", payment_means_code="58",
            payment_terms="Auszahlung innerhalb von 14 Tagen.",
        ),
        items=_sample_items("Gutschrift"),
        document_type=DocumentType.SELF_BILLED_INVOICE,
    )
    invoice.calculate(force=True)
    return invoice


def create_sample_document(document_type: DocumentType) -> Invoice:
    """Erstellt passend zum Belegtyp stets eine frische Beispielinstanz."""
    document_type = DocumentType.from_value(document_type)
    if document_type is DocumentType.SELF_BILLED_INVOICE:
        return create_sample_self_billed_invoice()
    return create_sample_invoice()
