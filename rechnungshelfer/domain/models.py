from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from datetime import date, timedelta

from .calculation import (
    TaxLine,
    calculate_invoice,
    calculate_line,
)


DEFAULT_BUYER_REFERENCE = "BUCHHALTUNG"

# =========================
# Hilfsfunktionen
# =========================
def to_decimal(value):
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    s = str(value).strip()
    if not s:
        return Decimal("0.0")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s)

# =========================
# Enums
# =========================
class CalculationMode(Enum):
    AUTO = "auto"
    IMPORTED = "imported"
    MANUAL = "manual"


class DocumentType(Enum):
    INVOICE = "invoice"
    SELF_BILLED_INVOICE = "self_billed_invoice"

    @property
    def invoice_type_code(self) -> str:
        return "389" if self is DocumentType.SELF_BILLED_INVOICE else "380"

    @property
    def label(self) -> str:
        if self is DocumentType.SELF_BILLED_INVOICE:
            return "Gutschrift (Abrechnung durch Käufer)"
        return "Rechnung"

    @classmethod
    def from_value(cls, value, invoice_type_code="380"):
        if isinstance(value, cls):
            return value
        if value:
            try:
                return cls(str(value))
            except ValueError:
                pass
        if str(invoice_type_code or "380") == "389":
            return cls.SELF_BILLED_INVOICE
        return cls.INVOICE

class Unit(Enum):
    C62 = "Stk"; H87 = "Stk"; EA = "Stk"
    KGM = "kg"; GRM = "g"; TNE = "t"
    LTR = "l"; MTQ = "m³"
    MTR = "m"; MTK = "m²"
    HUR = "Std"; MIN = "Min"; DAY = "Tag"; WEE = "Woche"; MON = "Monat"; ANN = "Jahr"
    LS = "Leistung"

    @property
    def label(self) -> str:
        return self.value

# =========================
# Base-Klasse
# =========================
class Validatable:
    required_fields: list = []

    def is_valid(self):
        return all(bool(getattr(self, f, None)) for f in self.required_fields)

    def get_label(self, field):
        # Default-Fallback, falls keine Übersetzung vorhanden
        return field.replace("_", " ").title()

# =========================
# Seller / Buyer
# =========================
class Seller(Validatable):
    required_fields = ["name", "street", "postcode", "city", "country", "vat", "registry_number", "email", "contact_name"]
    readonly_fields = ["country"]
    FIELD_LABELS_DE = {
        "name": "Name",
        "street": "Straße",
        "postcode": "PLZ",
        "city": "Ort",
        "country": "Land",
        "vat": "USt-IdNr.",
        "registry_number": "Handelsregisternummer",
        "email": "E-Mail",
        "contact_name": "Kontaktperson",
        "phone": "Telefon",
        "tax_number": "Steuernummer",
        "supplier_number": "GeschÃ¤ftspartnernummer",
        "buyer_reference": "Käuferreferenz (BT-10)",
    }

    def __init__(self, name="Musterfirma", street="Musterstraße 10", postcode="12345", city="Musterhausen", country="DE",
                 phone="+49 1234 567890", email="info@musterfirma.de", vat="DE123456789",
                 tax_number="12/345/67890", registry_number="HRB 12345",
                 contact_name="Max Mustermann", supplier_number="", buyer_reference=DEFAULT_BUYER_REFERENCE):
        self.name = name; self.street = street; self.postcode = postcode
        self.city = city; self.country = country; self.vat = vat
        self.phone = phone; self.email = email; self.tax_number = tax_number
        self.registry_number = registry_number; self.contact_name = contact_name
        self.supplier_number = supplier_number
        self.buyer_reference = buyer_reference

    def get_label(self, field):
        return self.FIELD_LABELS_DE.get(field, super().get_label(field))

class Buyer(Validatable):
    required_fields = [
        "name", "street", "postcode", "city",
        "country", "email"
    ]

    readonly_fields = ["country"]

    FIELD_LABELS_DE = {
        "name": "Name",
        "street": "Straße",
        "postcode": "PLZ",
        "city": "Ort",
        "country": "Land",
        "email": "E-Mail",
        "leitweg_id": "Käuferreferenz (BT-10)",
        "contact_name": "Ansprechpartner",
        "customer_number": "GeschÃ¤ftspartnernummer",
        "phone": "Telefon",
        "vat": "USt-IdNr.",
        "tax_number": "Steuernummer",
        "registry_number": "Handelsregisternummer",
    }

    def __init__(
        self,
        name="",
        street="",
        postcode="",
        city="",
        country="DE",
        leitweg_id="",
        email="",
        contact_name="",
        customer_number="",
        use_invoice_address_as_delivery=False,
        phone="",
        vat="",
        tax_number="",
        registry_number=""
    ):
        self.name = name
        self.street = street
        self.postcode = postcode
        self.city = city
        self.country = country
        self.leitweg_id = leitweg_id
        self.email = email
        self.contact_name = contact_name
        self.customer_number = customer_number
        self.phone = phone
        self.vat = vat
        self.tax_number = tax_number
        self.registry_number = registry_number
        if isinstance(use_invoice_address_as_delivery, str):
            use_invoice_address_as_delivery = (
                use_invoice_address_as_delivery.strip().lower()
                in ("true", "1", "yes", "ja")
            )
        self.use_invoice_address_as_delivery = bool(use_invoice_address_as_delivery)

    def get_label(self, field):
        return self.FIELD_LABELS_DE.get(field, super().get_label(field))
    
    def to_dict(self):
        """
        Gibt alle Attribute des Buyers als dict zurück, 
        Decimal-Felder werden in Strings umgewandelt
        """
        result = {}
        for k, v in self.__dict__.items():
            if isinstance(v, Decimal):
                result[k] = str(v)
            else:
                result[k] = v
        return result

    @classmethod
    def from_dict(cls, data: dict):
        """
        Baut ein Buyer-Objekt aus einem dict wieder auf.
        """
        # Decimal-Felder ggf. zurückwandeln
        decimal_fields = []  # Falls du in Zukunft Decimal-Felder im Buyer hast
        for f in decimal_fields:
            if f in data:
                data[f] = Decimal(str(data[f]))
        return cls(**data)


class Delivery(Validatable):
    required_fields = []
    readonly_fields = ["country"]

    FIELD_LABELS_DE = {
        "name": "Leistungsempfänger",
        "street": "Straße",
        "postcode": "PLZ",
        "city": "Ort",
        "country": "Land",
    }

    def __init__(
        self,
        name="",
        street="",
        postcode="",
        city="",
        country=""
    ):
        # Eigene Instanz-Liste, damit required_fields nicht ungewollt zwischen Objekten geteilt wird
        self.required_fields = []

        self.name = name
        self.street = street
        self.postcode = postcode
        self.city = city
        self.country = country
    
    def update_required_fields(self, buyer: Buyer):
        if not buyer.use_invoice_address_as_delivery:
            self.required_fields = ["name", "street", "postcode", "city", "country"]
            self.country = "DE"
        else:
            self.required_fields = []
            self.country = ""

    def get_label(self, field):
        return self.FIELD_LABELS_DE.get(field, super().get_label(field))
    
# =========================
# InvoiceItem
# =========================
class InvoiceItem(Validatable):
    required_fields = ["pos", "name", "qty", "unit", "price_without_discount", "net", "vat", "tax_category"]
    readonly_fields = ["net", "price", "pos"]

    FIELD_LABELS_DE = {
        "pos": "Pos.",
        "name": "Bezeichnung",
        "description": "Beschreibung",
        "qty": "Menge",
        "unit": "Einheit",
        "price": "Preis",
        "discount": "Rabatt",
        "vat": "MwSt %",
        "net": "Netto",
        "price_without_discount": "Preis ohne Rabatt",
        "tax_category": "Steuerkategorie"
    }

    # -------------------------
    # MwSt Optionen
    # -------------------------
    VAT_OPTIONS = [
        {"id": "Z", "percent": Decimal("0.00"), "label": "0 %"},
        {"id": "S", "percent": Decimal("19.00"), "label": "19 %"},
        {"id": "S", "percent": Decimal("7.00"), "label": "7 %"},
        {"id": "S", "percent": Decimal("7.80"), "label": "7,8 %"}
    ]

    def __init__(self, pos="", name="", description="", qty="1", unit="C62",
                 price="0.0", discount="0.0", vat="19.0", net="0.0", price_without_discount="0.0", tax_category="S"):
        self.pos = pos
        self.name = name
        self.description = description
        self.unit = unit
        self.tax_category = tax_category
        self.qty = to_decimal(qty)
        self.price = to_decimal(price)
        self.discount = to_decimal(discount)
        self.vat = to_decimal(vat)
        self.net = to_decimal(net)
        self.price_without_discount = to_decimal(price_without_discount)
        self.recalculate()

    def recalculate(self):
        result = calculate_line(
            self.price_without_discount,
            self.discount,
            self.qty,
        )
        self.price = result.price
        self.net = result.net

    def set_vat(self, value):
        self.vat = to_decimal(value)
        matching_option = next(
            (option for option in self.VAT_OPTIONS if option["percent"] == self.vat),
            None,
        )
        if matching_option:
            self.tax_category = matching_option["id"]
        self.recalculate()

    def get_label(self, field):
        return self.FIELD_LABELS_DE.get(field, super().get_label(field))

# =========================
# InvoiceInfo
# =========================
class InvoiceInfo(Validatable):
    required_fields = ["invoice_number","invoice_date","payment_due_date","currency","customization_id","profile_id","invoice_type_code"]
    readonly_fields = ["customization_id", "profile_id", "invoice_type_code", "currency"]

    FIELD_LABELS_DE = {
        "invoice_number": "Rechnungsnummer",
        "invoice_date": "Rechnungsdatum",
        "delivery_date": "Lieferdatum",
        "payment_due_date": "Zahlungsziel",
        "currency": "Währung",
        "invoice_type_code": "Rechnungsart",
        "delivery_note": "Lieferschein",
        "delivery_instruction": "Lieferhinweis",
        "customization_id": "Custom-ID",
        "profile_id": "Profil-ID",
    }

    def __init__(self, invoice_number="", invoice_date=None,
                 delivery_date="",
                 payment_due_date=None, currency="EUR", invoice_type_code="380",
                 delivery_note="", customization_id=None, profile_id=None, delivery_instruction=""):
        
        # Wichtig: date.today() nicht als Default-Parameter verwenden,
        # sonst bleibt das Datum ab Programmstart gleich.
        if invoice_date is None:
            invoice_date = date.today().strftime("%d.%m.%Y")

        if payment_due_date is None:
            payment_due_date = (date.today() + timedelta(days=14)).strftime("%d.%m.%Y")

        self.invoice_number = invoice_number; self.invoice_date = invoice_date
        self.delivery_date = delivery_date; self.payment_due_date = payment_due_date
        self.currency = currency; self.invoice_type_code = invoice_type_code
        self.delivery_note = delivery_note
        self.delivery_instruction = delivery_instruction
        self.customization_id = customization_id or "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
        self.profile_id = profile_id or "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

    def get_label(self, field):
        return self.FIELD_LABELS_DE.get(field, super().get_label(field))

# =========================
# Payment
# =========================
class Payment(Validatable):
    required_fields = ["iban","bic","account_holder","payment_means_code","payment_terms"]
    readonly_fields = ["payment_means_code"]
    FIELD_LABELS_DE = {
        "iban": "IBAN",
        "bic": "BIC",
        "account_holder": "Kontoinhaber",
        "payment_means_code": "Zahlungsart",
        "payment_terms": "Zahlungsbedingungen"
    }

    def __init__(self, iban="DE89370400440532013000", bic="COBADEFFXXX", account_holder="Musterfirma",
                 payment_means_code="58", payment_terms="Zahlbar innerhalb von 14 Tagen netto"):
        self.iban = iban; self.bic = bic; self.account_holder = account_holder
        self.payment_means_code = payment_means_code; self.payment_terms = payment_terms

    def get_label(self, field):
        return self.FIELD_LABELS_DE.get(field, super().get_label(field))

# =========================
# TaxTotal & MonetaryTotal
# =========================
class TaxTotal:
    FIELD_LABELS_DE = {
        "amount": "MwSt-Betrag",
        "taxable_amount": "Bemessungsgrundlage",
        "tax_category": "Steuerkategorie",
        "percent": "Steuersatz (%)"
    }
    readonly_fields = ["amount", "taxable_amount", "percent", "tax_category"]

    def __init__(self, amount=Decimal("0.0"), taxable_amount=Decimal("0.0"), tax_category="S", percent=Decimal("19.0")):
        self.amount = to_decimal(amount)
        self.taxable_amount = to_decimal(taxable_amount)
        self.tax_category = tax_category
        self.percent = to_decimal(percent)

    def get_label(self, field):
        return self.FIELD_LABELS_DE.get(field, field.replace("_", " ").title())


class MonetaryTotal:
    FIELD_LABELS_DE = {
        "line_extension_amount": "Zwischensumme",
        "tax_exclusive_amount": "Summe ohne MwSt",
        "tax_inclusive_amount": "Summe inkl. MwSt",
        "payable_amount": "Zu zahlender Betrag"
    }
    readonly_fields = ["line_extension_amount", "tax_exclusive_amount", "tax_inclusive_amount", "payable_amount"]



    def __init__(self, line_extension_amount=Decimal("0.0"), tax_exclusive_amount=Decimal("0.0"),
                 tax_inclusive_amount=Decimal("0.0"), payable_amount=Decimal("0.0")):
        self.line_extension_amount = to_decimal(line_extension_amount)
        self.tax_exclusive_amount = to_decimal(tax_exclusive_amount)
        self.tax_inclusive_amount = to_decimal(tax_inclusive_amount)
        self.payable_amount = to_decimal(payable_amount)

    def get_label(self, field):
        return self.FIELD_LABELS_DE.get(field, field.replace("_", " ").title())

# =========================
# Invoice
# =========================
class Invoice:
    def __init__(self, seller: Seller, buyer: Buyer, delivery: Delivery, info: InvoiceInfo,
                 payment: Payment, items: list,
                 taxtotal=None, monetarytotal=None,
                 document_type=None):
        self.seller = seller
        self.buyer = buyer
        self.delivery = delivery
        self.info = info
        self.payment = payment
        self.items = items
        self.taxtotal = taxtotal if taxtotal is not None else []
        self.monetarytotal = monetarytotal if monetarytotal is not None else MonetaryTotal()
        self.calculation_mode = CalculationMode.AUTO
        self.validation_warnings = []
        self.document_type = DocumentType.from_value(
            document_type,
            self.info.invoice_type_code,
        )
        self.info.invoice_type_code = self.document_type.invoice_type_code
        self._update_required_fields_for_document_type()

    def _update_required_fields_for_document_type(self):
        self.seller.required_fields = list(Seller.required_fields)
        self.buyer.required_fields = list(Buyer.required_fields)
        self.payment.required_fields = list(Payment.required_fields)

        if self.document_type is DocumentType.SELF_BILLED_INVOICE:
            self.seller.required_fields = [
                "name", "street", "postcode", "city", "country", "email"
            ]
            self.buyer.required_fields = [
                "name", "street", "postcode", "city", "country", "email", "leitweg_id"
            ]
            self.payment.required_fields = [
                "iban", "bic", "account_holder", "payment_means_code"
            ]

    @property
    def is_self_billed(self) -> bool:
        return self.document_type is DocumentType.SELF_BILLED_INVOICE

    def set_document_type(self, document_type):
        self.document_type = DocumentType.from_value(document_type)
        self.info.invoice_type_code = self.document_type.invoice_type_code
        self._update_required_fields_for_document_type()

    def set_use_invoice_address_as_delivery(self, enabled):
        """Schaltet zwischen Rechnungsanschrift und eigener Lieferadresse um."""
        self.buyer.use_invoice_address_as_delivery = bool(enabled)
        if enabled:
            self._copy_buyer_address_to_delivery()
        self.delivery.update_required_fields(self.buyer)

    def replace_buyer(self, buyer: Buyer):
        """Ersetzt den Kunden und synchronisiert eine gekoppelte Lieferadresse."""
        self.buyer = buyer
        self.delivery.update_required_fields(self.buyer)
        if self.buyer.use_invoice_address_as_delivery:
            self._copy_buyer_address_to_delivery()

    def _copy_buyer_address_to_delivery(self):
        self.delivery.name = self.buyer.name
        self.delivery.street = self.buyer.street
        self.delivery.postcode = self.buyer.postcode
        self.delivery.city = self.buyer.city
        self.delivery.country = self.buyer.country

    # -------------------------
    # Berechnung
    # -------------------------
    def calculate(self, force=False):
        if self.calculation_mode == CalculationMode.IMPORTED and not force:
            return

        # Alle Positionen vor der Summenbildung neu berechnen
        for item in self.items:
            item.recalculate()

        result = calculate_invoice(
            TaxLine(
                net=item.net,
                vat_percent=item.vat,
                tax_category=item.tax_category,
            )
            for item in self.items
        )

        for item, tax_category in zip(self.items, result.tax_categories):
            item.tax_category = tax_category

        self.taxtotal = [
            TaxTotal(
                amount=group.amount,
                taxable_amount=group.taxable_amount,
                tax_category=group.tax_category,
                percent=group.percent,
            )
            for group in result.tax_groups
        ]

        self.monetarytotal.line_extension_amount = result.line_extension_amount
        self.monetarytotal.tax_exclusive_amount = result.tax_exclusive_amount
        self.monetarytotal.tax_inclusive_amount = result.tax_inclusive_amount
        self.monetarytotal.payable_amount = result.payable_amount

        # Berechnung abgeschlossen
        self.calculation_mode = CalculationMode.AUTO
        
    # -------------------------
    # VAT Properties
    # -------------------------
    @property
    def vat_sum_19(self):
        return next((t.amount for t in self.taxtotal if t.percent==Decimal("19.00")), Decimal("0.00"))
    @property
    def vat_sum_7(self):
        return next((t.amount for t in self.taxtotal if t.percent==Decimal("7.00")), Decimal("0.00"))
    @property
    def vat_sum_7_8(self):
        return next((t.amount for t in self.taxtotal if t.percent==Decimal("7.80")), Decimal("0.00"))

    # -------------------------
    # Validation
    # -------------------------
    def validate_calculation(self):
        warnings=[]
        def r2(v): return Decimal(v).quantize(Decimal("0.01"), ROUND_HALF_UP)
        calc_net = sum(i.net for i in self.items)
        if r2(calc_net)!=r2(self.monetarytotal.line_extension_amount):
            warnings.append(f"Netto-Abweichung: {calc_net} ≠ {self.monetarytotal.line_extension_amount}")
        calc_total = self.monetarytotal.tax_inclusive_amount
        if r2(calc_net+sum(t.amount for t in self.taxtotal)) != r2(calc_total):
            warnings.append(f"Brutto-Abweichung: {calc_net+sum(t.amount for t in self.taxtotal)} ≠ {calc_total}")
        self.validation_warnings=warnings
        return warnings

    # -------------------------
    # Required fields check
    # -------------------------
    def all_required_filled(self):
        delivery_valid = True
        if not self.buyer.use_invoice_address_as_delivery:
            delivery_valid = self.delivery.is_valid()

        return (
            self.seller.is_valid()
            and self.buyer.is_valid()
            and delivery_valid
            and self.info.is_valid()
            and self.payment.is_valid()
            and all(item.is_valid() for item in self.items)
        )

    # -------------------------
    # Serialisierung
    # -------------------------
    def to_dict(self):
        def serialize_value(v): return str(v) if isinstance(v, Decimal) else v
        return {
            "document_type": self.document_type.value,
            "seller":{k:serialize_value(v) for k,v in self.seller.__dict__.items()},
            "buyer":{k:serialize_value(v) for k,v in self.buyer.__dict__.items()},
            "delivery": {k: str(v) for k,v in self.delivery.__dict__.items()},
            "info":{k:serialize_value(v) for k,v in self.info.__dict__.items()},
            "payment":{k:serialize_value(v) for k,v in self.payment.__dict__.items()},
            "items": [
                {
                    k: serialize_value(v)
                    for k, v in i.__dict__.items()
                    if k not in ("required_fields", "readonly_fields", "FIELD_LABELS_DE")
                }
                for i in self.items
            ],
            "taxtotal":[
                {
                    "amount":str(t.amount),
                    "taxable_amount": str(t.taxable_amount),
                    "tax_category": t.tax_category,
                    "percent":str(t.percent)
                }
                for t in self.taxtotal
            ],
            "monetarytotal":{k:str(v) for k,v in self.monetarytotal.__dict__.items()}
        }

    @classmethod
    def from_dict(cls, data: dict):
        # --------------------------
        # Seller & Buyer laden
        # --------------------------
        seller_data = data.get("seller", {})
        buyer_data = data.get("buyer", {})
        buyer_data.setdefault("customer_number", "")
        buyer_data.setdefault("contact_name", "")
        buyer_data.setdefault("use_invoice_address_as_delivery", False)
        buyer_data.setdefault("country", "DE")
        
        # Nur die __init__ Parameter extrahieren
        seller_fields = Seller.__init__.__code__.co_varnames[1:Seller.__init__.__code__.co_argcount]
        buyer_fields = Buyer.__init__.__code__.co_varnames[1:Buyer.__init__.__code__.co_argcount]
        seller_params = {k: seller_data[k] for k in seller_fields if k in seller_data}
        buyer_params = {k: buyer_data[k] for k in buyer_fields if k in buyer_data}
        
        seller = Seller(**seller_params)
        buyer = Buyer(**buyer_params)

        # --------------------------
        # Delivery laden
        # --------------------------
        delivery_data = data.get("delivery", {})
        delivery_params = {k: delivery_data.get(k) for k in Delivery.__init__.__code__.co_varnames[1:]}
        delivery = Delivery(**delivery_params)
        
        # Interne Felder setzen, falls nötig
        for k, v in delivery_data.items():
            if not hasattr(delivery, k):
                setattr(delivery, k, v)

        # --------------------------
        # InvoiceInfo laden
        # --------------------------
        info_data = data.get("info", {})
        info_params = {k: info_data.get(k) for k in InvoiceInfo.__init__.__code__.co_varnames[1:]}
        info = InvoiceInfo(**info_params)

        # --------------------------
        # Payment laden
        # --------------------------
        payment_data = data.get("payment", {})
        payment_params = {k: payment_data.get(k) for k in Payment.__init__.__code__.co_varnames[1:]}
        payment = Payment(**payment_params)

        # --------------------------
        # Items laden
        # --------------------------
        allowed_item_fields = set(InvoiceItem.__init__.__code__.co_varnames[1:])
        items = []
        for i in data.get("items", []):
            i = {k: v for k, v in i.items() if k in allowed_item_fields}
            
            for f in ["qty","price","discount","net","price_without_discount","vat"]:
                if f in i:
                    i[f] = Decimal(str(i[f]))
            items.append(InvoiceItem(**i))

        # --------------------------
        # Invoice erzeugen
        # --------------------------
        document_type = DocumentType.from_value(
            data.get("document_type"),
            info.invoice_type_code,
        )
        invoice = cls(
            seller,
            buyer,
            delivery,
            info,
            payment,
            items,
            document_type=document_type,
        )
        invoice.delivery.update_required_fields(invoice.buyer)

        # --------------------------
        # Taxtotal & MonetaryTotal
        # --------------------------
        invoice.taxtotal = [
            TaxTotal(
                amount=Decimal(str(t.get("amount", "0.00"))),
                taxable_amount=Decimal(str(t.get("taxable_amount", "0.00"))),
                tax_category=t.get("tax_category", "S"),
                percent=Decimal(str(t.get("percent", "19.00")))
            )
            for t in data.get("taxtotal", [])
        ]

        mt = data.get("monetarytotal", {})
        invoice.monetarytotal = MonetaryTotal(
            **{k: Decimal(str(v)) for k,v in mt.items()}
        )

        invoice.calculate(force=True)
        return invoice
