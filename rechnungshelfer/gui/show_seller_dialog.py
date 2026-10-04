# rechnungshelfer/gui/show_seller_dialog.py

from copy import deepcopy
from tkinter import messagebox

import customtkinter as ctk

from .components import button, clear_frame
from .party_card import PartyCard
from .styles import APP_BG


class SellerDialog:
    def __init__(self, parent, controller, invoice, on_saved=None):
        self.parent = parent
        self.controller = controller
        self.invoice = invoice
        self.on_saved = on_saved

        self.window = None
        self.container = None
        self.content = None
        self.button_bar = None

        self.field_entries = {}

        self.seller = deepcopy(invoice.seller)
        self.payment = deepcopy(invoice.payment)

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Verkäufer / Zahlung")
        self.window.geometry("980x560")
        self.window.minsize(900, 520)
        self.window.grab_set()

        self.window.configure(fg_color=APP_BG)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(0, weight=1)

        self.container = ctk.CTkFrame(
            self.window,
            fg_color=APP_BG,
            corner_radius=0,
        )
        self.container.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=26,
            pady=24,
        )

        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_rowconfigure(1, weight=0)

        self.content = ctk.CTkFrame(
            self.container,
            fg_color="transparent",
            corner_radius=0,
        )
        self.content.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        self.content.grid_columnconfigure(0, weight=1, uniform="seller_dialog_cards")
        self.content.grid_columnconfigure(1, weight=1, uniform="seller_dialog_cards")
        self.content.grid_rowconfigure(0, weight=0)

        self.button_bar = ctk.CTkFrame(
            self.container,
            fg_color="transparent",
            corner_radius=0,
        )
        self.button_bar.grid(
            row=1,
            column=0,
            sticky="e",
            pady=(22, 0),
        )

        self._render_content()

    def _render_content(self):
        clear_frame(self.content)
        clear_frame(self.button_bar)
        self.field_entries.clear()

        seller_card = PartyCard(
            self.content,
            "Verkäufer",
            self.seller,
            field_entries=self.field_entries,
            exclude_fields=["country", "supplier_number"],
        ).render()
        seller_card.grid(
            row=0,
            column=0,
            sticky="new",
            padx=(0, 12),
        )

        payment_card = PartyCard(
            self.content,
            "Bankdaten / Zahlungshinweise",
            self.payment,
            field_entries=self.field_entries,
            exclude_fields=self._exclude_payment_fields(),
        ).render()
        payment_card.grid(
            row=0,
            column=1,
            sticky="new",
            padx=(12, 0),
        )

        button(
            self.button_bar,
            "Stammdaten laden",
            self.reset_to_defaults,
        ).grid(row=0, column=0, padx=(0, 10))

        button(
            self.button_bar,
            "Als Stammdaten speichern",
            self.save,
        ).grid(row=0, column=2, padx=(0, 10))

        button(
            self.button_bar,
            "Schließen",
            self.close,
        ).grid(row=0, column=3)

    def _exclude_payment_fields(self):
        keywords = [
            "zahlungsbedingungen",
            "zahlungsbedingung",
            "zahlungsart",
            "zahlungsweise",
            "zahlungsmethode",
            "payment terms",
            "payment method",
        ]

        fields = []

        for field in self.payment.__dict__.keys():
            if field.startswith("_"):
                continue

            label = (
                self.payment.get_label(field)
                if hasattr(self.payment, "get_label")
                else field
            )

            text = f"{field} {label}".lower()

            if any(keyword in text for keyword in keywords):
                fields.append(field)

        return fields

    def take_from_current_invoice(self):
        self.seller = deepcopy(self.invoice.seller)
        self.payment = deepcopy(self.invoice.payment)
        self._render_content()

    def reset_to_defaults(self):
        self.controller.load_master_data(self.seller, self.payment)
        self._render_content()

    def save(self):
        try:
            self.controller.save_master_data(self.seller, self.payment)

            messagebox.showinfo(
                "Gespeichert",
                "Aktueller Verkäufer und Zahlungsdaten wurden als Stammdaten gespeichert.",
            )

            if self.on_saved:
                self.on_saved()

            self.close()

        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def close(self):
        if self.window:
            self.window.destroy()
            self.window = None
