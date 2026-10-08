"""Eingabedialoge fuer Lieferungen und Regeln der Getreideabrechnung."""

from __future__ import annotations

from collections.abc import Callable
from tkinter import messagebox

import customtkinter as ctk

from rechnungshelfer.domain.grain_models import GrainValidationError

from .components import button, form_entry, small_button
from .grain_form_mapper import (
    AnalysisFormValue,
    DeliveryFormValue,
    FeatureFormValue,
    RuleFormValue,
    build_preview_scheme,
)
from .styles import APP_BG, FONT_NORMAL, FONT_SMALL, TEXT, TEXT_MUTED


RULE_TYPES = {
    "Menge · Analysewert prozentual": (
        "quantity_deduction",
        "percentage_of_measurement",
    ),
    "Menge · Nur über Basiswert": ("quantity_deduction", "excess_over_basis"),
    "Menge · Fester kg-Abzug": ("quantity_deduction", "fixed_quantity"),
    "Menge · Staffel": ("quantity_deduction", "tiered"),
    "Preis · Fester Betrag EUR/t": ("price_adjustment", "absolute_per_tonne"),
    "Preis · Analyse über Basiswert": (
        "price_adjustment",
        "excess_over_basis",
    ),
    "Preis · Prozent vom Preis": ("price_adjustment", "percentage_of_price"),
    "Preis · Analyse-Staffel": ("price_adjustment", "tiered"),
    "Kosten · Fester Betrag EUR": ("cost", "fixed_amount"),
}
RULE_TYPE_LABELS = {value: label for label, value in RULE_TYPES.items()}
RULE_REFERENCES = {
    "Bruttomenge": ("gross_quantity", ""),
    "Verbleibende Menge": ("remaining_quantity", ""),
    "Basispreis": ("", "base_price"),
    "Laufender Preis": ("", "running_price"),
    "Ohne Bezug": ("", ""),
}
REFERENCE_LABELS = {value: label for label, value in RULE_REFERENCES.items()}
RULE_DIRECTIONS = {
    "Abzug": "deduction",
    "Zuschlag": "surcharge",
}
DIRECTION_LABELS = {value: label for label, value in RULE_DIRECTIONS.items()}
GRAIN_TYPES = {
    "Weizen": "wheat",
    "Gerste": "barley",
    "Roggen": "rye",
    "Triticale": "triticale",
    "Mais": "maize",
}
GRAIN_TYPE_LABELS = {value: label for label, value in GRAIN_TYPES.items()}


class DeliveryDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        *,
        delivery_id: str,
        features: tuple[FeatureFormValue, ...],
        on_save: Callable[[DeliveryFormValue], bool],
        value: DeliveryFormValue | None = None,
        default_grain_type_code: str = "wheat",
    ):
        super().__init__(parent)
        self.title("Lieferung bearbeiten" if value else "Lieferung hinzufügen")
        self.geometry("650x520")
        self.configure(fg_color=APP_BG)
        self.transient(parent.winfo_toplevel())
        self.delivery_id = delivery_id
        self.features = features
        self.on_save = on_save
        existing_analyses = {
            analysis.feature_code: analysis
            for analysis in (value.analyses if value else ())
        }

        content = ctk.CTkScrollableFrame(self, fg_color="white")
        content.pack(fill="both", expand=True, padx=12, pady=12)
        content.grid_columnconfigure(1, weight=1)
        self.delivery_date = self._field(
            content, 0, "Lieferdatum", value.delivery_date if value else ""
        )
        self.ticket_number = self._field(
            content, 1, "Wiegeschein", value.ticket_number if value else ""
        )
        ctk.CTkLabel(
            content,
            text="Getreideart",
            font=FONT_NORMAL,
            text_color=TEXT,
        ).grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        self.grain_type = ctk.CTkOptionMenu(
            content,
            values=list(GRAIN_TYPES),
            height=28,
            font=FONT_SMALL,
        )
        grain_type_code = (
            value.grain_type_code if value else default_grain_type_code
        )
        self.grain_type.set(GRAIN_TYPE_LABELS.get(grain_type_code, "Weizen"))
        self.grain_type.grid(row=2, column=1, sticky="ew", pady=5)
        self.gross_quantity = self._field(
            content, 3, "Bruttomenge kg", value.gross_quantity_kg if value else ""
        )
        self.base_price = self._field(
            content,
            4,
            "Basispreis EUR/t",
            value.base_price_per_tonne if value else "",
        )

        ctk.CTkLabel(
            content,
            text="Analysewerte",
            font=("Segoe UI", 16, "bold"),
            text_color=TEXT,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(18, 5))
        self.analysis_entries = {}
        for index, feature in enumerate(features, start=6):
            current = existing_analyses.get(feature.code)
            label = f"{feature.label} ({feature.code})"
            if feature.required:
                label += " *"
            ctk.CTkLabel(
                content,
                text=label,
                font=FONT_SMALL,
                text_color=TEXT,
            ).grid(row=index, column=0, sticky="w", padx=(0, 10), pady=4)
            row = ctk.CTkFrame(content, fg_color="transparent")
            row.grid(row=index, column=1, sticky="ew", pady=4)
            raw = form_entry(row, current.raw_value if current else "", 130)
            raw.pack(side="left", padx=(0, 8))
            corrected = form_entry(
                row,
                current.corrected_value if current else "",
                130,
            )
            corrected.pack(side="left")
            ctk.CTkLabel(
                row,
                text="Wert / Korrektur",
                font=FONT_SMALL,
                text_color=TEXT_MUTED,
            ).pack(side="left", padx=8)
            self.analysis_entries[feature.code] = (raw, corrected)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(0, 12))
        button(actions, "Speichern", self._save, primary=True).pack(side="right")
        button(actions, "Abbrechen", self.destroy).pack(side="right", padx=8)
        self.after(20, self.grab_set)

    @staticmethod
    def _field(parent, row: int, label: str, value: str):
        ctk.CTkLabel(
            parent, text=label, font=FONT_NORMAL, text_color=TEXT
        ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        widget = form_entry(parent, value)
        widget.grid(row=row, column=1, sticky="ew", pady=5)
        return widget

    def _save(self):
        analyses = tuple(
            AnalysisFormValue(
                feature_code=feature.code,
                raw_value=self.analysis_entries[feature.code][0].get(),
                corrected_value=self.analysis_entries[feature.code][1].get(),
            )
            for feature in self.features
        )
        saved = self.on_save(
            DeliveryFormValue(
                id=self.delivery_id,
                delivery_date=self.delivery_date.get(),
                ticket_number=self.ticket_number.get(),
                grain_type_code=GRAIN_TYPES[self.grain_type.get()],
                gross_quantity_kg=self.gross_quantity.get(),
                base_price_per_tonne=self.base_price.get(),
                analyses=analyses,
            )
        )
        if saved:
            self.destroy()


class _FeatureRow:
    def __init__(self, parent, on_remove, value: FeatureFormValue | None = None):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        small_button(self.frame, "−", lambda: on_remove(self)).pack(side="left")
        self.code = form_entry(self.frame, value.code if value else "", 130)
        self.code.pack(side="left", padx=5)
        self.label = form_entry(self.frame, value.label if value else "", 220)
        self.label.pack(side="left", padx=5)
        self.required = ctk.CTkCheckBox(self.frame, text="Pflicht", font=FONT_SMALL)
        self.required.pack(side="left", padx=5)
        if value is None or value.required:
            self.required.select()

    def value(self) -> FeatureFormValue:
        return FeatureFormValue(
            code=self.code.get(),
            label=self.label.get(),
            required=bool(self.required.get()),
        )


class _RuleRow:
    def __init__(self, parent, on_remove, value: RuleFormValue | None = None):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        small_button(self.frame, "−", lambda: on_remove(self)).pack(side="left")
        self.code = form_entry(self.frame, value.code if value else "", 120)
        self.code.pack(side="left", padx=3)
        self.label = form_entry(self.frame, value.label if value else "", 150)
        self.label.pack(side="left", padx=3)
        self.kind = ctk.CTkOptionMenu(
            self.frame, values=list(RULE_TYPES), width=190, height=28, font=FONT_SMALL
        )
        kind = (
            RULE_TYPE_LABELS.get(
                (value.phase, value.kind),
                "Menge · Analysewert prozentual",
            )
            if value
            else "Menge · Analysewert prozentual"
        )
        self.kind.set(kind)
        self.kind.pack(side="left", padx=3)
        self.feature_code = form_entry(
            self.frame,
            value.feature_code if value else "",
            105,
        )
        self.feature_code.pack(side="left", padx=3)
        self.reference = ctk.CTkOptionMenu(
            self.frame,
            values=list(RULE_REFERENCES),
            width=160,
            height=28,
            font=FONT_SMALL,
        )
        reference = (
            REFERENCE_LABELS.get(
                (value.quantity_reference, value.price_reference),
                "Ohne Bezug",
            )
            if value
            else "Bruttomenge"
        )
        self.reference.set(reference)
        self.reference.pack(side="left", padx=3)
        self.direction = ctk.CTkOptionMenu(
            self.frame,
            values=list(RULE_DIRECTIONS),
            width=100,
            height=28,
            font=FONT_SMALL,
        )
        self.direction.set(
            DIRECTION_LABELS.get(value.direction, "Abzug")
            if value
            else "Abzug"
        )
        self.direction.pack(side="left", padx=3)
        self.parameters = form_entry(
            self.frame,
            value.parameters if value else "",
            210,
        )
        self.parameters.pack(side="left", padx=3)
        self.tiers = form_entry(self.frame, value.tiers if value else "", 280)
        self.tiers.pack(side="left", padx=3)

    def value(self, order: int) -> RuleFormValue:
        phase, kind = RULE_TYPES[self.kind.get()]
        quantity_reference, price_reference = RULE_REFERENCES[
            self.reference.get()
        ]
        return RuleFormValue(
            code=self.code.get(),
            label=self.label.get(),
            kind=kind,
            feature_code=self.feature_code.get(),
            quantity_reference=quantity_reference,
            parameters=self.parameters.get(),
            tiers=self.tiers.get(),
            order=order,
            phase=phase,
            direction=RULE_DIRECTIONS[self.direction.get()],
            price_reference=price_reference,
        )


class RuleEditorDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        *,
        grain_type_code: str,
        features: tuple[FeatureFormValue, ...],
        rules: tuple[RuleFormValue, ...],
        on_save: Callable[
            [tuple[FeatureFormValue, ...], tuple[RuleFormValue, ...]], None
        ],
    ):
        super().__init__(parent)
        self.title("Abrechnungsregeln")
        self.geometry("1180x650")
        self.configure(fg_color=APP_BG)
        self.transient(parent.winfo_toplevel())
        self.grain_type_code = grain_type_code
        self.on_save = on_save
        self.feature_rows: list[_FeatureRow] = []
        self.rule_rows: list[_RuleRow] = []

        content = ctk.CTkScrollableFrame(self, fg_color="white")
        content.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(
            content,
            text="Analysemerkmale",
            font=("Segoe UI", 17, "bold"),
            text_color=TEXT,
        ).pack(anchor="w")
        button(content, "+ Merkmal", lambda: self._add_feature()).pack(anchor="w", pady=5)
        self.feature_host = ctk.CTkFrame(content, fg_color="transparent")
        self.feature_host.pack(fill="x")
        for value in features:
            self._add_feature(value)

        ctk.CTkLabel(
            content,
            text="Mengen-, Preis- und Kostenregeln",
            font=("Segoe UI", 17, "bold"),
            text_color=TEXT,
        ).pack(anchor="w", pady=(18, 0))
        button(content, "+ Regel", lambda: self._add_rule()).pack(anchor="w", pady=5)
        ctk.CTkLabel(
            content,
            text=(
                "Code | Bezeichnung | Typ | Merkmal | Bezug | Richtung | "
                "Parameter | Staffeln\n"
                "Menge: factor=1,1 · basis_value=14 · amount_kg=100   "
                "Preis: amount_per_tonne=5 · percentage=2 · "
                "basis_value=14,5; amount_per_unit=2   "
                "Kosten: amount=25\n"
                "Staffel: ..14,5=0 | 14,5..16=2 | 16..=3,5"
            ),
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
            justify="left",
        ).pack(anchor="w")
        self.rule_host = ctk.CTkFrame(content, fg_color="transparent")
        self.rule_host.pack(fill="x", pady=5)
        for value in rules:
            self._add_rule(value)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(0, 12))
        button(actions, "Übernehmen", self._save, primary=True).pack(side="right")
        button(actions, "Abbrechen", self.destroy).pack(side="right", padx=8)
        self.after(20, self.grab_set)

    def _add_feature(self, value: FeatureFormValue | None = None):
        row = _FeatureRow(self.feature_host, self._remove_feature, value)
        row.frame.pack(fill="x", pady=2)
        self.feature_rows.append(row)

    def _remove_feature(self, row: _FeatureRow):
        row.frame.destroy()
        self.feature_rows.remove(row)

    def _add_rule(self, value: RuleFormValue | None = None):
        row = _RuleRow(self.rule_host, self._remove_rule, value)
        row.frame.pack(fill="x", pady=2)
        self.rule_rows.append(row)

    def _remove_rule(self, row: _RuleRow):
        row.frame.destroy()
        self.rule_rows.remove(row)

    def _save(self):
        features = tuple(row.value() for row in self.feature_rows)
        rules = tuple(row.value(index) for index, row in enumerate(self.rule_rows))
        try:
            build_preview_scheme(self.grain_type_code, features, rules)
        except (GrainValidationError, ValueError) as exc:
            messagebox.showerror("Abrechnungsregeln", str(exc), parent=self)
            return
        self.on_save(features, rules)
        self.destroy()
