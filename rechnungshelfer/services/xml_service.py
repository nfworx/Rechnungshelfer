# rechnungshelfer/services/xml_service.py
from lxml import etree
from rechnungshelfer.domain.models import Invoice
from datetime import datetime, timedelta
from decimal import Decimal

# ==========================================================
# Namespaces (XRechnung 3.0 / UBL 2.1)
# ==========================================================
NSMAP = {
    None: "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

def _cbc(tag): return f"{{{NSMAP['cbc']}}}{tag}"
def _cac(tag): return f"{{{NSMAP['cac']}}}{tag}"
def _ext(tag): return f"{{{NSMAP['ext']}}}{tag}"

# ==========================================================
# Hilfsfunktionen (FORMATIERUNG – KEINE LOGIK)
# ==========================================================
def format_date_iso(date_str: str, default="2026-01-01") -> str:
    if not date_str:
        return default
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return default

def format_iso(value) -> str:
    return f"{Decimal(str(value)):.2f}"


def format_percent(value) -> str:
    decimal_value = Decimal(str(value))
    text = format(decimal_value.normalize(), "f")
    return "0" if text == "-0" else text

# ==========================================================
# UBL Extensions (nur für XSD-Check)
# ==========================================================
def build_extensions(root, invoice):
    ext_el = etree.SubElement(root, _ext("UBLExtensions"))
    ubl_ext = etree.SubElement(ext_el, _ext("UBLExtension"))
    content = etree.SubElement(ubl_ext, _ext("ExtensionContent"))

    ctx = etree.SubElement(content, "ExchangedDocumentContext")
    etree.SubElement(
        ctx,
        "GuidelineSpecifiedDocumentContextParameter"
    ).text = "urn:cen.eu:en16931:2017"

# ==========================================================
# UBL Header
# ==========================================================
def build_ubl_header(root, invoice):
    etree.SubElement(root, _cbc("CustomizationID")).text = invoice.info.customization_id
    etree.SubElement(root, _cbc("ProfileID")).text = invoice.info.profile_id
    etree.SubElement(root, _cbc("ID")).text = str(invoice.info.invoice_number)
    etree.SubElement(root, _cbc("IssueDate")).text = format_date_iso(invoice.info.invoice_date)
    etree.SubElement(root, _cbc("DueDate")).text = format_date_iso(invoice.info.payment_due_date)
    etree.SubElement(root, _cbc("InvoiceTypeCode")).text = invoice.info.invoice_type_code
    etree.SubElement(root, _cbc("DocumentCurrencyCode")).text = invoice.info.currency

    #if invoice.info.delivery_instruction:
    #    etree.SubElement(root, _cbc("Note")).text = invoice.info.delivery_instruction

    if invoice.buyer.leitweg_id:
        etree.SubElement(root, _cbc("BuyerReference")).text = invoice.buyer.leitweg_id

    # -------------------------
    # Lieferschein (nur Nummer!)
    # -------------------------
    if invoice.info.delivery_note:
        despatch = etree.SubElement(root, _cac("DespatchDocumentReference"))
        etree.SubElement(despatch, _cbc("ID")).text = invoice.info.delivery_note

    # InvoicePeriod nur, wenn kein Lieferschein
    if not invoice.info.delivery_note:
        end_date = format_date_iso(invoice.info.invoice_date)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=30)

        period = etree.SubElement(root, _cac("InvoicePeriod"))
        etree.SubElement(period, _cbc("StartDate")).text = start_dt.strftime("%Y-%m-%d")
        etree.SubElement(period, _cbc("EndDate")).text = end_date

# ==========================================================
# Delivery (BT-70–BT-80)
# ==========================================================
def build_delivery(root, invoice):
    has_delivery_address = bool(
        not invoice.buyer.use_invoice_address_as_delivery
        and invoice.delivery
        and invoice.delivery.street
        and invoice.delivery.postcode
        and invoice.delivery.city
    )

    # Kein leeres Delivery-Element erzeugen.
    if not invoice.info.delivery_date and not has_delivery_address:
        return

    delivery = etree.SubElement(root, _cac("Delivery"))

    # BT-72 Lieferdatum
    if invoice.info.delivery_date:
        etree.SubElement(
            delivery,
            _cbc("ActualDeliveryDate")
        ).text = format_date_iso(invoice.info.delivery_date)

    # -------------------------
    # DeliveryLocation zuerst
    # -------------------------
    if has_delivery_address:
        location = etree.SubElement(delivery, _cac("DeliveryLocation"))
        addr = etree.SubElement(location, _cac("Address"))
        etree.SubElement(addr, _cbc("StreetName")).text = invoice.delivery.street
        etree.SubElement(addr, _cbc("CityName")).text = invoice.delivery.city
        etree.SubElement(addr, _cbc("PostalZone")).text = invoice.delivery.postcode

        country = etree.SubElement(addr, _cac("Country"))
        etree.SubElement(country, _cbc("IdentificationCode")).text = invoice.delivery.country or "DE"

        # -------------------------
        # DeliveryParty danach
        # -------------------------
        party = etree.SubElement(delivery, _cac("DeliveryParty"))

        # Empfängername
        if invoice.delivery.name:
            pname = etree.SubElement(party, _cac("PartyName"))
            etree.SubElement(pname, _cbc("Name")).text = invoice.delivery.name

# ==========================================================
# Supplier
# ==========================================================
def build_supplier(root, invoice):
    supplier = etree.SubElement(root, _cac("AccountingSupplierParty"))
    party = etree.SubElement(supplier, _cac("Party"))

    if invoice.seller.email:
        etree.SubElement(party, _cbc("EndpointID"), schemeID="EM").text = invoice.seller.email

    if invoice.seller.supplier_number:
        identification = etree.SubElement(party, _cac("PartyIdentification"))
        etree.SubElement(identification, _cbc("ID")).text = invoice.seller.supplier_number

    postal = etree.SubElement(party, _cac("PostalAddress"))
    etree.SubElement(postal, _cbc("StreetName")).text = invoice.seller.street
    etree.SubElement(postal, _cbc("CityName")).text = invoice.seller.city
    etree.SubElement(postal, _cbc("PostalZone")).text = invoice.seller.postcode

    country = etree.SubElement(postal, _cac("Country"))
    etree.SubElement(country, _cbc("IdentificationCode")).text = invoice.seller.country or "DE"

    if invoice.seller.vat:
        tax = etree.SubElement(party, _cac("PartyTaxScheme"))
        etree.SubElement(tax, _cbc("CompanyID")).text = invoice.seller.vat
        scheme = etree.SubElement(tax, _cac("TaxScheme"))
        etree.SubElement(scheme, _cbc("ID")).text = "VAT"

    if invoice.seller.tax_number:
        tax = etree.SubElement(party, _cac("PartyTaxScheme"))
        etree.SubElement(tax, _cbc("CompanyID")).text = invoice.seller.tax_number
        scheme = etree.SubElement(tax, _cac("TaxScheme"))
        etree.SubElement(scheme, _cbc("ID")).text = "FC"

    legal = etree.SubElement(party, _cac("PartyLegalEntity"))
    etree.SubElement(legal, _cbc("RegistrationName")).text = invoice.seller.name
    if invoice.seller.registry_number:
        etree.SubElement(legal, _cbc("CompanyID")).text = invoice.seller.registry_number

    if any([invoice.seller.contact_name, invoice.seller.phone, invoice.seller.email]):
        contact = etree.SubElement(party, _cac("Contact"))
        etree.SubElement(contact, _cbc("Name")).text = (
            invoice.seller.contact_name or invoice.seller.name
        )
        if invoice.seller.phone:
            etree.SubElement(contact, _cbc("Telephone")).text = invoice.seller.phone
        if invoice.seller.email:
            etree.SubElement(contact, _cbc("ElectronicMail")).text = invoice.seller.email

# ==========================================================
# Customer (Buyer)
# ==========================================================
def build_customer(root, invoice):
    customer = etree.SubElement(root, _cac("AccountingCustomerParty"))
    party = etree.SubElement(customer, _cac("Party"))

    if invoice.buyer.email:
        etree.SubElement(party, _cbc("EndpointID"), schemeID="EM").text = invoice.buyer.email

    # Kundennummer
    if invoice.buyer.customer_number:
        pid = etree.SubElement(party, _cac("PartyIdentification"))
        etree.SubElement(pid, _cbc("ID")).text = invoice.buyer.customer_number

    postal = etree.SubElement(party, _cac("PostalAddress"))
    etree.SubElement(postal, _cbc("StreetName")).text = invoice.buyer.street
    etree.SubElement(postal, _cbc("CityName")).text = invoice.buyer.city
    etree.SubElement(postal, _cbc("PostalZone")).text = invoice.buyer.postcode

    country = etree.SubElement(postal, _cac("Country"))
    etree.SubElement(country, _cbc("IdentificationCode")).text = invoice.buyer.country or "DE"

    if invoice.buyer.vat:
        tax = etree.SubElement(party, _cac("PartyTaxScheme"))
        etree.SubElement(tax, _cbc("CompanyID")).text = invoice.buyer.vat
        scheme = etree.SubElement(tax, _cac("TaxScheme"))
        etree.SubElement(scheme, _cbc("ID")).text = "VAT"

    if invoice.buyer.tax_number:
        tax = etree.SubElement(party, _cac("PartyTaxScheme"))
        etree.SubElement(tax, _cbc("CompanyID")).text = invoice.buyer.tax_number
        scheme = etree.SubElement(tax, _cac("TaxScheme"))
        etree.SubElement(scheme, _cbc("ID")).text = "FC"

    legal = etree.SubElement(party, _cac("PartyLegalEntity"))
    etree.SubElement(legal, _cbc("RegistrationName")).text = invoice.buyer.name
    if invoice.buyer.registry_number:
        etree.SubElement(legal, _cbc("CompanyID")).text = invoice.buyer.registry_number

    # Abteilung / Ansprechpartner
    if invoice.buyer.contact_name:
        contact = etree.SubElement(party, _cac("Contact"))
        etree.SubElement(contact, _cbc("Name")).text = invoice.buyer.contact_name
        if invoice.buyer.phone:
            etree.SubElement(contact, _cbc("Telephone")).text = invoice.buyer.phone
        if invoice.buyer.email:
            etree.SubElement(contact, _cbc("ElectronicMail")).text = invoice.buyer.email

# ==========================================================
# Payment
# ==========================================================
def build_payment_means(root, invoice):
    pm = etree.SubElement(root, _cac("PaymentMeans"))
    etree.SubElement(pm, _cbc("PaymentMeansCode")).text = invoice.payment.payment_means_code

    acc = etree.SubElement(pm, _cac("PayeeFinancialAccount"))
    etree.SubElement(acc, _cbc("ID")).text = invoice.payment.iban
    etree.SubElement(acc, _cbc("Name")).text = invoice.payment.account_holder

    branch = etree.SubElement(acc, _cac("FinancialInstitutionBranch"))
    etree.SubElement(branch, _cbc("ID")).text = invoice.payment.bic

def build_payment_terms(root, invoice):
    if invoice.payment.payment_terms:
        terms = etree.SubElement(root, _cac("PaymentTerms"))
        etree.SubElement(terms, _cbc("Note")).text = invoice.payment.payment_terms

# ==========================================================
# Invoice Lines
# ==========================================================
def build_invoice_lines(root, invoice):
    for item in invoice.items:
        line = etree.SubElement(root, _cac("InvoiceLine"))
        etree.SubElement(line, _cbc("ID")).text = str(item.pos)

        etree.SubElement(
            line,
            _cbc("InvoicedQuantity"),
            unitCode=item.unit or "C62"
        ).text = format_iso(item.qty)

        etree.SubElement(
            line,
            _cbc("LineExtensionAmount"),
            currencyID=invoice.info.currency
        ).text = format_iso(item.net)

        item_el = etree.SubElement(line, _cac("Item"))

        if item.description:
            etree.SubElement(item_el, _cbc("Description")).text = item.description

        etree.SubElement(item_el, _cbc("Name")).text = item.name

        # -------------------------
        # Steuer / TaxCategory
        # -------------------------
        tax = etree.SubElement(item_el, _cac("ClassifiedTaxCategory"))
        # ID = Steuerkategorie (z.B. "S")
        etree.SubElement(tax, _cbc("ID")).text = item.tax_category or "S"
        # Percent = Steuersatz (Decimal korrekt formatiert)
        etree.SubElement(tax, _cbc("Percent")).text = format_percent(item.vat)
        # TaxScheme immer "VAT"
        scheme = etree.SubElement(tax, _cac("TaxScheme"))
        etree.SubElement(scheme, _cbc("ID")).text = "VAT"

        price = etree.SubElement(line, _cac("Price"))
        etree.SubElement(
            price,
            _cbc("PriceAmount"),
            currencyID=invoice.info.currency
        ).text = format_iso(item.price)

# ==========================================================
# Tax Total
# ==========================================================
def build_tax_total(root, invoice):
    tax_total = etree.SubElement(root, _cac("TaxTotal"))

    total_tax = sum(t.amount for t in getattr(invoice, 'taxtotal', []))
    etree.SubElement(
        tax_total,
        _cbc("TaxAmount"),
        currencyID=invoice.info.currency
    ).text = format_iso(total_tax)

    for tax in getattr(invoice, 'taxtotal', []):
        sub = etree.SubElement(tax_total, _cac("TaxSubtotal"))

        etree.SubElement(
            sub,
            _cbc("TaxableAmount"),
            currencyID=invoice.info.currency
        ).text = format_iso(tax.taxable_amount)

        etree.SubElement(
            sub,
            _cbc("TaxAmount"),
            currencyID=invoice.info.currency
        ).text = format_iso(tax.amount)

        cat = etree.SubElement(sub, _cac("TaxCategory"))
        etree.SubElement(cat, _cbc("ID")).text = tax.tax_category
        etree.SubElement(cat, _cbc("Percent")).text = format_percent(tax.percent)

        scheme = etree.SubElement(cat, _cac("TaxScheme"))
        etree.SubElement(scheme, _cbc("ID")).text = "VAT"

# ==========================================================
# Legal Monetary Total
# ==========================================================
def build_legal_monetary_total(root, invoice):
    mt = invoice.monetarytotal
    total = etree.SubElement(root, _cac("LegalMonetaryTotal"))

    etree.SubElement(
        total,
        _cbc("LineExtensionAmount"),
        currencyID=invoice.info.currency
    ).text = format_iso(mt.line_extension_amount)

    etree.SubElement(
        total,
        _cbc("TaxExclusiveAmount"),
        currencyID=invoice.info.currency
    ).text = format_iso(mt.tax_exclusive_amount)

    etree.SubElement(
        total,
        _cbc("TaxInclusiveAmount"),
        currencyID=invoice.info.currency
    ).text = format_iso(mt.tax_inclusive_amount)

    etree.SubElement(
        total,
        _cbc("PayableAmount"),
        currencyID=invoice.info.currency
    ).text = format_iso(mt.payable_amount)

# ==========================================================
# XML erzeugen
# ==========================================================
def create_xml(invoice: Invoice, output_filename: str | None = None, include_extensions: bool = False) -> bytes:
    # Sicherstellen, dass Summen / Steuerwerte aktuell sind
    invoice.calculate(force=True)

    root = etree.Element(
        "Invoice",
        nsmap=NSMAP,
        attrib={
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation":
            f"{NSMAP[None]} UBL-Invoice-2.1.xsd"
        }
    )

    BUILD_ORDER = [
        (build_extensions, include_extensions),
        (build_ubl_header, True),
        (build_supplier, True),
        (build_customer, True),
        (build_delivery, True),
        (build_payment_means, True),
        (build_payment_terms, True),
        (build_tax_total, True),
        (build_legal_monetary_total, True),
        (build_invoice_lines, True),
    ]

    for builder, enabled in BUILD_ORDER:
        if enabled:
            builder(root, invoice)

    xml_bytes = etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="utf-8"
    )

    if output_filename:
        with open(output_filename, "wb") as f:
            f.write(xml_bytes)

    return xml_bytes
