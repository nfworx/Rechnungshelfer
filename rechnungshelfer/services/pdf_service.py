# rechnungshelfer/services/pdf_service.py
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageTemplate, Frame, Image, KeepTogether
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from rechnungshelfer.domain.models import Invoice
import os
import sys
from decimal import Decimal
from rechnungshelfer.domain.models import Unit
from pathlib import Path

# ====================
# Fonts
# ====================
def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parents[2]

    return str(base_path / relative_path)

pdfmetrics.registerFont(
    TTFont("LatinModern", resource_path("assets/fonts/LMRoman10-Regular.ttf"))
)
pdfmetrics.registerFont(
    TTFont("LatinModern-Bold", resource_path("assets/fonts/LMRoman10-Bold.ttf"))
)
font_name = 'LatinModern'

# ====================
# Styles
# ====================
styles = getSampleStyleSheet()
normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontName=font_name, fontSize=10, leading=12)
normal_style_left = ParagraphStyle('NormalLeft', parent=normal_style, alignment=0)
bold_style = ParagraphStyle('Bold', parent=normal_style, fontName=font_name + '-Bold')
footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontName=font_name, fontSize=8, leading=10)
header_right_style = ParagraphStyle('HeaderRight', parent=normal_style, alignment=2)
invoice_style = ParagraphStyle('InvoiceHeader', parent=normal_style, fontSize=12, leading=14, fontName=font_name+'-Bold')

# ====================
# HELPERS
# ====================
def de_format(value):
    """
    Decimal oder String in deutsches Format umwandeln:
    - Tausenderpunkt
    - Komma als Dezimaltrennzeichen
    - Immer 2 Nachkommastellen
    """
    if value is None or value == "":
        return ""
    try:
        d = Decimal(str(value))
        int_part, dec_part = f"{d:.2f}".split(".")
        int_part = "{:,}".format(int(int_part)).replace(",", ".")
        return f"{int_part},{dec_part}"
    except Exception:
        return str(value)


def de_percent(value):
    try:
        decimal_value = Decimal(str(value)).normalize()
        return format(decimal_value, "f").replace(".", ",")
    except Exception:
        return str(value)
    
def unit_code_to_label(code: str) -> str:
    if code in Unit.__members__:
        return Unit[code].label
    return code  # Fallback


def _pdf_parties(invoice: 'Invoice'):
    """Return the document issuer and the addressee in PDF order."""
    if invoice.is_self_billed:
        # A self-billed invoice is issued by the buyer to the supplier.
        return invoice.buyer, invoice.seller
    return invoice.seller, invoice.buyer


def _pdf_invoice_details(invoice: 'Invoice'):
    """Build the metadata shown next to the document heading."""
    seller = invoice.seller
    buyer = invoice.buyer
    info = invoice.info
    details = []

    if invoice.is_self_billed and seller.supplier_number:
        details.append(("Lieferantennummer:", seller.supplier_number))
    if not invoice.is_self_billed and buyer.customer_number:
        details.append(("Kundennummer:", buyer.customer_number))
    if not invoice.is_self_billed and buyer.leitweg_id:
        details.append(("Leitweg-ID:", buyer.leitweg_id))
    if invoice.is_self_billed:
        if seller.vat:
            details.append(("USt-ID Lieferant:", seller.vat))
        if seller.tax_number:
            details.append(("Steuernummer Lieferant:", seller.tax_number))

    details.append(("Währung:", info.currency))
    if info.payment_due_date:
        due_date_label = "Auszahlungsdatum:" if invoice.is_self_billed else "Zahlungsziel:"
        details.append((due_date_label, info.payment_due_date))

    return details


def _pdf_detail_layout(frame_width):
    """Return column widths for the two metadata blocks without overflow."""
    gutter_width = 5 * mm
    available_width = frame_width - gutter_width
    left_width = available_width * 0.46
    right_width = available_width - left_width

    return {
        "outer": [left_width, gutter_width, right_width],
        "invoice": [left_width * 0.62, left_width * 0.38],
        "delivery": [right_width * 0.62, right_width * 0.38],
    }

# ====================
# PDF-Erstellung
# ====================
def create_pdf(invoice: 'Invoice', output_filename="Rechnung.pdf"):
    seller = invoice.seller
    buyer = invoice.buyer
    delivery = invoice.delivery
    info = invoice.info
    payment = invoice.payment
    items = invoice.items
    is_self_billed = invoice.is_self_billed
    issuer, recipient = _pdf_parties(invoice)

    # ====================
    # Layout
    # ====================
    page_width, page_height = A4
    top_margin = 5 * mm
    bottom_margin = 5 * mm
    header_height = 30 * mm
    footer_height = 25 * mm

    # ====================
    # Custom Canvas mit Seitennummern
    # ====================
    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                header_footer(self, doc)
                self.draw_page_number(num_pages)
                super().showPage()
            super().save()

        def draw_page_number(self, page_count):
            page = self.getPageNumber()
            x = doc.leftMargin + doc.width
            y = 10 * mm
            self.setFont(font_name, 8)
            self.drawRightString(x, y, f"Seite {page} von {page_count}")

    # ====================
    # Header & Footer
    # ====================
    def header_footer(canvas, doc):
        y_header = page_height - top_margin
        logo_width = 24 * mm
        logo_height = 24 * mm
        logo_path = resource_path("assets/images/logo.png")
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=logo_width, height=logo_height)
        else:
            logo = Paragraph("<b>LOGO</b>", normal_style)

        sender_text = f"<b>{issuer.name}</b><br/>{issuer.street}<br/>{issuer.postcode} {issuer.city}<br/>Telefon: {issuer.phone}<br/>E-Mail: {issuer.email}"
        sender_para = Paragraph(sender_text, header_right_style)

        header_table = Table([[logo, "", sender_para]], colWidths=[logo_width, 50*mm, doc.width-logo_width-50*mm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (2,0), (2,0), 'RIGHT'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2 * mm),
            ('LINEBELOW', (0,0), (-1,0), 0.5, colors.black),
        ]))
        w, h = header_table.wrap(doc.width, header_height)
        header_table.drawOn(canvas, doc.leftMargin, y_header - h)

        # FOOTER
        y_footer = bottom_margin
        footer_left_text = f"{issuer.name}<br/>{issuer.street}<br/>{issuer.postcode} {issuer.city}<br/>Telefon: {issuer.phone}<br/>E-Mail: {issuer.email}"
        footer_left = Paragraph(footer_left_text, footer_style)
        footer_center_data = [
            ["HR-Nr.:", issuer.registry_number],
            ["USt-ID:", issuer.vat],
            ["St.-Nr.:", issuer.tax_number],
            ["IBAN:", "" if is_self_billed else payment.iban],
            ["BIC:", "" if is_self_billed else payment.bic]
        ]
        footer_center_table = Table(footer_center_data, colWidths=[15*mm, 60*mm], hAlign='LEFT')
        footer_center_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), font_name),
            ('FONTSIZE', (0,0), (-1,-1), footer_style.fontSize),
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('ALIGN', (1,0), (1,-1), 'LEFT'),
            ('TOPPADDING', (0,0), (-1,-1), 0*mm),
            ('BOTTOMPADDING', (0,0), (-1,-1), -0.75*mm),
        ]))
        footer_table = Table([[footer_left, footer_center_table, ""]], colWidths=[doc.width*0.4, doc.width*0.4, doc.width*0.2])
        footer_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEABOVE', (0,0), (-1,0), 0.5, colors.black),
        ]))
        fw, fh = footer_table.wrap(doc.width, footer_height)
        footer_table.drawOn(canvas, doc.leftMargin, y_footer)

    # -----------------------------
    # Dokument & Frame mit Header-Margin
    # -----------------------------
    doc = SimpleDocTemplate(
        str(output_filename),
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=top_margin + header_height,   # <-- Platz für Header oben freilassen
        bottomMargin=bottom_margin + footer_height  # <-- Platz für Footer unten freilassen
    )

    # Frame-Höhe automatisch berechnet
    frame_height = page_height - top_margin - header_height - bottom_margin - footer_height
    frame_y = bottom_margin + footer_height
    frame = Frame(doc.leftMargin, frame_y, doc.width, frame_height, id='normal')

    template = PageTemplate(id='rechnung', frames=[frame], onPage=header_footer)
    doc.addPageTemplates([template])

    # ====================
    # Elemente
    # ====================
    elements = []

    # Spacer für DIN-Fensterbrief
    recipient_spacer_height = max(0, 50*mm - top_margin - header_height)
    elements.append(Spacer(1, recipient_spacer_height))

    # Absender
    text = f"{issuer.name}, {issuer.street}, {issuer.postcode} {issuer.city}"
    text_width = stringWidth(text, font_name, 8)
    sender_table = Table([[text]], colWidths=[text_width], hAlign='LEFT')
    sender_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('LINEBELOW', (0,0), (-1,0), 0.5, colors.black),
        ('LEFTPADDING', (0,0), (-1,-1), 0*mm),
    ]))
    elements.append(sender_table)
    elements.append(Spacer(1, 2*mm))

    # Empfänger
    recipient_lines = [recipient.name]
    if recipient.contact_name:
        recipient_lines.append(recipient.contact_name)
    recipient_lines.append(recipient.street)
    recipient_lines.append(f"{recipient.postcode} {recipient.city}")

    recipient_text = "<br/>".join(recipient_lines)

    # Breite für das Empfängerfeld (z.B. 85 mm)
    recipient_col_width = 85 * mm
    recipient_para = Paragraph(recipient_text, normal_style)

    recipient_table = Table([[recipient_para]], colWidths=[recipient_col_width], hAlign='LEFT')
    recipient_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),    # oben ausrichten
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),    # linksbündig
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))

    elements.append(recipient_table)
    elements.append(Spacer(1, 10*mm))

    # Rechnungsüberschrift
    document_title = "Gutschrift" if is_self_billed else "Rechnung"
    elements.append(Paragraph(f"{document_title} Nr. {info.invoice_number} vom {info.invoice_date}", invoice_style))
    elements.append(Spacer(1, 2*mm))

    # -----------------------------
    # Dokumentbreite
    # -----------------------------
    detail_layout = _pdf_detail_layout(doc.width)
    left_width, gutter_width, right_width = detail_layout["outer"]

    # -----------------------------
    # Linke Tabelle: Rechnungsdetails
    # -----------------------------
    invoice_data = [
        [Paragraph(label, normal_style_left), Paragraph(value, normal_style_left)]
        for label, value in _pdf_invoice_details(invoice)
    ]

    invoice_table = Table(invoice_data, colWidths=detail_layout["invoice"])
    invoice_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 0*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0*mm),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (0,-1), 3*mm),
    ]))

    # -----------------------------
    # Rechte Tabelle: Lieferdatum, Lieferschein, Leistungsempfänger
    # -----------------------------
    right_rows = []

    # Liefer-/Leistungsdatum
    if info.delivery_date:
        right_rows.append([
            Paragraph("Liefer-/Leistungsdatum:", normal_style),
            Paragraph(info.delivery_date, normal_style)
        ])

    # Lieferschein
    if info.delivery_note:
        right_rows.append([
            Paragraph("Lieferschein:", normal_style),
            Paragraph(info.delivery_note, normal_style)
        ])

    # Leistungsempfänger NUR wenn erlaubt
    if not buyer.use_invoice_address_as_delivery and invoice.delivery and invoice.delivery.name:
        delivery_lines = [invoice.delivery.name]
        if invoice.delivery.street:
            delivery_lines.append(invoice.delivery.street)
        delivery_lines.append(f"{invoice.delivery.postcode} {invoice.delivery.city}")

        right_rows.append([
            Paragraph("<b>Leistungsempfänger:</b>", normal_style),
            Paragraph("<br/>".join(delivery_lines), normal_style)
        ])

    # ➜ IMMER eine rechte Tabelle erzeugen
    if right_rows:
        delivery_table = Table(
            right_rows,
            colWidths=detail_layout["delivery"]
        )
    else:
        delivery_table = Table(
            [["", ""]],
            colWidths=detail_layout["delivery"]
        )

    delivery_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (0,-1), 3*mm),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))

    # Beide Bereiche mit einem festen Zwischenraum kombinieren.
    combined_table = Table(
        [[invoice_table, "", delivery_table]],
        colWidths=[left_width, gutter_width, right_width],
        hAlign='LEFT'
    )

    combined_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))

    elements.append(combined_table)

    elements.append(Spacer(1, 5*mm))

    # ====================
    # Lieferhinweis VOR der Items-Tabelle
    # ====================
    if info.delivery_instruction:
        elements.append(Spacer(1, 3*mm))
        delivery_instr_para = Paragraph(f"<b>Lieferhinweis:</b> {info.delivery_instruction}", normal_style)
        elements.append(delivery_instr_para)
        elements.append(Spacer(1, 3*mm))

    # ====================
    # Positionstabellen mit DE-Format
    # ====================
    table_data = [["Pos", "Bezeichnung", "Menge", "Einheit", "Einzelpreis", "MwSt", "Netto gesamt"]]
    col_widths = [10*mm, 60*mm, 15*mm, 15*mm, 25*mm, 15*mm, doc.width-(10+60+15+15+25+15)*mm]
    row_index = 1
    table_style = TableStyle([
        ('FONTNAME', (0,0), (-1,-1), font_name),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (1,0), (1,-1), 'LEFT'),
        ('ALIGN', (2,0), (2,-1), 'CENTER'),
        ('ALIGN', (3,0), (3,-1), 'CENTER'),
        ('ALIGN', (4,0), (4,-1), 'RIGHT'),
        ('ALIGN', (5,0), (5,-1), 'CENTER'),
        ('ALIGN', (6,0), (6,-1), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), -0.75*mm),
        ('BOTTOMPADDING', (0,0), (-1,0), 2*mm),
        ('FONTNAME', (0,0), (-1,0), font_name + '-Bold')
    ])

    for item in items:
        menge = de_format(item.qty)
        einheit = unit_code_to_label(item.unit)
        einzelpreis = de_format(item.price)
        mwst = de_percent(item.vat)
        preis_netto = de_format(item.net)
        rabatt = de_format(item.discount)
        einzelpreis_ohne_rabatt = de_format(item.price_without_discount)

        table_data.append([item.pos, item.name, menge, einheit, einzelpreis, f"{mwst}%", preis_netto])
        table_style.add('NOSPLIT', (0, row_index), (-1, row_index))
        table_style.add('FONTNAME', (0, row_index), (-1, row_index), font_name + '-Bold')
        table_style.add('LINEABOVE', (0, row_index), (-1, row_index), 0.5, colors.grey)
        if row_index > 1:
            table_style.add('BOTTOMPADDING', (0, row_index-1), (-1, row_index-1), 2*mm)
        row_index += 1

        if item.description:
            table_data.append(["", item.description, "", "", "", "", ""])
            row_index += 1
        if rabatt and rabatt != "0,00":
            table_data.append(["", "Rabatt", "", "", f"-{rabatt}", "", ""])
            row_index += 1
            table_data.append(["", "Einzelpreis ohne Rabatt", "", "", f"{einzelpreis_ohne_rabatt}", "", ""])
            row_index += 1

    table = Table(table_data, colWidths=col_widths, repeatRows=1, splitByRow=True)
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 10*mm))

    # ====================
    # Summen
    # ====================
    mt = invoice.monetarytotal
    taxes = invoice.taxtotal
    currency = invoice.info.currency
    totals_data = []

    # Nettosumme
    totals_data.append([
        "Nettosumme:",
        f"{de_format(mt.line_extension_amount)} {currency}"
    ])

    # Steuerzeilen dynamisch
    for tax in sorted(taxes, key=lambda t: t.percent):
        totals_data.append([
            f"MwSt {de_percent(tax.percent)} %:",
            f"{de_format(tax.amount)} {currency}"
        ])

    # Gesamtbetrag
    totals_data.append([
        "Auszahlungsbetrag:" if is_self_billed else "Gesamtbetrag:",
        f"{de_format(mt.payable_amount)} {currency}"
    ])

    totals_table = Table(totals_data, colWidths=[40*mm, 35*mm], hAlign='RIGHT')
    last_row = len(totals_data) - 1

    totals_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,last_row-1), font_name),
        ('FONTSIZE', (0,0), (-1,last_row), 10),
        ('ALIGN', (0,0), (-1,last_row), 'RIGHT'),
        ('LINEABOVE', (0,last_row), (-1,last_row), 0.75, colors.black),
        ('FONTNAME', (0,last_row), (-1,last_row), font_name + '-Bold'),
        ('TOPPADDING', (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
    ]))
    elements.append(totals_table)

    # Zahlungshinweis
    if is_self_billed:
        payment_text = (
            f"Der Auszahlungsbetrag wird bis {info.payment_due_date} auf das Konto des Lieferanten überwiesen:<br/>"
            f"IBAN: {payment.iban}<br/>BIC: {payment.bic}<br/>Kontoinhaber: {payment.account_holder}"
        )
    else:
        payment_text = (
            f"Bitte überweisen Sie den Rechnungsbetrag bis {info.payment_due_date} auf folgendes Konto:<br/>"
            f"IBAN: {payment.iban}<br/>BIC: {payment.bic}<br/>Kontoinhaber: {payment.account_holder}"
        )
    payment_paragraph = Paragraph(payment_text, normal_style)
    elements.append(Spacer(1, 5*mm))
    elements.append(KeepTogether([payment_paragraph]))

    # PDF bauen
    doc.build(elements, canvasmaker=NumberedCanvas)
