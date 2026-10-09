"""Editierbare Prüfansicht für erkannte Sammel-Final-Gutschriften."""

from __future__ import annotations

import customtkinter as ctk

from rechnungshelfer.application.settlement_review_service import (
    SettlementReview,
    SettlementReviewDelivery,
    SettlementReviewDetail,
)

from .components import HoverTooltip, button, form_entry
from .styles import APP_BG, BORDER, FONT_NORMAL, FONT_SECTION, FONT_SMALL, TEXT, TEXT_MUTED


class SettlementReviewDialog:
    def __init__(self, parent, controller, draft):
        self.parent = parent
        self.controller = controller
        self.draft = draft
        self.review = controller.create_settlement_review(draft)
        self.window = None
        self.entries = {}
        self.status_box = None

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Abrechnung prüfen")
        self.window.geometry("1180x820")
        self.window.minsize(940, 650)
        self.window.configure(fg_color=APP_BG)
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self.window,
            text="Erkannte Abrechnung prüfen und korrigieren",
            font=FONT_SECTION,
            text_color="white",
        ).grid(row=0, column=0, padx=20, pady=(16, 10), sticky="w")

        body = ctk.CTkScrollableFrame(
            self.window,
            fg_color="#f8fafc",
            corner_radius=10,
        )
        body.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        row = 0
        row = self._section(
            body,
            row,
            "Gutschrift",
            (
                ("Gutschriftnummer", "credit_note_number", self.review.credit_note_number),
                ("Ausstellungsdatum", "credit_note_date", self.review.credit_note_date),
            ),
        )
        for index, delivery in enumerate(self.review.deliveries):
            prefix = f"deliveries.{index}"
            row = self._section(
                body,
                row,
                f"Lieferung {index + 1}",
                (
                    ("Lieferscheinnummer", f"{prefix}.ticket_number", delivery.ticket_number),
                    ("Lieferdatum", f"{prefix}.delivery_date", delivery.delivery_date),
                    ("Bezeichnung", f"{prefix}.grain_name", delivery.grain_name),
                    ("Ursprungsmenge kg", f"{prefix}.gross_quantity_kg", delivery.gross_quantity_kg),
                    ("Basispreis EUR/t", f"{prefix}.base_price_per_tonne", delivery.base_price_per_tonne),
                    ("Abrechnungsmenge kg", f"{prefix}.settlement_quantity_kg", delivery.settlement_quantity_kg),
                    ("Abrechnungspreis EUR/t", f"{prefix}.settlement_price_per_tonne", delivery.settlement_price_per_tonne),
                    ("Lieferbetrag EUR", f"{prefix}.net_amount", delivery.net_amount),
                ),
            )
            for detail_index, detail in enumerate(delivery.details):
                detail_prefix = f"{prefix}.details.{detail_index}"
                row = self._section(
                    body,
                    row,
                    f"Analysezeile {index + 1}.{detail_index + 1}",
                    (
                        ("Bezeichnung", f"{detail_prefix}.label", detail.label),
                        ("Analysewert", f"{detail_prefix}.analysis_value", detail.analysis_value),
                        ("Mengenänderung kg", f"{detail_prefix}.quantity_change_kg", detail.quantity_change_kg),
                        ("Preisänderung EUR/t", f"{detail_prefix}.price_change_per_tonne", detail.price_change_per_tonne),
                    ),
                )

        self._section(
            body,
            row,
            "Summen",
            (
                ("Steuersatz %", "vat_rate", self.review.vat_rate),
                ("Nettosumme EUR", "net_amount", self.review.net_amount),
                ("Umsatzsteuer EUR", "vat_amount", self.review.vat_amount),
                ("Gesamtbetrag EUR", "total_amount", self.review.total_amount),
                ("Abschlagszahlung EUR", "advance_payment", self.review.advance_payment),
                ("Gutschriftbetrag EUR", "credit_amount", self.review.credit_amount),
            ),
        )

        footer = ctk.CTkFrame(self.window, fg_color="transparent")
        footer.grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.status_box = ctk.CTkTextbox(
            footer,
            height=95,
            font=FONT_SMALL,
            wrap="word",
        )
        self.status_box.grid(row=0, column=0, columnspan=3, pady=(0, 10), sticky="ew")
        self._set_status(
            "Werte mit niedriger Erkennungssicherheit sind orange markiert. "
            "Korrekturen gelten nur in dieser Prüfansicht."
        )
        button(footer, "Erneut prüfen", self.validate, primary=True).grid(
            row=1, column=1, padx=8
        )
        button(footer, "Schließen", self.close).grid(row=1, column=2, padx=(8, 0))
        self.validate()

    def _section(self, parent, row, title, fields):
        frame = ctk.CTkFrame(
            parent,
            fg_color="white",
            border_width=1,
            border_color=BORDER,
            corner_radius=8,
        )
        frame.grid(row=row, column=0, padx=10, pady=7, sticky="ew")
        frame.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(
            frame,
            text=title,
            font=FONT_SECTION,
            text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, padx=12, pady=(9, 5), sticky="ew")
        for index, (label, path, field) in enumerate(fields):
            field_row = 1 + index // 2
            offset = (index % 2) * 2
            confidence = (
                f", {field.confidence:.0%}"
                if field.confidence is not None
                else ""
            )
            page = f" (S. {field.page_number}{confidence})" if field.page_number else ""
            ctk.CTkLabel(
                frame,
                text=f"{label}{page}",
                font=FONT_SMALL,
                text_color=TEXT_MUTED,
                anchor="w",
            ).grid(row=field_row, column=offset, padx=(12, 6), pady=5, sticky="w")
            entry = form_entry(frame, field.value, width=190)
            entry.grid(
                row=field_row,
                column=offset + 1,
                padx=(0, 12),
                pady=5,
                sticky="ew",
            )
            if field.confidence is not None and field.confidence < 0.85:
                entry.configure(border_color="#f59e0b", border_width=2)
            if field.source:
                HoverTooltip(entry, lambda source=field.source: f"OCR-Quelle:\n{source}")
            self.entries[path] = entry
        return row + 1

    def collect_review(self) -> SettlementReview:
        def updated(path, field):
            return field.with_value(self.entries[path].get())

        deliveries = []
        for index, delivery in enumerate(self.review.deliveries):
            prefix = f"deliveries.{index}"
            details = []
            for detail_index, detail in enumerate(delivery.details):
                detail_prefix = f"{prefix}.details.{detail_index}"
                details.append(
                    SettlementReviewDetail(
                        label=updated(f"{detail_prefix}.label", detail.label),
                        analysis_value=updated(
                            f"{detail_prefix}.analysis_value",
                            detail.analysis_value,
                        ),
                        quantity_change_kg=updated(
                            f"{detail_prefix}.quantity_change_kg",
                            detail.quantity_change_kg,
                        ),
                        price_change_per_tonne=updated(
                            f"{detail_prefix}.price_change_per_tonne",
                            detail.price_change_per_tonne,
                        ),
                    )
                )
            deliveries.append(
                SettlementReviewDelivery(
                    ticket_number=updated(f"{prefix}.ticket_number", delivery.ticket_number),
                    delivery_date=updated(f"{prefix}.delivery_date", delivery.delivery_date),
                    grain_name=updated(f"{prefix}.grain_name", delivery.grain_name),
                    gross_quantity_kg=updated(f"{prefix}.gross_quantity_kg", delivery.gross_quantity_kg),
                    base_price_per_tonne=updated(f"{prefix}.base_price_per_tonne", delivery.base_price_per_tonne),
                    settlement_quantity_kg=updated(f"{prefix}.settlement_quantity_kg", delivery.settlement_quantity_kg),
                    settlement_price_per_tonne=updated(f"{prefix}.settlement_price_per_tonne", delivery.settlement_price_per_tonne),
                    net_amount=updated(f"{prefix}.net_amount", delivery.net_amount),
                    details=tuple(details),
                )
            )
        return SettlementReview(
            credit_note_number=updated("credit_note_number", self.review.credit_note_number),
            credit_note_date=updated("credit_note_date", self.review.credit_note_date),
            deliveries=tuple(deliveries),
            vat_rate=updated("vat_rate", self.review.vat_rate),
            net_amount=updated("net_amount", self.review.net_amount),
            vat_amount=updated("vat_amount", self.review.vat_amount),
            total_amount=updated("total_amount", self.review.total_amount),
            advance_payment=updated("advance_payment", self.review.advance_payment),
            credit_amount=updated("credit_amount", self.review.credit_amount),
        )

    def validate(self):
        self.review = self.collect_review()
        result = self.controller.validate_settlement_review(self.review)
        for entry in self.entries.values():
            entry.configure(border_color=BORDER, border_width=1)
        for path, entry in self.entries.items():
            field = self._field_by_path(path)
            if field.confidence is not None and field.confidence < 0.85:
                entry.configure(border_color="#f59e0b", border_width=2)
        for issue in result.issues:
            entry = self.entries.get(issue.field_path)
            if entry is not None:
                entry.configure(
                    border_color="#ef4444" if issue.severity == "error" else "#f59e0b",
                    border_width=2,
                )
        if result.issues:
            self._set_status(
                "\n".join(
                    f"{'Fehler' if issue.severity == 'error' else 'Hinweis'}: {issue.message}"
                    for issue in result.issues
                )
            )
        else:
            self._set_status(
                "Alle Pflichtwerte und Summen sind rechnerisch schlüssig. "
                "Die Formularübernahme folgt im nächsten Entwicklungsschritt."
            )
        return result

    def _field_by_path(self, path):
        current = self.review
        parts = path.split(".")
        index = 0
        while index < len(parts):
            part = parts[index]
            if part in {"deliveries", "details"}:
                current = getattr(current, part)[int(parts[index + 1])]
                index += 2
            else:
                current = getattr(current, part)
                index += 1
        return current

    def _set_status(self, text):
        self.status_box.configure(state="normal")
        self.status_box.delete("1.0", "end")
        self.status_box.insert("1.0", text)
        self.status_box.configure(state="disabled")

    def close(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None


__all__ = ["SettlementReviewDialog"]
