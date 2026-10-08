import customtkinter as ctk
from tkinter import messagebox

from .components import button
from .styles import (
    APP_BG,
    BORDER,
    FONT_NORMAL,
    FONT_SECTION,
    FONT_SMALL,
    PRIMARY,
    TEXT,
    TEXT_MUTED,
)


class SupplierLoadDialog:
    def __init__(
        self,
        parent,
        controller,
        on_supplier_selected,
        on_create_supplier=None,
    ):
        self.parent = parent
        self.controller = controller
        self.on_supplier_selected = on_supplier_selected
        self.on_create_supplier = on_create_supplier
        self.window = None
        self.search_entry = None
        self.list_frame = None
        self.selected = None
        self.selected_row = None
        self._render_job = None

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Lieferant auswählen")
        self.window.geometry("900x600")
        self.window.grab_set()
        self.window.configure(fg_color=APP_BG)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.window,
            text="Lieferantenliste",
            font=FONT_SECTION,
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

        self.search_entry = ctk.CTkEntry(
            self.window,
            placeholder_text=(
                "Suche nach GeschÃ¤ftspartnernummer, Name, Ort oder Steuernummer..."
            ),
            height=34,
        )
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.search_entry.bind("<KeyRelease>", self._schedule_render)

        self.list_frame = ctk.CTkScrollableFrame(self.window, fg_color="#f8fafc")
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 14))
        self.list_frame.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self.window, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="e", padx=18, pady=(0, 18))
        column = 0
        if self.on_create_supplier:
            button(footer, "Neuer Lieferant", self.create_supplier).grid(
                row=0,
                column=column,
                padx=(0, 10),
            )
            column += 1
        button(footer, "Lieferant übernehmen", self.load_selected).grid(
            row=0,
            column=column,
            padx=(0, 10),
        )
        button(footer, "Löschen", self.delete_selected).grid(
            row=0,
            column=column + 1,
            padx=(0, 10),
        )
        button(footer, "Abbrechen", self.close).grid(
            row=0,
            column=column + 2,
        )
        self.render_list()

    def _schedule_render(self, event=None):
        if self._render_job is not None:
            self.window.after_cancel(self._render_job)
        self._render_job = self.window.after(150, self._render_scheduled)

    def _render_scheduled(self):
        self._render_job = None
        self.render_list()

    def render_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.selected = None
        self.selected_row = None
        query = (self.search_entry.get() if self.search_entry else "").lower().strip()
        suppliers = []
        for seller, payment in self.controller.list_suppliers():
            searchable = " ".join(
                [seller.supplier_number, seller.name, seller.city, seller.tax_number, seller.vat]
            ).lower()
            if query in searchable:
                suppliers.append((seller, payment))

        if not suppliers:
            ctk.CTkLabel(
                self.list_frame,
                text="Keine Lieferanten gespeichert.",
                font=FONT_NORMAL,
                text_color=TEXT_MUTED,
            ).grid(row=0, column=0, sticky="w", padx=14, pady=14)
            return

        for index, supplier in enumerate(suppliers):
            self._render_row(index, supplier)

    def _render_row(self, index, supplier):
        seller, payment = supplier
        frame = ctk.CTkFrame(
            self.list_frame,
            fg_color="#ffffff" if index % 2 == 0 else "#f8fafc",
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        frame.grid(row=index, column=0, sticky="ew", padx=10, pady=5)
        frame.grid_columnconfigure(0, weight=1)
        texts = [
            f"{seller.supplier_number or '-'} | {seller.name}",
            f"{seller.street}, {seller.postcode} {seller.city}",
            f"Steuernummer: {seller.tax_number or '-'}    "
            f"USt-ID: {seller.vat or '-'}    "
            f"IBAN: {payment.iban or '-'}",
        ]
        for row, text in enumerate(texts):
            label = ctk.CTkLabel(
                frame,
                text=text,
                font=FONT_NORMAL if row == 0 else FONT_SMALL,
                text_color=TEXT if row < 2 else TEXT_MUTED,
                anchor="w",
            )
            label.grid(row=row, column=0, sticky="ew", padx=14, pady=3)
            label.bind(
                "<Button-1>",
                lambda event, value=supplier, widget=frame: self.select(
                    value,
                    widget,
                ),
            )
            label.bind("<Double-Button-1>", lambda event, value=supplier: self.load(value))
        frame.bind(
            "<Button-1>",
            lambda event, value=supplier, widget=frame: self.select(value, widget),
        )

    def select(self, supplier, row):
        if self.selected_row and self.selected_row.winfo_exists():
            self.selected_row.configure(border_color=BORDER)
        self.selected = supplier
        self.selected_row = row
        row.configure(border_color=PRIMARY)

    def load_selected(self):
        if not self.selected:
            messagebox.showwarning("Auswahl fehlt", "Bitte wähle einen Lieferanten aus.")
            return
        self.load(self.selected)

    def load(self, supplier):
        self.on_supplier_selected(*supplier)
        self.close()

    def create_supplier(self):
        callback = self.on_create_supplier
        self.close()
        if callback:
            callback()

    def delete_selected(self):
        if not self.selected:
            messagebox.showwarning("Auswahl fehlt", "Bitte wähle einen Lieferanten aus.")
            return
        seller, _ = self.selected
        if messagebox.askyesno("Lieferant löschen", f"{seller.name} wirklich löschen?"):
            self.controller.delete_supplier(seller.supplier_number)
            self.render_list()

    def close(self):
        if self._render_job is not None and self.window:
            self.window.after_cancel(self._render_job)
            self._render_job = None
        if self.window:
            self.window.destroy()
            self.window = None
