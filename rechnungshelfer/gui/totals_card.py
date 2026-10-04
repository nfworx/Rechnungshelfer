# rechnungshelfer/gui/totals_card.py

import customtkinter as ctk

from .styles import *
from .components import HoverTooltip, card, button, set_button_enabled
from rechnungshelfer.services.format_service import format_de, parse_de


class TotalsCard:
    def __init__(
        self,
        parent,
        invoice,
        on_pdf,
        on_xml,
        can_export_pdf=None,
        can_export_xml=None,
        pdf_export_hint=None,
        xml_export_hint=None,
    ):
        self.parent = parent
        self.invoice = invoice
        self.on_pdf = on_pdf
        self.on_xml = on_xml
        self.can_export_pdf = can_export_pdf
        self.can_export_xml = can_export_xml
        self.pdf_export_hint = pdf_export_hint
        self.xml_export_hint = xml_export_hint
        self.frame = None
        self.rows = {}
        self.pdf_button = None
        self.xml_button = None

    def render(self):
        self.rows.clear()

        self.frame = card(self.parent, "Summen")
        self.frame.pack(fill="both", expand=True)

        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_columnconfigure(1, weight=0)

        rows = [
            ("line_extension_amount", "Nettosumme"),
            ("tax_19", "MwSt 19%"),
            ("tax_7", "MwSt 7%"),
            ("tax_7_8", "MwSt 7,8 %"),
            ("payable_amount", "Auszahlungsbetrag" if self.invoice.is_self_billed else "Gesamtbetrag"),
        ]

        for row, (key, label) in enumerate(rows, start=1):
            is_total = key == "payable_amount"
            font = FONT_SECTION if is_total else FONT_SMALL

            ctk.CTkLabel(
                self.frame,
                text=label,
                font=font,
                text_color=TEXT,
                anchor="w",
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=14,
                pady=(3 if not is_total else 10, 3),
            )

            value_label = ctk.CTkLabel(
                self.frame,
                text="0,00 EUR",
                font=font,
                text_color=TEXT,
                anchor="e",
            )
            value_label.grid(
                row=row,
                column=1,
                sticky="e",
                padx=14,
                pady=(3 if not is_total else 10, 3),
            )

            self.rows[key] = value_label

        self.pdf_button = button(self.frame, "PDF erstellen", self.on_pdf)
        self.pdf_button.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(12, 8),
        )

        self.xml_button = button(self.frame, "XML erstellen", self.on_xml)
        self.xml_button.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(0, 14),
        )

        HoverTooltip(
            self.pdf_button,
            self.pdf_export_hint or (lambda: ""),
        )
        HoverTooltip(
            self.xml_button,
            self.xml_export_hint or (lambda: ""),
        )

        self.refresh()

        return self.frame

    def refresh(self, recalculate=True):
        if not self.rows:
            return

        if recalculate:
            try:
                self.invoice.calculate(force=True)
            except (ValueError, ArithmeticError):
                return

        mt = self.invoice.monetarytotal
        taxes = getattr(self.invoice, "taxtotal", [])
        currency = getattr(self.invoice.info, "currency", "EUR")

        self.rows["line_extension_amount"].configure(
            text=f"{format_de(mt.line_extension_amount)} {currency}"
        )

        tax_map = {float(tax.percent): tax.amount for tax in taxes}

        self.rows["tax_19"].configure(
            text=f"{format_de(tax_map.get(19.0, 0))} {currency}"
        )

        self.rows["tax_7"].configure(
            text=f"{format_de(tax_map.get(7.0, 0))} {currency}"
        )

        self.rows["tax_7_8"].configure(
            text=f"{format_de(tax_map.get(7.8, 0))} {currency}"
        )

        self.rows["payable_amount"].configure(
            text=f"{format_de(mt.payable_amount)} {currency}"
        )

        self.refresh_export_buttons()

    def refresh_export_buttons(self):
        if not self.pdf_button or not self.xml_button:
            return

        pdf_enabled = bool(self.can_export_pdf()) if self.can_export_pdf else True
        xml_enabled = bool(self.can_export_xml()) if self.can_export_xml else True

        set_button_enabled(self.pdf_button, pdf_enabled)
        set_button_enabled(self.xml_button, xml_enabled)
