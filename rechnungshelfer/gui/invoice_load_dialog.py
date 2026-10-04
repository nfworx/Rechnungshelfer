# rechnungshelfer/gui/invoice_load_dialog.py

import customtkinter as ctk
from tkinter import messagebox

from .components import button
from .styles import *
from rechnungshelfer.services.format_service import format_de, parse_de

def truncate(text, max_len=45):
    text = str(text or "")
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


class InvoiceLoadDialog:
    def __init__(self, parent, controller, on_invoice_loaded):
        self.parent = parent
        self.controller = controller
        self.on_invoice_loaded = on_invoice_loaded

        self.window = None
        self.search_entry = None
        self.list_frame = None

        self.rows = []
        self.selected_invoice_number = None
        self.selected_row = None
        self._render_job = None

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Beleg laden")
        self.window.geometry("900x600")
        self.window.grab_set()

        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(2, weight=1)

        title = ctk.CTkLabel(
            self.window,
            text="Beleg laden",
            font=FONT_SECTION,
            text_color=TEXT,
        )
        title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

        self.search_entry = ctk.CTkEntry(
            self.window,
            placeholder_text="Suche nach Belegnummer, Belegtyp oder Beteiligtem...",
            height=34,
            font=FONT_NORMAL,
            corner_radius=8,
            border_width=1,
        )
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.search_entry.bind("<KeyRelease>", self._schedule_render)

        self.list_frame = ctk.CTkScrollableFrame(
            self.window,
            fg_color="#f8fafc",
            corner_radius=10,
        )
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 14))
        self.list_frame.grid_columnconfigure(0, weight=1)

        self._render_footer()
        self.render_list()

    def _schedule_render(self, event=None):
        if self._render_job is not None:
            self.window.after_cancel(self._render_job)
        self._render_job = self.window.after(150, self._render_scheduled)

    def _render_scheduled(self):
        self._render_job = None
        self.render_list()

    def _columns(self):
        return [
            ("Belegnummer", 170, "w"),
            ("Kunde", 330, "w"),
            ("Datum", 130, "center"),
            ("Betrag", 120, "e"),
        ]

    def _render_footer(self):
        footer = ctk.CTkFrame(self.window, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="e", padx=18, pady=(0, 18))

        button(footer, "Beleg laden", self.load_selected).grid(
            row=0,
            column=0,
            padx=(0, 10),
        )

        button(footer, "Als neuen Beleg kopieren", self.copy_selected).grid(
            row=0,
            column=1,
            padx=(0, 10),
        )

        button(footer, "Löschen", self.delete_selected).grid(
            row=0,
            column=2,
            padx=(0, 10),
        )

        button(footer, "Abbrechen", self.close).grid(
            row=0,
            column=3,
        )

    def render_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        self._render_header()

        self.rows = []
        self.selected_invoice_number = None
        self.selected_row = None

        query = (self.search_entry.get() if self.search_entry else "").lower().strip()
        summaries = self.controller.list_invoice_summaries()

        filtered = []
        for item in summaries:
            text = (
                f"{item.get('invoice_number', '')} "
                f"{item.get('counterparty_name', '')} "
                f"{item.get('document_type', '')}"
            ).lower()
            if query in text:
                filtered.append(item)

        if not filtered:
            ctk.CTkLabel(
                self.list_frame,
                text="Keine Rechnungen gefunden.",
                font=FONT_NORMAL,
                text_color=TEXT_MUTED,
            ).grid(row=1, column=0, columnspan=4, sticky="w", padx=10, pady=12)
            return

        for row_index, item in enumerate(filtered, start=1):
            self._render_row(row_index, item)

    def _render_header(self):
        header_frame = ctk.CTkFrame(
            self.list_frame,
            fg_color="#eef2f7",
            corner_radius=8,
        )
        header_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))

        for col, (title, width, anchor) in enumerate(self._columns()):
            ctk.CTkLabel(
                header_frame,
                text=title,
                width=width,
                font=("Segoe UI", 11, "bold"),
                text_color=TEXT,
                anchor=anchor,
            ).grid(row=0, column=col, sticky="ew", padx=10, pady=8)

    def _render_row(self, row_index, item):
        invoice_number = item.get("invoice_number", "")
        buyer_name = item.get("counterparty_name", item.get("buyer_name", ""))
        is_self_billed = item.get("document_type") == "self_billed_invoice"
        customer_number = item.get("customer_number", "")
        supplier_number = item.get("supplier_number", "")
        invoice_date = item.get("invoice_date", "")
        payable_amount = item.get("payable_amount", "")

        try:
            payable_amount = f"{format_de(payable_amount)} €"
        except Exception:
            payable_amount = str(payable_amount)

        bg_color = "#ffffff" if row_index % 2 == 0 else "#f8fafc"

        row_frame = ctk.CTkFrame(
            self.list_frame,
            fg_color=bg_color,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        row_frame.grid(row=row_index, column=0, sticky="ew", padx=(16, 16), pady=5)
        row_frame.configure(width=820)
        row_frame.grid_columnconfigure(0, weight=1)

        document_name = "Gutschrift" if is_self_billed else "Rechnung"
        title = f"{document_name} {invoice_number} | {buyer_name}"
        number_label = "Lieferantennummer" if is_self_billed else "Kundennummer"
        party_number = supplier_number if is_self_billed else customer_number
        subtitle = f"{number_label}: {party_number or '-'}    Datum: {invoice_date or '-'}"
        details = f"Betrag: {payable_amount}"

        labels = []

        for i, (text, font, color) in enumerate([
            (title, FONT_NORMAL, TEXT),
            (subtitle, FONT_SMALL, TEXT_MUTED),
            (details, FONT_SMALL, TEXT),
        ]):
            label = ctk.CTkLabel(
                row_frame,
                text=text,
                font=font,
                text_color=color,
                anchor="w",
                justify="left",
            )
            label.grid(row=i, column=0, sticky="ew", padx=14, pady=(8 if i == 0 else 1, 8 if i == 2 else 1))
            labels.append(label)

            label.bind("<Button-1>", lambda e, num=invoice_number, rf=row_frame: self.select_row(num, rf))
            label.bind("<Double-Button-1>", lambda e, num=invoice_number: self.load_invoice(num))
            label.bind("<Enter>", lambda e, rf=row_frame: self._hover_row(rf, True))
            label.bind("<Leave>", lambda e, rf=row_frame: self._hover_row(rf, False))

        row_frame.bind("<Button-1>", lambda e, num=invoice_number, rf=row_frame: self.select_row(num, rf))
        row_frame.bind("<Double-Button-1>", lambda e, num=invoice_number: self.load_invoice(num))
        row_frame.bind("<Enter>", lambda e, rf=row_frame: self._hover_row(rf, True))
        row_frame.bind("<Leave>", lambda e, rf=row_frame: self._hover_row(rf, False))

        row_frame._labels = labels
        row_frame._base_color = bg_color

        self.rows.append(row_frame)

    def _hover_row(self, row_frame, enter):
        if row_frame == self.selected_row:
            return

        if enter:
            row_frame.configure(fg_color="#e2e8f0")
        else:
            row_frame.configure(fg_color=row_frame._base_color)

    def select_row(self, invoice_number, row_frame):
        if self.selected_row and self.selected_row.winfo_exists():
            self.selected_row.configure(
                fg_color=self.selected_row._base_color,
                border_color=BORDER,
            )

        self.selected_invoice_number = invoice_number
        self.selected_row = row_frame

        row_frame.configure(
            fg_color="#dbeafe",
            border_color=PRIMARY,
        )

    def load_selected(self):
        if not self.selected_invoice_number:
            messagebox.showwarning("Auswahl fehlt", "Bitte wähle eine Rechnung aus.")
            return

        self.load_invoice(self.selected_invoice_number)

    def load_invoice(self, invoice_number):
        try:
            invoice = self.controller.load_invoice(invoice_number)
            self.on_invoice_loaded(invoice)
            self.close()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def copy_selected(self):
        if not self.selected_invoice_number:
            messagebox.showwarning("Auswahl fehlt", "Bitte wähle einen Beleg aus.")
            return
        try:
            invoice = self.controller.load_invoice(self.selected_invoice_number)
            self.on_invoice_loaded(self.controller.copy_invoice(invoice))
            self.close()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def delete_selected(self):
        if not self.selected_invoice_number:
            messagebox.showwarning("Auswahl fehlt", "Bitte wähle eine Rechnung aus.")
            return

        ok = messagebox.askyesno(
            "Beleg löschen",
            f"Beleg {self.selected_invoice_number} wirklich löschen?",
        )

        if not ok:
            return

        try:
            self.controller.delete_invoice(self.selected_invoice_number)
            self.render_list()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def close(self):
        if self._render_job is not None and self.window:
            self.window.after_cancel(self._render_job)
            self._render_job = None
        if self.window:
            self.window.destroy()
            self.window = None
