#date_fields.py
"""Datumseingaben und Datepicker-Anbindung fuer die Benutzeroberflaeche."""

import customtkinter as ctk
from tkcalendar import Calendar

from rechnungshelfer.services.input_validation_service import normalize_date_de, InputValidationError


def attach_date_validation(entry: ctk.CTkEntry, field_name: str, required=True):
    def validate(_event=None): 
        try:
            normalized = normalize_date_de(entry.get(), field_name, required)

            entry.delete(0, "end")
            entry.insert(0, normalized)
            entry.configure(border_color="green")
            return True

        except InputValidationError as e:
            entry.configure(border_color="red")
            print(e)
            return False

    entry.bind("<FocusOut>", validate, add="+")
    entry.bind("<Return>", validate, add="+")

    return validate


def open_datepicker(entry: ctk.CTkEntry, field_name="Datum"):
    dialog = ctk.CTkToplevel()
    dialog.title(f"{field_name} auswählen")
    dialog.geometry("300x320")
    dialog.grab_set()

    cal = Calendar(
        dialog,
        selectmode="day",
        date_pattern="dd.mm.yyyy"
    )
    cal.pack(padx=20, pady=20, fill="both", expand=True)

    def apply_date():
        selected = normalize_date_de(cal.get_date(), field_name)
        entry.delete(0, "end")
        entry.insert(0, selected)
        entry.configure(border_color="green")
        dialog.destroy()

    ctk.CTkButton(dialog, text="Übernehmen", command=apply_date).pack(pady=10)
