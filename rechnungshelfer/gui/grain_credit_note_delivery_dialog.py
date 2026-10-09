"""Kompakter Editor fuer eine strukturierte Getreidegutschrift-Lieferung."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from rechnungshelfer.application.settlement_review_service import (
    ReviewField,
    SettlementReviewDelivery,
    SettlementReviewDetail,
)
from rechnungshelfer.services.format_service import parse_de
from rechnungshelfer.services.input_validation_service import (
    InputValidationError,
    normalize_date_de,
)

from .components import button, clear_frame, form_entry, small_button
from .grain_settlement_dialogs import GRAIN_TYPES, GRAIN_TYPE_LABELS
from .styles import APP_BG, FONT_NORMAL, FONT_SECTION, FONT_SMALL, TEXT


_UNASSIGNED_GRAIN_TYPE = "Nicht zugeordnet"


class GrainCreditNoteDeliveryDialog(ctk.CTkToplevel):
    """Bearbeitet Belegwerte einer einzelnen bestaetigten Lieferung."""

    def __init__(self, parent, delivery, on_save):
        super().__init__(parent)
        self.delivery = delivery
        self.on_save = on_save
        self.title("Lieferung bearbeiten")
        self.geometry("760x720")
        self.minsize(680, 560)
        self.configure(fg_color=APP_BG)
        self.transient(parent.winfo_toplevel())

        body = ctk.CTkScrollableFrame(self, fg_color="white")
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.grid_columnconfigure(1, weight=1)

        self.ticket_number = self._field(
            body, 0, "Lieferscheinnummer", delivery.ticket_number.value
        )
        self.delivery_date = self._field(
            body, 1, "Lieferdatum", delivery.delivery_date.value
        )
        self.grain_name = self._field(
            body, 2, "Getreidebezeichnung", delivery.grain_name.value
        )
        ctk.CTkLabel(
            body,
            text="Getreideart",
            font=FONT_NORMAL,
            text_color=TEXT,
        ).grid(row=3, column=0, sticky="w", padx=(0, 10), pady=5)
        self.grain_type = ctk.CTkOptionMenu(
            body,
            values=[_UNASSIGNED_GRAIN_TYPE, *GRAIN_TYPES],
            height=28,
            font=FONT_SMALL,
        )
        self.grain_type.set(
            GRAIN_TYPE_LABELS.get(
                delivery.grain_type_code,
                _UNASSIGNED_GRAIN_TYPE,
            )
        )
        self.grain_type.grid(row=3, column=1, sticky="ew", pady=5)
        self.gross_quantity = self._field(
            body, 4, "Ursprungsmenge kg", delivery.gross_quantity_kg.value
        )
        self.base_price = self._field(
            body, 5, "Basispreis EUR/t", delivery.base_price_per_tonne.value
        )
        self.settlement_quantity = self._field(
            body,
            6,
            "Abrechnungsmenge kg",
            delivery.settlement_quantity_kg.value,
        )
        self.settlement_price = self._field(
            body,
            7,
            "Abrechnungspreis EUR/t",
            delivery.settlement_price_per_tonne.value,
        )

        ctk.CTkLabel(
            body,
            text="Analyse- und Anpassungszeilen",
            font=FONT_SECTION,
            text_color=TEXT,
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(18, 6))
        self.detail_host = ctk.CTkFrame(body, fg_color="transparent")
        self.detail_host.grid(row=9, column=0, columnspan=2, sticky="ew")
        self.detail_host.grid_columnconfigure(0, weight=1)
        self._detail_values = list(delivery.details)
        self._detail_entries = []
        self._render_details()
        button(body, "+ Analysezeile", self._add_detail).grid(
            row=10,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(8, 4),
        )

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(0, 12))
        button(actions, "Übernehmen", self._save, primary=True).pack(side="right")
        button(actions, "Abbrechen", self.destroy).pack(side="right", padx=8)
        self.after(20, self.grab_set)

    @staticmethod
    def _field(parent, row, label, value):
        ctk.CTkLabel(
            parent,
            text=label,
            font=FONT_NORMAL,
            text_color=TEXT,
        ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        entry = form_entry(parent, value)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        return entry

    def _render_details(self):
        clear_frame(self.detail_host)
        self._detail_entries = []
        headers = (
            "Bezeichnung",
            "Analysewert",
            "Menge kg",
            "Preis EUR/t",
            "Betrag EUR",
            "",
        )
        for column, label in enumerate(headers):
            ctk.CTkLabel(
                self.detail_host,
                text=label,
                font=FONT_SMALL,
                text_color=TEXT,
            ).grid(row=0, column=column, padx=3, pady=3, sticky="w")
        for index, detail in enumerate(self._detail_values, start=1):
            entries = (
                form_entry(self.detail_host, detail.label.value, 170),
                form_entry(self.detail_host, detail.analysis_value.value, 90),
                form_entry(self.detail_host, detail.quantity_change_kg.value, 90),
                form_entry(self.detail_host, detail.price_change_per_tonne.value, 90),
                form_entry(self.detail_host, detail.amount_change.value, 90),
            )
            for column, entry in enumerate(entries):
                entry.grid(row=index, column=column, padx=3, pady=3, sticky="ew")
            small_button(
                self.detail_host,
                "×",
                lambda item=index - 1: self._remove_detail(item),
            ).grid(row=index, column=5, padx=3, pady=3)
            self._detail_entries.append(entries)

    def _snapshot_details(self):
        values = []
        for index, entries in enumerate(self._detail_entries):
            previous = self._detail_values[index]
            values.append(
                SettlementReviewDetail(
                    label=previous.label.with_value(entries[0].get()),
                    analysis_value=previous.analysis_value.with_value(entries[1].get()),
                    quantity_change_kg=previous.quantity_change_kg.with_value(
                        entries[2].get()
                    ),
                    price_change_per_tonne=(
                        previous.price_change_per_tonne.with_value(entries[3].get())
                    ),
                    amount_change=previous.amount_change.with_value(entries[4].get()),
                )
            )
        return values

    def _add_detail(self):
        self._detail_values = self._snapshot_details()
        self._detail_values.append(
            SettlementReviewDetail(
                label=ReviewField(""),
                analysis_value=ReviewField(""),
                quantity_change_kg=ReviewField(""),
                price_change_per_tonne=ReviewField(""),
                amount_change=ReviewField(""),
            )
        )
        self._render_details()

    def _remove_detail(self, index):
        self._detail_values = self._snapshot_details()
        del self._detail_values[index]
        self._render_details()

    def _validation_errors(self, details):
        errors = []
        for label, value in (
            ("Lieferscheinnummer", self.ticket_number.get()),
            ("Getreidebezeichnung", self.grain_name.get()),
        ):
            if not value.strip():
                errors.append(f"{label} fehlt.")
        try:
            normalize_date_de(self.delivery_date.get(), "Lieferdatum")
        except InputValidationError as exc:
            errors.append(str(exc))
        for label, entry, positive in (
            ("Ursprungsmenge", self.gross_quantity, True),
            ("Basispreis", self.base_price, False),
            ("Abrechnungsmenge", self.settlement_quantity, True),
            ("Abrechnungspreis", self.settlement_price, False),
        ):
            try:
                value = parse_de(entry.get())
                if value < 0 or (positive and value == 0):
                    raise ValueError
            except ValueError:
                errors.append(f"{label} ist ungültig.")
        for index, detail in enumerate(details, start=1):
            if not detail.label.value.strip():
                errors.append(f"Bezeichnung der Analysezeile {index} fehlt.")
            for label, field, required in (
                ("Analysewert", detail.analysis_value, True),
                ("Mengenänderung", detail.quantity_change_kg, False),
                ("Preisänderung", detail.price_change_per_tonne, False),
                ("Betragsänderung", detail.amount_change, False),
            ):
                if not field.value.strip() and not required:
                    continue
                try:
                    parse_de(field.value)
                except ValueError:
                    errors.append(f"{label} in Analysezeile {index} ist ungültig.")
        return errors

    def _save(self):
        details = tuple(self._snapshot_details())
        errors = self._validation_errors(details)
        if errors:
            messagebox.showerror(
                "Lieferung prüfen",
                "Bitte folgende Eingaben korrigieren:\n\n"
                + "\n".join(f"• {error}" for error in errors),
                parent=self,
            )
            return
        updated = SettlementReviewDelivery(
            ticket_number=self.delivery.ticket_number.with_value(
                self.ticket_number.get().strip()
            ),
            delivery_date=self.delivery.delivery_date.with_value(
                normalize_date_de(self.delivery_date.get(), "Lieferdatum")
            ),
            grain_name=self.delivery.grain_name.with_value(
                self.grain_name.get().strip()
            ),
            gross_quantity_kg=self.delivery.gross_quantity_kg.with_value(
                self.gross_quantity.get()
            ),
            base_price_per_tonne=self.delivery.base_price_per_tonne.with_value(
                self.base_price.get()
            ),
            settlement_quantity_kg=(
                self.delivery.settlement_quantity_kg.with_value(
                    self.settlement_quantity.get()
                )
            ),
            settlement_price_per_tonne=(
                self.delivery.settlement_price_per_tonne.with_value(
                    self.settlement_price.get()
                )
            ),
            net_amount=self.delivery.net_amount,
            details=details,
            grain_type_code=(
                self.delivery.grain_type_code
                if self.grain_type.get() == _UNASSIGNED_GRAIN_TYPE
                else GRAIN_TYPES[self.grain_type.get()]
            ),
        )
        if self.on_save(updated):
            self.destroy()


__all__ = ["GrainCreditNoteDeliveryDialog"]
