# rechnungshelfer/gui/totals_card.py

import customtkinter as ctk
from decimal import Decimal

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
        on_save,
        can_export_pdf=None,
        can_export_xml=None,
        pdf_export_hint=None,
        xml_export_hint=None,
    ):
        self.parent = parent
        self.invoice = invoice
        self.on_pdf = on_pdf
        self.on_xml = on_xml
        self.on_save = on_save
        self.can_export_pdf = can_export_pdf
        self.can_export_xml = can_export_xml
        self.pdf_export_hint = pdf_export_hint
        self.xml_export_hint = xml_export_hint
        self.frame = None
        self.rows = {}
        self.row_widgets = {}
        self.pdf_button = None
        self.xml_button = None
        self.save_button = None

    def render(self):
        self.rows.clear()
        self.row_widgets.clear()

        self.frame = card(self.parent, "Summen")
        self.frame.pack(fill="both", expand=True)

        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_columnconfigure(1, weight=0)

        rows = [
            ("line_extension_amount", "Nettosumme"),
            ("tax_0", "Umsatzsteuer 0 %"),
            ("tax_7", "Umsatzsteuer 7 %"),
            ("tax_7_8", "Umsatzsteuer 7,8 %"),
            ("tax_19", "Umsatzsteuer 19 %"),
            ("payable_amount", "Auszahlungsbetrag" if self.invoice.is_self_billed else "Gesamtbetrag"),
        ]

        for row, (key, label) in enumerate(rows, start=1):
            is_total = key == "payable_amount"
            font = FONT_SECTION if is_total else FONT_SMALL

            label_widget = ctk.CTkLabel(
                self.frame,
                text=label,
                font=font,
                text_color=TEXT,
                anchor="w",
            )
            label_widget.grid(
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
            self.row_widgets[key] = (label_widget, value_label)

        self.pdf_button = button(self.frame, "PDF erstellen", self.on_pdf)
        self.pdf_button.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(12, 8),
        )

        self.xml_button = button(self.frame, "XML erstellen", self.on_xml)
        self.xml_button.grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(0, 8),
        )

        self.save_button = button(
            self.frame,
            "Speichern",
            self.on_save,
            primary=True,
        )
        self.save_button.grid(
            row=9,
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

        tax_rows = {
            Decimal("0"): "tax_0",
            Decimal("7"): "tax_7",
            Decimal("7.8"): "tax_7_8",
            Decimal("19"): "tax_19",
        }
        tax_map = {Decimal(str(tax.percent)): tax.amount for tax in taxes}
        for percent, key in tax_rows.items():
            label_widget, value_widget = self.row_widgets[key]
            if percent in tax_map:
                label_widget.grid()
                value_widget.grid()
                value_widget.configure(
                    text=f"{format_de(tax_map[percent])} {currency}"
                )
            else:
                label_widget.grid_remove()
                value_widget.grid_remove()

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
