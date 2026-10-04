# rechnungshelfer/gui/customer_load_dialog.py

import customtkinter as ctk
from tkinter import messagebox

from .components import button
from .styles import *


def truncate(text, max_len=45):
    text = str(text or "")
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


class CustomerLoadDialog:
    def __init__(self, parent, controller, on_customer_selected):
        self.parent = parent
        self.controller = controller
        self.on_customer_selected = on_customer_selected

        self.window = None
        self.search_entry = None
        self.list_frame = None

        self.rows = []
        self.selected_customer_number = None
        self.selected_customer = None
        self.selected_row = None
        self._render_job = None

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Kundenliste")
        self.window.geometry("900x600")
        self.window.grab_set()

        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(2, weight=1)

        title = ctk.CTkLabel(
            self.window,
            text="Kundenliste",
            font=FONT_SECTION,
            text_color=TEXT,
        )
        title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

        self.search_entry = ctk.CTkEntry(
            self.window,
            placeholder_text="Suche nach Kundennummer, Name, Ort oder E-Mail...",
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
            ("Kundennummer", 150, "w"),
            ("Name", 280, "w"),
            ("Ort", 180, "w"),
            ("E-Mail", 230, "w"),
            ("Leitweg-ID", 160, "w"),
        ]

    def _render_footer(self):
        footer = ctk.CTkFrame(self.window, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="e", padx=18, pady=(0, 18))

        button(footer, "Kunde übernehmen", self.load_selected).grid(
            row=0,
            column=0,
            padx=(0, 10),
        )

        button(footer, "Löschen", self.delete_selected).grid(
            row=0,
            column=1,
            padx=(0, 10),
        )

        button(footer, "Abbrechen", self.close).grid(
            row=0,
            column=2,
        )

    def render_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        self._render_header()

        self.rows = []
        self.selected_customer_number = None
        self.selected_customer = None
        self.selected_row = None

        query = (self.search_entry.get() if self.search_entry else "").lower().strip()
        customers = self.controller.list_customers()

        filtered = []
        for customer in customers:
            text = " ".join([
                str(getattr(customer, "customer_number", "")),
                str(getattr(customer, "name", "")),
                str(getattr(customer, "city", "")),
                str(getattr(customer, "email", "")),
                str(getattr(customer, "leitweg_id", "")),
            ]).lower()

            if query in text:
                filtered.append(customer)

        if not filtered:
            ctk.CTkLabel(
                self.list_frame,
                text="Keine Kunden gefunden.",
                font=FONT_NORMAL,
                text_color=TEXT_MUTED,
            ).grid(row=1, column=0, columnspan=5, sticky="w", padx=10, pady=12)
            return

        for row_index, customer in enumerate(filtered, start=1):
            self._render_row(row_index, customer)

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

    def _render_row(self, row_index, customer):
        customer_number = getattr(customer, "customer_number", "")
        name = getattr(customer, "name", "")
        street = getattr(customer, "street", "")
        postcode = getattr(customer, "postcode", "")
        city = getattr(customer, "city", "")
        email = getattr(customer, "email", "")
        leitweg_id = getattr(customer, "leitweg_id", "")
        contact_name = getattr(customer, "contact_name", "")

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

        title = f"{customer_number or '-'} | {name}"
        subtitle = f"{street}, {postcode} {city}"
        details = f"E-Mail: {email or '-'}    Leitweg-ID: {leitweg_id or '-'}"

        if contact_name:
            details += f"    Ansprechpartner: {contact_name}"

        labels = []

        for i, (text, font, color) in enumerate([
            (title, FONT_NORMAL, TEXT),
            (subtitle, FONT_SMALL, TEXT),
            (details, FONT_SMALL, TEXT_MUTED),
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

            label.bind("<Button-1>", lambda e, c=customer, rf=row_frame: self.select_row(c, rf))
            label.bind("<Double-Button-1>", lambda e, c=customer: self.load_customer(c))
            label.bind("<Enter>", lambda e, rf=row_frame: self._hover_row(rf, True))
            label.bind("<Leave>", lambda e, rf=row_frame: self._hover_row(rf, False))

        row_frame.bind("<Button-1>", lambda e, c=customer, rf=row_frame: self.select_row(c, rf))
        row_frame.bind("<Double-Button-1>", lambda e, c=customer: self.load_customer(c))
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

    def select_row(self, customer, row_frame):
        if self.selected_row and self.selected_row.winfo_exists():
            self.selected_row.configure(
                fg_color=self.selected_row._base_color,
                border_color=BORDER,
            )

        self.selected_customer = customer
        self.selected_customer_number = getattr(customer, "customer_number", "")
        self.selected_row = row_frame

        row_frame.configure(
            fg_color="#dbeafe",
            border_color=PRIMARY,
        )

    def load_selected(self):
        if not self.selected_customer:
            messagebox.showwarning("Auswahl fehlt", "Bitte wähle einen Kunden aus.")
            return

        self.load_customer(self.selected_customer)

    def load_customer(self, customer):
        self.on_customer_selected(customer)
        self.close()

    def delete_selected(self):
        if not self.selected_customer_number:
            messagebox.showwarning("Auswahl fehlt", "Bitte wähle einen Kunden aus.")
            return

        ok = messagebox.askyesno(
            "Kunde löschen",
            f"Kunde {self.selected_customer_number} wirklich löschen?",
        )

        if not ok:
            return

        try:
            self.controller.delete_customer(self.selected_customer_number)
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
