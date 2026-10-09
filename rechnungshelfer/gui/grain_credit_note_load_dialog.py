"""Auswahl gespeicherter strukturierter Getreidegutschriften."""

import sqlite3

import customtkinter as ctk
from tkinter import messagebox

from rechnungshelfer.services.format_service import format_de

from .components import button
from .styles import BORDER, FONT_NORMAL, FONT_SECTION, FONT_SMALL, TEXT, TEXT_MUTED


class GrainCreditNoteLoadDialog:
    def __init__(self, parent, controller, on_loaded):
        self.parent = parent
        self.controller = controller
        self.on_loaded = on_loaded
        self.window = None
        self.search_entry = None
        self.list_frame = None
        self.selected_number = None
        self.selected_row = None

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Getreidegutschrift öffnen")
        self.window.geometry("820x560")
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.window,
            text="Gespeicherte Getreidegutschrift öffnen",
            font=FONT_SECTION,
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))
        self.search_entry = ctk.CTkEntry(
            self.window,
            placeholder_text="Suche nach Nummer oder Lieferant ...",
            height=34,
            font=FONT_NORMAL,
        )
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.search_entry.bind("<KeyRelease>", lambda _event: self.render_list())

        self.list_frame = ctk.CTkScrollableFrame(
            self.window,
            fg_color="#f8fafc",
            corner_radius=10,
        )
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 14))
        self.list_frame.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self.window, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="e", padx=18, pady=(0, 18))
        button(footer, "Öffnen", self.load_selected, primary=True).pack(
            side="left", padx=(0, 8)
        )
        button(footer, "Abbrechen", self.close).pack(side="left")
        self.render_list()

    def render_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.selected_number = None
        self.selected_row = None
        query = self.search_entry.get().strip().casefold()
        summaries = self.controller.list_grain_credit_note_summaries()
        filtered = [
            item
            for item in summaries
            if query
            in (
                f"{item['credit_note_number']} {item['supplier_number']} "
                f"{item['supplier_name']}"
            ).casefold()
        ]
        if not filtered:
            ctk.CTkLabel(
                self.list_frame,
                text="Keine gespeicherten Getreidegutschriften gefunden.",
                font=FONT_NORMAL,
                text_color=TEXT_MUTED,
            ).grid(row=0, column=0, sticky="w", padx=12, pady=12)
            return
        for index, item in enumerate(filtered):
            self._render_row(index, item)

    def _render_row(self, index, item):
        number = item["credit_note_number"]
        row = ctk.CTkFrame(
            self.list_frame,
            fg_color="#ffffff" if index % 2 == 0 else "#f8fafc",
            border_width=1,
            border_color=BORDER,
            corner_radius=8,
        )
        row.grid(row=index, column=0, sticky="ew", padx=6, pady=4)
        row.grid_columnconfigure(0, weight=1)
        try:
            amount = f"{format_de(item['credit_amount'])} EUR"
        except Exception:
            amount = str(item["credit_amount"])
        texts = (
            (f"Getreidegutschrift {number}", FONT_NORMAL, TEXT),
            (
                f"Lieferant {item['supplier_number'] or '-'} · "
                f"{item['supplier_name'] or '-'}",
                FONT_SMALL,
                TEXT_MUTED,
            ),
            (f"Datum: {item['credit_note_date']} · Betrag: {amount}", FONT_SMALL, TEXT),
        )
        for line, (text, font, color) in enumerate(texts):
            label = ctk.CTkLabel(
                row,
                text=text,
                font=font,
                text_color=color,
                anchor="w",
            )
            label.grid(row=line, column=0, sticky="ew", padx=12, pady=2)
            label.bind("<Button-1>", lambda _e, n=number, r=row: self.select(n, r))
            label.bind("<Double-Button-1>", lambda _e, n=number: self.load(n))
        row.bind("<Button-1>", lambda _e, n=number, r=row: self.select(n, r))

    def select(self, number, row):
        if self.selected_row is not None and self.selected_row.winfo_exists():
            self.selected_row.configure(border_color=BORDER)
        self.selected_number = number
        self.selected_row = row
        row.configure(border_color="#2563eb")

    def load_selected(self):
        if not self.selected_number:
            messagebox.showwarning(
                "Auswahl fehlt",
                "Bitte wähle eine Getreidegutschrift aus.",
                parent=self.window,
            )
            return False
        return self.load(self.selected_number)

    def load(self, number):
        try:
            note = self.controller.load_grain_credit_note(number)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror("Getreidegutschrift öffnen", str(exc), parent=self.window)
            return False
        self.on_loaded(note)
        self.close()
        return True

    def close(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None


__all__ = ["GrainCreditNoteLoadDialog"]
