# main.py
import customtkinter as ctk
from rechnungshelfer.gui.main_window import InvoiceGUI
from rechnungshelfer.controller import InvoiceController
from updater.readiness import signal_ready
from rechnungshelfer.services.temp_report_service import (
    cleanup_current_temp_reports,
    cleanup_stale_temp_reports,
)


if __name__ == "__main__":
    cleanup_stale_temp_reports()
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    controller = InvoiceController()
    controller.migrate_customers_from_invoices_if_empty()
    gui = InvoiceGUI(root, controller, on_ready=signal_ready)

    def on_close():
        cleanup_current_temp_reports()
        controller.close()   # SQLite sauber schließen
        root.destroy()       # Fenster schließen

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
