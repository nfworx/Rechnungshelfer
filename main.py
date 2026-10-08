# main.py
import customtkinter as ctk
from tkinter import messagebox

from rechnungshelfer.gui.main_window import InvoiceGUI
from rechnungshelfer.controller import InvoiceController
from rechnungshelfer.repositories.migrations import DatabaseMigrationError
from updater.readiness import signal_ready
from rechnungshelfer.services.temp_report_service import (
    cleanup_current_temp_reports,
    cleanup_stale_temp_reports,
)


def _migration_error_message(error: DatabaseMigrationError) -> str:
    lines = [
        error.user_message,
        "",
        "Die Datenbank wurde nicht verändert.",
    ]
    if error.backup_path:
        lines.extend(("", f"Sicherung: {error.backup_path}"))
    return "\n".join(lines)


def main() -> int:
    cleanup_stale_temp_reports()
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    try:
        controller = InvoiceController()
    except DatabaseMigrationError as error:
        root.withdraw()
        messagebox.showerror(
            "Datenbank-Update nicht möglich",
            _migration_error_message(error),
            parent=root,
        )
        root.destroy()
        return 1

    gui = InvoiceGUI(root, controller, on_ready=signal_ready)

    def on_close():
        cleanup_current_temp_reports()
        controller.close()   # SQLite sauber schließen
        root.destroy()       # Fenster schließen

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
