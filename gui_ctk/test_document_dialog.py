import customtkinter as ctk

from gui_ctk.components import button
from gui_ctk.styles import FONT_NORMAL, FONT_SECTION, TEXT, TEXT_MUTED
from services.sample_document_service import (
    create_sample_invoice,
    create_sample_self_billed_invoice,
)


class TestDocumentDialog:
    """Laedt Beispieldaten ins Formular, ohne die Datenbank zu veraendern."""

    def __init__(self, parent, on_document_selected):
        self.parent = parent
        self.on_document_selected = on_document_selected
        self.window = None

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Testbeleg laden")
        self.window.geometry("540x250")
        self.window.resizable(False, False)
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            self.window,
            text="Testbeleg laden",
            font=FONT_SECTION,
            text_color=TEXT,
        ).grid(row=0, column=0, columnspan=2, pady=(24, 10))

        ctk.CTkLabel(
            self.window,
            text=(
                "Der gewählte Beleg wird vollständig ins Formular geladen.\n"
                "Die Datenbank wird erst über ‚Beleg speichern‘ geändert."
            ),
            font=FONT_NORMAL,
            text_color=TEXT_MUTED,
            justify="center",
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 22))

        button(
            self.window,
            "Testrechnung laden",
            lambda: self._select(create_sample_invoice()),
            primary=True,
        ).grid(row=2, column=0, padx=(24, 8), sticky="ew")

        button(
            self.window,
            "Testgutschrift laden",
            lambda: self._select(create_sample_self_billed_invoice()),
            primary=True,
        ).grid(row=2, column=1, padx=(8, 24), sticky="ew")

        button(self.window, "Abbrechen", self.close).grid(
            row=3,
            column=0,
            columnspan=2,
            pady=(18, 0),
        )

    def _select(self, invoice):
        self.close()
        self.on_document_selected(invoice)

    def close(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None
