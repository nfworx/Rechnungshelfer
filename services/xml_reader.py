# xml_reader.py

import xml.etree.ElementTree as ET
from decimal import Decimal
from datetime import datetime

from models import (
    Seller,
    Buyer,
    Delivery,
    InvoiceInfo,
    Payment,
    Invoice,
    InvoiceItem,
    TaxTotal,
    MonetaryTotal,
    CalculationMode,
)


class InvoiceParsingError(Exception):
    pass


def txt(el, path, ns):
    if el is None:
        return ""
    node = el.find(path, ns)
    return node.text.strip() if node is not None and node.text else ""


def first_txt(el, paths, ns):
    for path in paths:
        value = txt(el, path, ns)
        if value:
            return value
    return ""


def parse_de(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value

    s = str(value).strip()
    if not s:
        return Decimal("0.00")

    if "," in s:
        s = s.replace(".", "").replace(",", ".")

    try:
        return Decimal(s)
    except Exception:
        return Decimal("0.00")


def format_date_de(date_str):
    if not date_str:
        return ""

    date_str = str(date_str).strip()

    formats = [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%Y%m%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%d.%m.%Y")
        except ValueError:
            pass

    return date_str


def read_xml_file(filepath) -> Invoice:
    ns = {
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    }

    try:
        root = ET.parse(filepath).getroot()
    except ET.ParseError as e:
        raise InvoiceParsingError(f"XML-Datei ungültig: {e}")

    # =========================
    # Seller
    # =========================
    supplier = root.find("./cac:AccountingSupplierParty/cac:Party", ns)
    if supplier is None:
        raise InvoiceParsingError("Kein Supplier gefunden")

    seller_vat = ""
    seller_tax = ""

    for scheme in supplier.findall("cac:PartyTaxScheme", ns):
        scheme_id = txt(scheme, "cac:TaxScheme/cbc:ID", ns).upper()
        company_id = txt(scheme, "cbc:CompanyID", ns)

        if scheme_id == "VAT":
            seller_vat = company_id
        else:
            seller_tax = company_id

    seller = Seller(
        name=first_txt(supplier, [
            "cac:PartyLegalEntity/cbc:RegistrationName",
            "cac:PartyName/cbc:Name",
        ], ns),
        street=txt(supplier, "cac:PostalAddress/cbc:StreetName", ns),
        postcode=txt(supplier, "cac:PostalAddress/cbc:PostalZone", ns),
        city=txt(supplier, "cac:PostalAddress/cbc:CityName", ns),
        country=txt(supplier, "cac:PostalAddress/cac:Country/cbc:IdentificationCode", ns) or "DE",
        phone=txt(supplier, "cac:Contact/cbc:Telephone", ns),
        email=first_txt(supplier, [
            "cac:Contact/cbc:ElectronicMail",
            "cbc:EndpointID",
        ], ns),
        vat=seller_vat,
        tax_number=seller_tax,
        registry_number=txt(supplier, "cac:PartyLegalEntity/cbc:CompanyID", ns),
        contact_name=txt(supplier, "cac:Contact/cbc:Name", ns),
        supplier_number=txt(supplier, "cac:PartyIdentification/cbc:ID", ns),
    )

    # =========================
    # Buyer
    # =========================
    customer_party_node = root.find("./cac:AccountingCustomerParty", ns)
    customer = root.find("./cac:AccountingCustomerParty/cac:Party", ns)

    if customer is None:
        raise InvoiceParsingError("Kein Buyer gefunden")

    buyer_vat = ""
    buyer_tax = ""
    for scheme in customer.findall("cac:PartyTaxScheme", ns):
        scheme_id = txt(scheme, "cac:TaxScheme/cbc:ID", ns).upper()
        company_id = txt(scheme, "cbc:CompanyID", ns)
        if scheme_id == "VAT":
            buyer_vat = company_id
        else:
            buyer_tax = company_id

    buyer = Buyer(
        name=first_txt(customer, [
            "cac:PartyLegalEntity/cbc:RegistrationName",
            "cac:PartyName/cbc:Name",
        ], ns),
        street=txt(customer, "cac:PostalAddress/cbc:StreetName", ns),
        postcode=txt(customer, "cac:PostalAddress/cbc:PostalZone", ns),
        city=txt(customer, "cac:PostalAddress/cbc:CityName", ns),
        country=txt(customer, "cac:PostalAddress/cac:Country/cbc:IdentificationCode", ns) or "DE",
        leitweg_id=txt(root, "./cbc:BuyerReference", ns),
        email=first_txt(customer, [
            "cac:Contact/cbc:ElectronicMail",
            "cbc:EndpointID",
        ], ns),
        contact_name=txt(customer, "cac:Contact/cbc:Name", ns),
        customer_number=first_txt(customer_party_node, [
            "cbc:CustomerAssignedAccountID",
            "cac:Party/cac:PartyIdentification/cbc:ID",
        ], ns),
        phone=txt(customer, "cac:Contact/cbc:Telephone", ns),
        vat=buyer_vat,
        tax_number=buyer_tax,
        registry_number=txt(customer, "cac:PartyLegalEntity/cbc:CompanyID", ns),
    )

    # =========================
    # Delivery / Leistungsempfänger
    # =========================
    delivery_node = root.find("./cac:Delivery", ns)
    delivery_party = root.find("./cac:Delivery/cac:DeliveryParty", ns)
    delivery_address = root.find("./cac:Delivery/cac:DeliveryLocation/cac:Address", ns)

    if delivery_node is not None:
        name = ""

        if delivery_party is not None:
            name = first_txt(delivery_party, [
                "cac:PartyLegalEntity/cbc:RegistrationName",
                "cac:PartyName/cbc:Name",
                "cbc:Name",
            ], ns)

        street = first_txt(delivery_node, [
            "./cac:DeliveryLocation/cac:Address/cbc:StreetName",
            "./cac:DeliveryParty/cac:PostalAddress/cbc:StreetName",
        ], ns)

        postcode = first_txt(delivery_node, [
            "./cac:DeliveryLocation/cac:Address/cbc:PostalZone",
            "./cac:DeliveryParty/cac:PostalAddress/cbc:PostalZone",
        ], ns)

        city = first_txt(delivery_node, [
            "./cac:DeliveryLocation/cac:Address/cbc:CityName",
            "./cac:DeliveryParty/cac:PostalAddress/cbc:CityName",
        ], ns)

        country = first_txt(delivery_node, [
            "./cac:DeliveryLocation/cac:Address/cac:Country/cbc:IdentificationCode",
            "./cac:DeliveryParty/cac:PostalAddress/cac:Country/cbc:IdentificationCode",
        ], ns) or "DE"

        delivery = Delivery(
            name=name or buyer.name,
            street=street,
            postcode=postcode,
            city=city,
            country=country,
        )

        buyer.use_invoice_address_as_delivery = False

    else:
        delivery = Delivery(
            name=buyer.name,
            street=buyer.street,
            postcode=buyer.postcode,
            city=buyer.city,
            country=buyer.country,
        )
        buyer.use_invoice_address_as_delivery = True

    delivery.update_required_fields(buyer)

    # =========================
    # Payment
    # =========================
    payment_means = root.find("./cac:PaymentMeans", ns)
    payment_node = root.find("./cac:PaymentMeans/cac:PayeeFinancialAccount", ns)

    payment = Payment(
        iban=txt(payment_node, "cbc:ID", ns),
        bic=txt(payment_node, "cac:FinancialInstitutionBranch/cbc:ID", ns),
        account_holder=txt(payment_node, "cbc:Name", ns),
        payment_means_code=txt(payment_means, "cbc:PaymentMeansCode", ns) or "58",
        payment_terms=txt(root, "./cac:PaymentTerms/cbc:Note", ns),
    )

    # =========================
    # Items
    # =========================
    items = []

    for line in root.findall("./cac:InvoiceLine", ns):
        qty_el = line.find("cbc:InvoicedQuantity", ns)
        qty_raw = qty_el.text.strip() if qty_el is not None and qty_el.text else ""
        unit = qty_el.attrib.get("unitCode", "") if qty_el is not None else ""

        discount_raw = ""
        base_amount_raw = ""

        ac = line.find("cac:Price/cac:AllowanceCharge", ns)
        if ac is not None and txt(ac, "cbc:ChargeIndicator", ns).lower() == "false":
            discount_raw = txt(ac, "cbc:Amount", ns)
            base_amount_raw = txt(ac, "cbc:BaseAmount", ns)

        price_amount = parse_de(txt(line, "cac:Price/cbc:PriceAmount", ns))
        base_amount = parse_de(base_amount_raw)

        if not base_amount:
            base_amount = price_amount + parse_de(discount_raw)

        items.append(
            InvoiceItem(
                pos=txt(line, "cbc:ID", ns),
                name=txt(line, "cac:Item/cbc:Name", ns),
                description=txt(line, "cac:Item/cbc:Description", ns),
                qty=parse_de(qty_raw),
                unit=unit or "C62",
                price=price_amount,
                discount=parse_de(discount_raw),
                vat=parse_de(txt(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent", ns)),
                net=parse_de(txt(line, "cbc:LineExtensionAmount", ns)),
                price_without_discount=base_amount,
                tax_category=txt(line, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID", ns) or "S",
            )
        )

    # =========================
    # Tax Totals
    # =========================
    tax_totals = []

    for tax_sub in root.findall("./cac:TaxTotal/cac:TaxSubtotal", ns):
        tax_totals.append(
            TaxTotal(
                amount=parse_de(txt(tax_sub, "cbc:TaxAmount", ns)),
                taxable_amount=parse_de(txt(tax_sub, "cbc:TaxableAmount", ns)),
                tax_category=txt(tax_sub, "cac:TaxCategory/cbc:ID", ns) or "S",
                percent=parse_de(txt(tax_sub, "cac:TaxCategory/cbc:Percent", ns)),
            )
        )

    # =========================
    # Monetary Total
    # =========================
    lmt = root.find("./cac:LegalMonetaryTotal", ns)

    monetary_total = MonetaryTotal(
        line_extension_amount=parse_de(txt(lmt, "cbc:LineExtensionAmount", ns)),
        tax_exclusive_amount=parse_de(txt(lmt, "cbc:TaxExclusiveAmount", ns)),
        tax_inclusive_amount=parse_de(txt(lmt, "cbc:TaxInclusiveAmount", ns)),
        payable_amount=parse_de(txt(lmt, "cbc:PayableAmount", ns)),
    )

    # =========================
    # InvoiceInfo
    # =========================
    despatch = root.find("./cac:DespatchDocumentReference", ns)

    delivery_date = first_txt(root, [
        "./cac:Delivery/cbc:ActualDeliveryDate",
        "./cac:Delivery/cac:Despatch/cbc:ActualDespatchDate",
    ], ns)

    delivery_instruction = first_txt(root, [
        "./cac:Delivery/cbc:Instructions",
        "./cbc:Note",
    ], ns)

    if despatch is not None:
        delivery_note = txt(despatch, "cbc:ID", ns)

        if not delivery_date:
            delivery_date = txt(despatch, "cbc:IssueDate", ns)

        if not delivery_instruction:
            delivery_instruction = first_txt(despatch, [
                "cbc:DocumentDescription",
                "cbc:Note",
            ], ns)
    else:
        delivery_note = ""

    info = InvoiceInfo(
        invoice_number=txt(root, "./cbc:ID", ns),
        invoice_date=format_date_de(txt(root, "./cbc:IssueDate", ns)),
        delivery_date=format_date_de(delivery_date),
        payment_due_date=format_date_de(txt(root, "./cbc:DueDate", ns)),
        currency=txt(root, "./cbc:DocumentCurrencyCode", ns) or "EUR",
        invoice_type_code=txt(root, "./cbc:InvoiceTypeCode", ns) or "380",
        delivery_note=delivery_note,
        delivery_instruction=delivery_instruction,
        customization_id=txt(root, "./cbc:CustomizationID", ns) or None,
        profile_id=txt(root, "./cbc:ProfileID", ns) or None,
    )

    invoice = Invoice(
        seller=seller,
        buyer=buyer,
        delivery=delivery,
        info=info,
        payment=payment,
        items=items,
        taxtotal=tax_totals,
        monetarytotal=monetary_total,
    )

    invoice.calculation_mode = CalculationMode.IMPORTED

    invoice.validate_calculation()
    invoice.calculate(force=False)

    return invoice
