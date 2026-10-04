"""Abbildung gespeicherter Rechnungsdaten auf durchsuchbare DB-Spalten."""


def invoice_summary_from_data(data: dict) -> dict[str, str]:
    buyer = data.get("buyer", {})
    seller = data.get("seller", {})
    info = data.get("info", {})
    monetarytotal = data.get("monetarytotal", {})
    invoice_type_code = str(info.get("invoice_type_code", "380"))
    document_type = data.get("document_type") or (
        "self_billed_invoice" if invoice_type_code == "389" else "invoice"
    )
    counterparty = seller if document_type == "self_billed_invoice" else buyer
    return {
        "document_type": document_type,
        "counterparty_name": counterparty.get("name", ""),
        "buyer_name": buyer.get("name", ""),
        "customer_number": buyer.get("customer_number", ""),
        "supplier_number": seller.get("supplier_number", ""),
        "invoice_date": info.get("invoice_date", ""),
        "payable_amount": monetarytotal.get("payable_amount") or "0.00",
    }
