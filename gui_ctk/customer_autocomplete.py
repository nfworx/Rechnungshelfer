#customer_autocomplete.py
import customtkinter as ctk


class CustomerAutocomplete:
    def __init__(self, parent, entry, controller, field, on_select):
        self.parent = parent
        self.entry = entry
        self.controller = controller
        self.field = field
        self.on_select = on_select

        self.popup = None
        self.items = []
        self._search_job = None

        entry.bind("<KeyRelease>", self._on_key_release, add="+")
        entry.bind("<FocusOut>", self._on_focus_out, add="+")

    # -------------------------
    # Tippen → Suche
    # -------------------------
    def _on_key_release(self, event=None):
        if self._search_job is not None:
            self.entry.after_cancel(self._search_job)
            self._search_job = None

        text = self.entry.get().strip()

        if len(text) < 2:
            self.close()
            return

        self._search_job = self.entry.after(
            150,
            lambda value=text: self._run_search(value),
        )

    def _run_search(self, text):
        self._search_job = None
        if text != self.entry.get().strip():
            return

        self.items = self.controller.search_customers(self.field, text)

        if not self.items:
            self.close()
            return

        self.show(self.items)

    # -------------------------
    # Popup anzeigen
    # -------------------------
    def show(self, customers):
        self.close()

        self.popup = ctk.CTkToplevel(self.parent)
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)

        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        w = self.entry.winfo_width()

        self.popup.geometry(f"{w}x{len(customers) * 40}+{x}+{y}")

        for customer in customers:
            text = (
                f"{customer.customer_number or '-'} | "
                f"{customer.name} | "
                f"{customer.postcode or ''} {customer.city or ''}"
            )

            btn = ctk.CTkButton(
                self.popup,
                text=text,
                anchor="w",
                height=36,
                command=lambda c=customer: self.select(c),
            )
            btn.pack(fill="x", padx=2, pady=1)

    # -------------------------
    # Auswahl
    # -------------------------
    def select(self, customer):
        self.close()
        self.on_select(customer)

    # -------------------------
    # Schließen
    # -------------------------
    def close(self):
        if self._search_job is not None:
            self.entry.after_cancel(self._search_job)
            self._search_job = None
        if self.popup and self.popup.winfo_exists():
            self.popup.destroy()
        self.popup = None

    def _on_focus_out(self, event=None):
        # kleines Delay, damit Klick auf Button noch funktioniert
        self.entry.after(150, self.close)
