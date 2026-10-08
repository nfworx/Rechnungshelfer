"""Dialog zum expliziten Anlegen eines Lieferantenstammsatzes."""

from copy import deepcopy
from tkinter import messagebox

import customtkinter as ctk

from rechnungshelfer.domain.models import DocumentType

from .components import button
from .party_card import PartyCard
from .styles import APP_BG


class SupplierEditDialog:
    def __init__(self, parent, controller, on_saved):
        self.parent = parent
        self.controller = controller
        self.on_saved = on_saved
        draft = controller.create_empty_invoice(DocumentType.SELF_BILLED_INVOICE)
        self.seller = deepcopy(draft.seller)
        self.payment = deepcopy(draft.payment)
        self.window = None
        self.field_entries = {}

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Neuen Lieferanten anlegen")
        self.window.geometry("1050x720")
        self.window.minsize(900, 600)
        self.window.grab_set()
        self.window.configure(fg_color=APP_BG)
        self.window.grid_columnconfigure((0, 1), weight=1)
        self.window.grid_rowconfigure(0, weight=1)

        seller_card = PartyCard(
            self.window,
            "Lieferant",
            self.seller,
            field_entries=self.field_entries,
            exclude_fields=["buyer_reference"],
        ).render()
        seller_card.grid(row=0, column=0, sticky="nsew", padx=(18, 8), pady=18)

        payment_card = PartyCard(
            self.window,
            "Bankdaten / Auszahlung",
            self.payment,
            field_entries=self.field_entries,
        ).render()
        payment_card.grid(row=0, column=1, sticky="nsew", padx=(8, 18), pady=18)

        actions = ctk.CTkFrame(self.window, fg_color="transparent")
        actions.grid(row=1, column=0, columnspan=2, sticky="e", padx=18, pady=(0, 18))
        button(actions, "Speichern und übernehmen", self.save, primary=True).pack(
            side="left",
            padx=(0, 8),
        )
        button(actions, "Abbrechen", self.close).pack(side="left")

    def save(self):
        try:
            self.controller.save_supplier(self.seller, self.payment)
        except Exception as exc:
            messagebox.showerror("Lieferant", str(exc), parent=self.window)
            return
        self.on_saved(deepcopy(self.seller), deepcopy(self.payment))
        self.close()

    def close(self):
        if self.window:
            self.window.destroy()
            self.window = None
