"""Eingabedialoge fuer Lieferungen und Regeln der Getreideabrechnung."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from tkinter import messagebox

import customtkinter as ctk

from rechnungshelfer.domain.grain_models import GrainValidationError
from rechnungshelfer.services.format_service import parse_de
from rechnungshelfer.services.input_validation_service import (
    InputValidationError,
    normalize_date_de,
)

from .components import button, form_entry, small_button, style_entry
from .date_fields import attach_date_validation, open_datepicker
from .grain_form_mapper import (
    AnalysisFormValue,
    DeliveryFormValue,
    FeatureFormValue,
    RuleFormValue,
    build_preview_scheme,
    parse_parameters,
)
from .grain_rule_presets import grain_rule_preset
from .styles import APP_BG, FONT_NORMAL, FONT_SMALL, TEXT, TEXT_MUTED


RULE_TYPES = {
    "Mengenabzug · Anteil des Analysewerts": (
        "quantity_deduction",
        "percentage_of_measurement",
    ),
    "Mengenabzug · Nur oberhalb des Basiswerts": ("quantity_deduction", "excess_over_basis"),
    "Mengenabzug · Feste Menge in kg": ("quantity_deduction", "fixed_quantity"),
    "Mengenabzug · Nach Wertestaffel": ("quantity_deduction", "tiered"),
    "Preisabzug · Fester Betrag je Tonne": ("price_adjustment", "absolute_per_tonne"),
    "Preisabzug · Je Einheit oberhalb des Basiswerts": (
        "price_adjustment",
        "excess_over_basis",
    ),
    "Preisabzug · Prozent vom Preis": ("price_adjustment", "percentage_of_price"),
    "Preisabzug · Nach Wertestaffel": ("price_adjustment", "tiered"),
    "Kosten · Fester Betrag je Lieferung": ("cost", "fixed_amount"),
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
PARAMETER_FIELDS = {
    ("quantity_deduction", "percentage_of_measurement"): (
        ("factor", "Abzugsfaktor", "1,0 = 1 % Mengenabzug je Prozentpunkt"),
    ),
    ("quantity_deduction", "excess_over_basis"): (
        ("basis_value", "Freigrenze / Basiswert", "Nur der darüberliegende Anteil zählt"),
        ("factor", "Abzugsfaktor", "1,0 = 1 % Mengenabzug je Prozentpunkt"),
    ),
    ("quantity_deduction", "fixed_quantity"): (
        ("amount_kg", "Abzugsmenge", "kg"),
    ),
    ("price_adjustment", "absolute_per_tonne"): (
        ("amount_per_tonne", "Betrag", "EUR je Tonne"),
    ),
    ("price_adjustment", "excess_over_basis"): (
        ("basis_value", "Freigrenze / Basiswert", "Nur der darüberliegende Anteil zählt"),
        ("amount_per_unit", "Preisabzug je Einheit", "EUR/t je Prozentpunkt bzw. Messeinheit"),
    ),
    ("price_adjustment", "percentage_of_price"): (
        ("percentage", "Preisabzug", "% vom gewählten Preis"),
    ),
    ("cost", "fixed_amount"): (
        ("amount", "Betrag", "EUR je Lieferung"),
    ),
}
GRAIN_TYPES = {
    "Weizen": "wheat",
    "Gerste (Futtergerste)": "barley",
    "Braugerste": "malting_barley",
    "Hafer": "oats",
    "Roggen": "rye",
    "Mais": "maize",
    "Raps": "rapeseed",
}
GRAIN_TYPE_LABELS = {value: label for label, value in GRAIN_TYPES.items()}


def _tiers_for_display(value: str) -> str:
    """Uebersetzt die interne Staffelnotation in lesbaren Bedienertext."""

    result = []
    for part in (item.strip() for item in str(value or "").split("|")):
        if not part:
            continue
        interval, tier_value = (item.strip() for item in part.split("=", 1))
        lower, upper = (item.strip() for item in interval.split("..", 1))
        if lower and upper:
            boundary = f"{lower} bis unter {upper}"
        elif lower:
            boundary = f"ab {lower}"
        else:
            boundary = f"unter {upper}"
        result.append(f"{boundary}: {tier_value}")
    return " | ".join(result)


def _tiers_for_storage(value: str) -> str:
    """Uebersetzt lesbare Staffelgrenzen in die kompakte Domaenennotation."""

    result = []
    for part in (item.strip() for item in str(value or "").split("|")):
        if not part:
            continue
        if ":" not in part:
            raise GrainValidationError(
                "Staffel bitte als 'unter 72: 4', '72 bis unter 73: 3' "
                "oder 'ab 73: 0' eingeben."
            )
        boundary, tier_value = (item.strip() for item in part.split(":", 1))
        if boundary.startswith("unter "):
            interval = f"..{boundary[6:].strip()}"
        elif boundary.startswith("ab "):
            interval = f"{boundary[3:].strip()}.."
        elif " bis unter " in boundary:
            lower, upper = boundary.split(" bis unter ", 1)
            interval = f"{lower.strip()}..{upper.strip()}"
        else:
            raise GrainValidationError(
                f"Staffelgrenze '{boundary}' ist nicht verständlich."
            )
        result.append(f"{interval}={tier_value}")
    return " | ".join(result)


def delivery_input_errors(
    *,
    delivery_date: str,
    ticket_number: str,
    gross_quantity: str,
    base_price: str,
    features: tuple[FeatureFormValue, ...],
    analyses: dict[str, tuple[str, str]],
) -> dict[str, str]:
    """Validiert eine Lieferung feldbezogen vor dem Domain-Mapping."""

    errors = {}
    try:
        normalize_date_de(delivery_date, "Lieferdatum")
    except InputValidationError as exc:
        errors["delivery_date"] = str(exc)

    if not str(ticket_number or "").strip():
        errors["ticket_number"] = "Wiegescheinnummer fehlt."

    _validate_number(
        errors,
        "gross_quantity",
        gross_quantity,
        "Bruttomenge",
        strictly_positive=True,
    )
    _validate_number(
        errors,
        "base_price",
        base_price,
        "Basispreis",
        strictly_positive=False,
    )

    for feature in features:
        raw, corrected = analyses.get(feature.code, ("", ""))
        raw_key = f"analysis:{feature.code}:raw"
        corrected_key = f"analysis:{feature.code}:corrected"
        if feature.required and not str(raw or "").strip():
            errors[raw_key] = f"Analysewert {feature.label} fehlt."
        elif str(raw or "").strip():
            _validate_number(errors, raw_key, raw, feature.label)
        if str(corrected or "").strip():
            if not str(raw or "").strip():
                errors[corrected_key] = (
                    f"Korrektur für {feature.label} benötigt einen Ausgangswert."
                )
            else:
                _validate_number(
                    errors,
                    corrected_key,
                    corrected,
                    f"Korrektur {feature.label}",
                )
    return errors


def require_features_used_by_active_rules(
    features: tuple[FeatureFormValue, ...],
    rules: tuple[RuleFormValue, ...],
) -> tuple[FeatureFormValue, ...]:
    """Macht Analysewerte aktiver Regeln automatisch verpflichtend."""

    required_codes = {
        rule.feature_code
        for rule in rules
        if rule.enabled and rule.feature_code
    }
    return tuple(
        replace(feature, required=True)
        if feature.code in required_codes and not feature.required
        else feature
        for feature in features
    )


def _validate_number(
    errors: dict[str, str],
    key: str,
    value: str,
    label: str,
    *,
    strictly_positive: bool = False,
) -> None:
    if not str(value or "").strip():
        errors[key] = f"{label} fehlt."
        return
    try:
        number = parse_de(value)
    except ValueError:
        errors[key] = f"{label} ist keine gültige Zahl."
        return
    if number < 0 or (strictly_positive and number == 0):
        qualifier = "größer als null" if strictly_positive else "nicht negativ"
        errors[key] = f"{label} muss {qualifier} sein."


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
        self._entries = {}
        existing_analyses = {
            analysis.feature_code: analysis
            for analysis in (value.analyses if value else ())
        }

        content = ctk.CTkScrollableFrame(self, fg_color="white")
        content.pack(fill="both", expand=True, padx=12, pady=12)
        content.grid_columnconfigure(1, weight=1)
        self.delivery_date = self._date_field(
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
        self._entries.update(
            {
                "delivery_date": self.delivery_date,
                "ticket_number": self.ticket_number,
                "gross_quantity": self.gross_quantity,
                "base_price": self.base_price,
            }
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
            label = feature.label
            if feature.unit:
                label += f" ({feature.unit})"
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
            analysis_value = (
                (current.corrected_value or current.raw_value)
                if current
                else ""
            )
            raw = form_entry(row, analysis_value, 190)
            raw.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                row,
                text="Analysewert",
                font=FONT_SMALL,
                text_color=TEXT_MUTED,
            ).pack(side="left", padx=8)
            self.analysis_entries[feature.code] = raw
            self._entries[f"analysis:{feature.code}:raw"] = raw

        self._configure_validation()

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

    @staticmethod
    def _date_field(parent, row: int, label: str, value: str):
        ctk.CTkLabel(
            parent, text=label, font=FONT_NORMAL, text_color=TEXT
        ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
        field = ctk.CTkFrame(parent, fg_color="transparent")
        field.grid(row=row, column=1, sticky="ew", pady=5)
        field.grid_columnconfigure(0, weight=1)
        entry = form_entry(field, value)
        entry.grid(row=0, column=0, sticky="ew")
        calendar_button = ctk.CTkButton(
            field,
            text="📅",
            width=32,
            height=28,
            command=lambda: open_datepicker(
                entry,
                label,
                calendar_button,
            ),
        )
        calendar_button.grid(row=0, column=1, padx=(6, 0))
        attach_date_validation(entry, label, required=True)
        return entry

    def _analysis_values(self):
        return {
            feature_code: (entry.get(), "")
            for feature_code, entry in self.analysis_entries.items()
        }

    def _validation_errors(self):
        return delivery_input_errors(
            delivery_date=self.delivery_date.get(),
            ticket_number=self.ticket_number.get(),
            gross_quantity=self.gross_quantity.get(),
            base_price=self.base_price.get(),
            features=self.features,
            analyses=self._analysis_values(),
        )

    def _configure_validation(self):
        required_keys = {
            "delivery_date",
            "ticket_number",
            "gross_quantity",
            "base_price",
            *(
                f"analysis:{feature.code}:raw"
                for feature in self.features
                if feature.required
            ),
        }
        for key, entry in self._entries.items():
            style_entry(
                entry,
                required=key in required_keys,
                filled=bool(entry.get().strip()),
            )
            entry.bind(
                "<FocusOut>",
                lambda _event: self._validate_entries(),
                add="+",
            )

    def _validate_entries(self):
        errors = self._validation_errors()
        for key, entry in self._entries.items():
            if key in errors:
                entry.configure(border_color="#ef4444")
            else:
                required = key in {
                    "delivery_date",
                    "ticket_number",
                    "gross_quantity",
                    "base_price",
                } or any(
                    key == f"analysis:{feature.code}:raw" and feature.required
                    for feature in self.features
                )
                style_entry(
                    entry,
                    required=required,
                    filled=bool(entry.get().strip()),
                    focused=False,
                )
        return errors

    def _save(self):
        errors = self._validate_entries()
        if errors:
            first_key = next(iter(errors))
            first_entry = self._entries[first_key]
            first_entry.focus_set()
            messagebox.showerror(
                "Lieferung prüfen",
                "Bitte folgende Eingaben korrigieren:\n\n"
                + "\n".join(f"• {message}" for message in errors.values()),
                parent=self,
            )
            return
        normalized_date = normalize_date_de(
            self.delivery_date.get(),
            "Lieferdatum",
        )
        self.delivery_date.delete(0, "end")
        self.delivery_date.insert(0, normalized_date)
        analyses = tuple(
            AnalysisFormValue(
                feature_code=feature.code,
                raw_value=self.analysis_entries[feature.code].get(),
                corrected_value="",
            )
            for feature in self.features
        )
        saved = self.on_save(
            DeliveryFormValue(
                id=self.delivery_id,
                delivery_date=normalized_date,
                ticket_number=self.ticket_number.get().strip(),
                grain_type_code=GRAIN_TYPES[self.grain_type.get()],
                gross_quantity_kg=self.gross_quantity.get(),
                base_price_per_tonne=self.base_price.get(),
                analyses=analyses,
            )
        )
        if saved:
            self.destroy()


class _FeatureRow:
    def __init__(
        self,
        parent,
        on_remove,
        *,
        code: str,
        value: FeatureFormValue | None = None,
    ):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        small_button(self.frame, "−", lambda: on_remove(self)).pack(side="left")
        self.code = value.code if value else code
        self.label = form_entry(self.frame, value.label if value else "", 220)
        self.label.pack(side="left", padx=5)
        self.unit = form_entry(self.frame, value.unit if value else "%", 90)
        self.unit.pack(side="left", padx=5)
        self.required = ctk.CTkCheckBox(self.frame, text="Pflicht", font=FONT_SMALL)
        self.required.pack(side="left", padx=5)
        if value is None or value.required:
            self.required.select()

    def value(self) -> FeatureFormValue:
        return FeatureFormValue(
            code=self.code,
            label=self.label.get(),
            required=bool(self.required.get()),
            unit=self.unit.get(),
        )


class _RuleRow:
    NO_FEATURE = "Kein Analysemerkmal"

    def __init__(
        self,
        parent,
        on_remove,
        *,
        code: str,
        features: tuple[FeatureFormValue, ...],
        value: RuleFormValue | None = None,
    ):
        self.frame = ctk.CTkFrame(parent, fg_color="#f4f6f8", corner_radius=8)
        self.frame.grid_columnconfigure(1, weight=1)
        self.code = value.code if value else code
        self._features = features
        self._parameters = parse_parameters(value.parameters) if value else {}
        self.parameter_entries = {}

        header = ctk.CTkFrame(self.frame, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=4, sticky="ew", padx=10, pady=(8, 4))
        self.enabled = ctk.CTkCheckBox(header, text="Regel aktiv", font=FONT_SMALL)
        self.enabled.pack(side="left")
        if value is None or value.enabled:
            self.enabled.select()
        small_button(header, "−", lambda: on_remove(self)).pack(side="right")

        self._label(self.frame, 1, 0, "Bezeichnung")
        self._label(self.frame, 1, 1, "Wirkung")
        self._label(self.frame, 1, 2, "Analysemerkmal")
        self._label(self.frame, 1, 3, "Richtung")
        self.label = form_entry(self.frame, value.label if value else "", 210)
        self.label.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.kind = ctk.CTkOptionMenu(
            self.frame,
            values=list(RULE_TYPES),
            width=300,
            height=28,
            font=FONT_SMALL,
            command=lambda _choice: self._render_parameters(),
        )
        kind = (
            RULE_TYPE_LABELS.get(
                (value.phase, value.kind),
                "Mengenabzug · Anteil des Analysewerts",
            )
            if value
            else "Mengenabzug · Anteil des Analysewerts"
        )
        self.kind.set(kind)
        self.kind.grid(row=2, column=1, sticky="ew", padx=8, pady=(0, 8))

        self.feature_labels = {
            feature.label: feature.code for feature in self._features
        }
        feature_values = [self.NO_FEATURE, *self.feature_labels]
        self.feature = ctk.CTkOptionMenu(
            self.frame, values=feature_values, width=190, height=28, font=FONT_SMALL
        )
        current_feature = self.NO_FEATURE
        if value and value.feature_code:
            current_feature = next(
                (
                    feature.label
                    for feature in self._features
                    if feature.code == value.feature_code
                ),
                self.NO_FEATURE,
            )
        self.feature.set(current_feature)
        self.feature.grid(row=2, column=2, sticky="ew", padx=8, pady=(0, 8))

        self.direction = ctk.CTkOptionMenu(
            self.frame,
            values=list(RULE_DIRECTIONS),
            width=110,
            height=28,
            font=FONT_SMALL,
        )
        self.direction.set(
            DIRECTION_LABELS.get(value.direction, "Abzug") if value else "Abzug"
        )
        self.direction.grid(row=2, column=3, sticky="ew", padx=8, pady=(0, 8))

        self.details = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.details.grid(row=3, column=0, columnspan=4, sticky="ew", padx=4, pady=(0, 8))
        self._tiers = _tiers_for_display(value.tiers) if value else ""
        self._reference = (
            REFERENCE_LABELS.get(
                (value.quantity_reference, value.price_reference), "Ohne Bezug"
            )
            if value
            else "Bruttomenge"
        )
        self._render_parameters()

    @staticmethod
    def _label(parent, row, column, text):
        ctk.CTkLabel(
            parent, text=text, font=FONT_SMALL, text_color=TEXT_MUTED
        ).grid(row=row, column=column, sticky="w", padx=8)

    def _render_parameters(self):
        for entry in self.parameter_entries.values():
            self._parameters[entry._parameter_name] = entry.get()
        if getattr(self, "tiers", None) is not None:
            self._tiers = self.tiers.get()
        if hasattr(self, "reference"):
            self._reference = self.reference.get()
        for widget in self.details.winfo_children():
            widget.destroy()
        self.parameter_entries = {}

        phase_kind = RULE_TYPES[self.kind.get()]
        fields = PARAMETER_FIELDS.get(phase_kind, ())
        column = 0
        for name, label, help_text in fields:
            field = ctk.CTkFrame(self.details, fg_color="transparent")
            field.grid(row=0, column=column, sticky="w", padx=4)
            ctk.CTkLabel(
                field, text=label, font=FONT_SMALL, text_color=TEXT
            ).pack(anchor="w")
            display_value = str(self._parameters.get(name, "")).replace(".", ",")
            entry = form_entry(field, display_value, 160)
            entry._parameter_name = name
            entry.pack(anchor="w")
            ctk.CTkLabel(
                field, text=help_text, font=FONT_SMALL, text_color=TEXT_MUTED
            ).pack(anchor="w")
            self.parameter_entries[name] = entry
            column += 1

        if phase_kind[1] == "tiered":
            field = ctk.CTkFrame(self.details, fg_color="transparent")
            field.grid(row=0, column=column, sticky="ew", padx=4)
            ctk.CTkLabel(
                field,
                text="Wertestaffel",
                font=FONT_SMALL,
                text_color=TEXT,
            ).pack(anchor="w")
            self.tiers = form_entry(field, self._tiers, 460)
            self.tiers.pack(anchor="w")
            ctk.CTkLabel(
                field,
                text="Beispiel: unter 72: 4 | 72 bis unter 73: 3 | ab 73: 0",
                font=FONT_SMALL,
                text_color=TEXT_MUTED,
            ).pack(anchor="w")
            column += 1
        else:
            self.tiers = None

        field = ctk.CTkFrame(self.details, fg_color="transparent")
        field.grid(row=0, column=column, sticky="w", padx=4)
        ctk.CTkLabel(
            field, text="Berechnungsbasis", font=FONT_SMALL, text_color=TEXT
        ).pack(anchor="w")
        phase, kind = phase_kind
        if phase == "quantity_deduction":
            reference_values = ["Bruttomenge", "Verbleibende Menge"]
        elif phase == "price_adjustment" and kind in {
            "percentage_of_price",
            "tiered",
        }:
            reference_values = ["Basispreis", "Laufender Preis"]
        else:
            reference_values = ["Ohne Bezug"]
        self.reference = ctk.CTkOptionMenu(
            field,
            values=reference_values,
            width=160,
            height=28,
            font=FONT_SMALL,
        )
        selected_reference = (
            self._reference
            if self._reference in reference_values
            else reference_values[0]
        )
        self.reference.set(selected_reference)
        self._reference = selected_reference
        self.reference.pack(anchor="w")

    def _serialized_parameters(self, phase: str, kind: str) -> str:
        values = []
        for name, _label, _help in PARAMETER_FIELDS.get((phase, kind), ()):
            entry = self.parameter_entries[name]
            values.append(f"{name}={entry.get()}")
        if kind == "tiered" and phase == "price_adjustment":
            values.append("result_kind=percentage_of_price")
        return "; ".join(values)

    def value(self, order: int) -> RuleFormValue:
        phase, kind = RULE_TYPES[self.kind.get()]
        quantity_reference, price_reference = RULE_REFERENCES[
            self.reference.get()
        ]
        return RuleFormValue(
            code=self.code,
            label=self.label.get(),
            kind=kind,
            feature_code=self.feature_labels.get(self.feature.get(), ""),
            quantity_reference=quantity_reference,
            parameters=self._serialized_parameters(phase, kind),
            tiers=_tiers_for_storage(self.tiers.get()) if self.tiers else "",
            order=order,
            phase=phase,
            direction=RULE_DIRECTIONS[self.direction.get()],
            price_reference=price_reference,
            enabled=bool(self.enabled.get()),
        )


class RuleEditorDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        *,
        grain_type_code: str,
        harvest_year: int,
        rule_sets: dict[
            str,
            tuple[tuple[FeatureFormValue, ...], tuple[RuleFormValue, ...]],
        ],
        on_save: Callable[[dict, str | None], bool],
    ):
        super().__init__(parent)
        self.title("Abrechnungsregeln")
        self.geometry("1180x760")
        self.configure(fg_color=APP_BG)
        self.transient(parent.winfo_toplevel())
        self.grain_type_code = grain_type_code
        self.harvest_year = harvest_year
        self.rule_sets = dict(rule_sets)
        self.on_save = on_save
        self.feature_rows: list[_FeatureRow] = []
        self.rule_rows: list[_RuleRow] = []

        content = ctk.CTkScrollableFrame(self, fg_color="white")
        content.pack(fill="both", expand=True, padx=12, pady=12)
        selector = ctk.CTkFrame(content, fg_color="transparent")
        selector.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            selector,
            text="Regelwerk für Getreideart",
            font=("Segoe UI", 16, "bold"),
            text_color=TEXT,
        ).pack(side="left", padx=(0, 12))
        self.grain_type = ctk.CTkOptionMenu(
            selector,
            values=list(GRAIN_TYPES),
            width=190,
            height=32,
            font=FONT_NORMAL,
            command=self._change_grain_type,
        )
        self.grain_type.set(GRAIN_TYPE_LABELS.get(grain_type_code, "Weizen"))
        self.grain_type.pack(side="left")
        ctk.CTkLabel(
            selector,
            text=f"Erntejahr {harvest_year} · Entwurf",
            font=FONT_NORMAL,
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=18)
        preset = grain_rule_preset(grain_type_code)
        self.notice = ctk.CTkFrame(content, fg_color="#fff4d6", corner_radius=8)
        self.notice.pack(fill="x", pady=(0, 14))
        self.notice_label = ctk.CTkLabel(
            self.notice,
            text=f"Praxisvorlage {preset.label}: {preset.note}",
            font=FONT_SMALL,
            text_color=TEXT,
            wraplength=850,
            justify="left",
        )
        self.notice_label.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        button(
            self.notice,
            "Praxisvorlage neu laden",
            self._load_preset,
        ).pack(side="right", padx=10, pady=8)
        ctk.CTkLabel(
            content,
            text="Analysemerkmale",
            font=("Segoe UI", 17, "bold"),
            text_color=TEXT,
        ).pack(anchor="w")
        button(content, "+ Merkmal", lambda: self._add_feature()).pack(anchor="w", pady=5)
        ctk.CTkLabel(
            content,
            text=(
                "Bezeichnung | Einheit | Pflichtfeld  · Merkmale aktiver Regeln "
                "werden automatisch zu Pflichtfeldern"
            ),
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
        ).pack(anchor="w")
        self.feature_host = ctk.CTkFrame(content, fg_color="transparent")
        self.feature_host.pack(fill="x")

        ctk.CTkLabel(
            content,
            text="Mengen-, Preis- und Kostenregeln",
            font=("Segoe UI", 17, "bold"),
            text_color=TEXT,
        ).pack(anchor="w", pady=(18, 0))
        button(content, "+ Regel", lambda: self._add_rule()).pack(anchor="w", pady=5)
        self.rule_host = ctk.CTkFrame(content, fg_color="transparent")
        self.rule_host.pack(fill="x", pady=5)
        features, rules = self.rule_sets[grain_type_code]
        self._show_rule_set(features, rules)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(0, 12))
        button(
            actions,
            "Entwurf speichern",
            lambda: self._save(activate=False),
            primary=True,
        ).pack(side="right")
        button(
            actions,
            "Als neue Version aktivieren",
            self._activate,
        ).pack(side="right", padx=8)
        button(actions, "Abbrechen", self.destroy).pack(side="right", padx=8)
        self.after(20, self.grab_set)

    def _add_feature(self, value: FeatureFormValue | None = None):
        row = _FeatureRow(
            self.feature_host,
            self._remove_feature,
            code=value.code if value else self._next_code("feature"),
            value=value,
        )
        row.frame.pack(fill="x", pady=2)
        self.feature_rows.append(row)

    def _remove_feature(self, row: _FeatureRow):
        row.frame.destroy()
        self.feature_rows.remove(row)

    def _add_rule(self, value: RuleFormValue | None = None):
        row = _RuleRow(
            self.rule_host,
            self._remove_rule,
            code=value.code if value else self._next_code("rule"),
            features=tuple(feature.value() for feature in self.feature_rows),
            value=value,
        )
        row.frame.pack(fill="x", pady=5)
        self.rule_rows.append(row)

    def _remove_rule(self, row: _RuleRow):
        row.frame.destroy()
        self.rule_rows.remove(row)

    def _next_code(self, prefix: str) -> str:
        used = {
            *(row.code for row in self.feature_rows),
            *(row.code for row in self.rule_rows),
        }
        number = 1
        while f"{prefix}-{number}" in used:
            number += 1
        return f"{prefix}-{number}"

    def _load_preset(self):
        preset = grain_rule_preset(self.grain_type_code)
        if not messagebox.askyesno(
            "Praxisvorlage laden",
            "Die aktuellen Merkmale und Regeln werden durch die Praxisvorlage "
            f"für {preset.label} ersetzt. Fortfahren?",
            parent=self,
        ):
            return
        self._show_rule_set(preset.features, preset.rules)

    def _current_values(self):
        features = tuple(row.value() for row in self.feature_rows)
        rules = tuple(row.value(index) for index, row in enumerate(self.rule_rows))
        features = require_features_used_by_active_rules(features, rules)
        required_codes = {feature.code for feature in features if feature.required}
        for row in self.feature_rows:
            if row.code in required_codes:
                row.required.select()
        return features, rules

    def _show_rule_set(self, features, rules):
        for row in (*self.feature_rows, *self.rule_rows):
            row.frame.destroy()
        self.feature_rows.clear()
        self.rule_rows.clear()
        for value in features:
            self._add_feature(value)
        for value in rules:
            self._add_rule(value)

    def _change_grain_type(self, label: str):
        self.rule_sets[self.grain_type_code] = self._current_values()
        self.grain_type_code = GRAIN_TYPES[label]
        preset = grain_rule_preset(self.grain_type_code)
        self.notice_label.configure(
            text=f"Praxisvorlage {preset.label}: {preset.note}"
        )
        features, rules = self.rule_sets.get(
            self.grain_type_code,
            (preset.features, preset.rules),
        )
        self._show_rule_set(features, rules)

    def _activate(self):
        grain_label = GRAIN_TYPE_LABELS[self.grain_type_code]
        if not messagebox.askyesno(
            "Regelwerk aktivieren",
            f"Für {grain_label} im Erntejahr {self.harvest_year} wird eine neue "
            "unveränderliche Version angelegt. Fortfahren?",
            parent=self,
        ):
            return
        self._save(activate=True)

    def _save(self, *, activate: bool):
        self.rule_sets[self.grain_type_code] = self._current_values()
        try:
            for grain_type_code, (features, rules) in self.rule_sets.items():
                build_preview_scheme(grain_type_code, features, rules)
        except (GrainValidationError, ValueError) as exc:
            messagebox.showerror("Abrechnungsregeln", str(exc), parent=self)
            return
        activated_grain = self.grain_type_code if activate else None
        if self.on_save(self.rule_sets, activated_grain):
            self.destroy()
