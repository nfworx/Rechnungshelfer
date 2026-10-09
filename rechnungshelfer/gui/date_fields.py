#date_fields.py
"""Datumseingaben und Datepicker-Anbindung fuer die Benutzeroberflaeche."""

import customtkinter as ctk
from tkcalendar import Calendar

from rechnungshelfer.services.input_validation_service import normalize_date_de, InputValidationError


DATEPICKER_WIDTH = 300
DATEPICKER_HEIGHT = 320
DATEPICKER_GAP = 6


def calculate_datepicker_position(
    *,
    anchor_x: int,
    anchor_y: int,
    anchor_width: int,
    anchor_height: int,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    """Positioniert den Dialog am Anker und haelt ihn auf dem Bildschirm."""
    x = anchor_x + anchor_width - DATEPICKER_WIDTH
    y = anchor_y + anchor_height + DATEPICKER_GAP

    if y + DATEPICKER_HEIGHT > screen_height:
        y = anchor_y - DATEPICKER_GAP - DATEPICKER_HEIGHT

    max_x = max(0, screen_width - DATEPICKER_WIDTH)
    max_y = max(0, screen_height - DATEPICKER_HEIGHT)
    return max(0, min(x, max_x)), max(0, min(y, max_y))


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


def apply_date_selection(
    entry: ctk.CTkEntry,
    selected_date,
    field_name="Datum",
    on_selected=None,
):
    """Uebernimmt ein Kalenderdatum in Feld und angebundenes Formularmodell."""

    selected = normalize_date_de(selected_date, field_name)
    entry.delete(0, "end")
    entry.insert(0, selected)
    entry.configure(border_color="green")
    if on_selected is not None:
        on_selected(selected)
    return selected


def open_datepicker(
    entry: ctk.CTkEntry,
    field_name="Datum",
    anchor=None,
    on_selected=None,
):
    parent = entry.winfo_toplevel()
    anchor = anchor or entry
    dialog = ctk.CTkToplevel(parent)
    dialog.withdraw()
    dialog.title(f"{field_name} auswählen")
    dialog.geometry(f"{DATEPICKER_WIDTH}x{DATEPICKER_HEIGHT}")
    dialog.transient(parent)

    cal = Calendar(
        dialog,
        selectmode="day",
        locale="de_DE",
        date_pattern="dd.mm.yyyy"
    )
    cal.pack(padx=20, pady=20, fill="both", expand=True)

    def apply_date():
        apply_date_selection(
            entry,
            cal.get_date(),
            field_name,
            on_selected,
        )
        dialog.destroy()

    attach_calendar_double_click(
        cal,
        apply_date,
        scheduler=dialog.after_idle,
    )

    ctk.CTkButton(dialog, text="Übernehmen", command=apply_date).pack(pady=10)

    dialog.update_idletasks()
    x, y = calculate_datepicker_position(
        anchor_x=anchor.winfo_rootx(),
        anchor_y=anchor.winfo_rooty(),
        anchor_width=anchor.winfo_width(),
        anchor_height=anchor.winfo_height(),
        screen_width=dialog.winfo_screenwidth(),
        screen_height=dialog.winfo_screenheight(),
    )
    dialog.geometry(f"{DATEPICKER_WIDTH}x{DATEPICKER_HEIGHT}+{x}+{y}")
    dialog.deiconify()
    dialog.grab_set()
    dialog.focus_force()


def attach_calendar_double_click(calendar, callback, *, scheduler=None):
    """Uebernimmt den markierten Tag per Doppelklick.

    ``tkcalendar.Calendar`` zeichnet die Tage in einem internen Widget. Die
    Bindung muss deshalb dort erfolgen; der Fallback haelt die Funktion auch
    fuer kuenftige Calendar-Implementierungen verwendbar.
    """

    event_target = getattr(calendar, "_calendar", calendar)

    def apply_after_selection(_event=None):
        if scheduler is None:
            callback()
        else:
            scheduler(callback)

    event_target.bind(
        "<Double-Button-1>",
        apply_after_selection,
        add="+",
    )
    return apply_after_selection
