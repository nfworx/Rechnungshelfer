"""Mehrlieferungs-Vorschau im Layout der Rechnungs- und Gutschriftmaske."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import sqlite3
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from rechnungshelfer.application.grain_credit_note_mapper import (
    grain_credit_note_creation_issues,
    grain_credit_note_from_calculation,
)
from rechnungshelfer.domain.grain_models import (
    GrainValidationError,
    SettlementBatchResult,
    SettlementResult,
)
from rechnungshelfer.domain.business_partner import BusinessPartnerRole
from rechnungshelfer.domain.models import DocumentType
from rechnungshelfer.services.format_service import format_de

from .components import (
    HoverTooltip,
    button,
    card,
    clear_frame,
    set_button_enabled,
    small_button,
)
from .grain_form_mapper import (
    AnalysisFormValue,
    DeliveryFormValue,
    FeatureFormValue,
    GrainSettlementForm,
    RuleFormValue,
    build_preview_inputs,
    calculate_settlement_preview,
    deserialize_rule_set,
    missing_required_analyses,
    parse_vat_rate,
    serialize_rule_set,
)
from .grain_settlement_dialogs import (
    GRAIN_TYPE_LABELS,
    DeliveryDialog,
    RuleEditorDialog,
    require_features_used_by_active_rules,
)
from .settlement_review_dialog import SettlementReviewDialog
from .grain_rule_presets import grain_rule_preset
from .business_partner_dialog import BusinessPartnerListDialog
from .party_card import PartyCard
from .styles import APP_BG, FONT_NORMAL, FONT_SECTION, FONT_SMALL, TEXT, TEXT_MUTED


_EXAMPLE_ANALYSIS_VALUES = {
    "moisture": "14,5",
    "dockage": "2,0",
    "hectolitre_weight": "76",
    "protein": "12,5",
    "falling_number": "250",
    "germination": "98",
    "whole_grain": "92",
    "oil_content": "40",
}


class GrainSettlementView(ctk.CTkFrame):
    """Ordnet Kopfdaten, Lieferungen und Summen wie die Belegmasken an."""

    def __init__(
        self,
        parent,
        controller,
        on_credit_note_created: Callable | None = None,
    ):
        super().__init__(parent, fg_color=APP_BG, corner_radius=0)
        self.controller = controller
        self.on_credit_note_created = on_credit_note_created
        self.document = controller.create_empty_invoice(
            DocumentType.SELF_BILLED_INVOICE
        )
        self.features: tuple[FeatureFormValue, ...] = ()
        self.rules: tuple[RuleFormValue, ...] = ()
        self.rule_sets: dict[
            str,
            tuple[tuple[FeatureFormValue, ...], tuple[RuleFormValue, ...]],
        ] = {}
        self.harvest_year = date.today().year
        self.deliveries: list[DeliveryFormValue] = []
        self.field_entries = {}
        self._next_delivery_number = 1
        self._last_result: SettlementBatchResult | None = None
        self.credit_note = None
        self.vat_variable = ctk.StringVar(master=self, value="— auswählen —")

        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_layout()
        self.reset_example()

    def _build_layout(self):
        self.top_grid = ctk.CTkFrame(self, fg_color=APP_BG, corner_radius=0)
        self.top_grid.grid(row=0, column=0, columnspan=2, sticky="ew")
        for column in range(3):
            self.top_grid.grid_columnconfigure(
                column,
                weight=1,
                uniform="grain_top_cards",
            )

        self.supplier_area = self._top_area(0, (0, 8))
        self.buyer_area = self._top_area(1, 8)
        self.info_area = self._top_area(2, (8, 0))

        self.delivery_area = ctk.CTkFrame(
            self,
            fg_color=APP_BG,
            corner_radius=0,
        )
        self.delivery_area.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 12),
            pady=(14, 0),
        )
        self.delivery_area.grid_columnconfigure(0, weight=1)
        self.delivery_area.grid_rowconfigure(0, weight=1)

        self.totals_area = ctk.CTkFrame(
            self,
            fg_color=APP_BG,
            corner_radius=0,
            width=310,
        )
        self.totals_area.grid(
            row=1,
            column=1,
            sticky="nsew",
            pady=(14, 0),
        )
        self.totals_area.grid_propagate(False)
        self._build_delivery_card()
        self._build_totals_card()

    def _top_area(self, column: int, padx):
        area = ctk.CTkFrame(self.top_grid, fg_color=APP_BG, corner_radius=0)
        area.grid(row=0, column=column, sticky="nsew", padx=padx)
        return area

    def _render_top_cards(self):
        for area in (self.supplier_area, self.buyer_area, self.info_area):
            clear_frame(area)
        self.field_entries.clear()

        supplier_card = PartyCard(
            self.supplier_area,
            "Lieferant",
            self.document.seller,
            field_entries=self.field_entries,
            exclude_fields=["country", "buyer_reference", "contact_name"],
            label_overrides={
                "supplier_number": "Geschäftspartnernummer (Lieferant/Kreditor)"
            },
            extra_fields=[
                (self.document.payment, ["iban", "bic", "account_holder"]),
            ],
            on_change=self._on_document_field_change,
        ).render()
        supplier_card.pack(fill="both", expand=True)

        PartyCard(
            self.buyer_area,
            "Käufer / Belegersteller (eigener Betrieb)",
            self.document.buyer,
            disabled=True,
            field_entries=self.field_entries,
            exclude_fields=[
                "country",
                "contact_name",
                "customer_number",
                "use_invoice_address_as_delivery",
            ],
            label_overrides={"leitweg_id": "Käuferreferenz (BT-10)"},
        ).render().pack(fill="both", expand=True)

        info_card = PartyCard(
            self.info_area,
            "Gutschriftsdaten",
            self.document.info,
            field_entries=self.field_entries,
            extra_fields=[(self.document.payment, ["payment_terms"])],
            exclude_fields=[
                "customization_id",
                "profile_id",
                "currency",
                "delivery_instruction",
                "delivery_note",
                "invoice_type_code",
            ],
            label_overrides={
                "invoice_number": "Gutschriftnummer",
                "invoice_date": "Ausstellungsdatum",
                "payment_due_date": "Auszahlungsdatum",
                "payment_terms": "Auszahlungsbedingungen",
            },
            on_change=self._on_document_field_change,
        ).render()
        info_card.pack(fill="both", expand=True)

    def _build_delivery_card(self):
        delivery_card = card(self.delivery_area, "Lieferungen / Wiegescheine")
        delivery_card.grid(row=0, column=0, sticky="nsew")
        delivery_card.grid_columnconfigure(0, weight=1)
        delivery_card.grid_rowconfigure(2, weight=1)

        actions = ctk.CTkFrame(delivery_card, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        self.add_button = button(
            actions,
            "+ Lieferung",
            self.add_delivery,
            primary=True,
        )
        self.add_button.pack(side="left")
        self.calculate_button = button(actions, "Neu berechnen", self.calculate)
        self.calculate_button.pack(side="left", padx=8)
        self.rule_button = button(actions, "Regeln bearbeiten", self.edit_rules)
        self.rule_button.pack(side="left")
        self.example_button = button(
            actions,
            "Beispiel zurücksetzen",
            self.reset_example,
        )
        self.example_button.pack(
            side="left",
            padx=8,
        )
        self.edit_credit_note_button = button(
            actions,
            "Getreidegutschrift bearbeiten",
            self.edit_credit_note,
            primary=True,
        )
        self.status_label = ctk.CTkLabel(
            actions,
            text="",
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
        )
        self.status_label.pack(side="right")

        self.delivery_host = ctk.CTkScrollableFrame(
            delivery_card,
            fg_color="transparent",
        )
        self.delivery_host.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=14,
            pady=(0, 14),
        )

    def _build_totals_card(self):
        totals = card(self.totals_area, "Summen")
        totals.pack(fill="both", expand=True)
        totals.grid_columnconfigure(0, weight=1)
        totals.grid_columnconfigure(1, weight=0)
        self.total_rows = {}
        definitions = (
            ("gross", "Bruttomenge"),
            ("deduction", "Mengenabzug"),
            ("settlement", "Abrechnungsmenge"),
            ("base_amount", "Basiswarenwert"),
            ("money_deduction", "Preis-/Kostenabzug"),
            ("net_amount", "Nettoabrechnungsbetrag"),
        )
        for row, (key, label) in enumerate(definitions, start=1):
            is_total = key == "net_amount"
            font = FONT_SECTION if is_total else FONT_SMALL
            ctk.CTkLabel(
                totals,
                text=label,
                font=font,
                text_color=TEXT,
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=14, pady=(8, 3))
            value = ctk.CTkLabel(
                totals,
                text="–",
                font=font,
                text_color=TEXT,
                anchor="e",
            )
            value.grid(row=row, column=1, sticky="e", padx=14, pady=(8, 3))
            self.total_rows[key] = value

        ctk.CTkLabel(
            totals,
            text="Umsatzsteuer",
            font=FONT_SMALL,
            text_color=TEXT,
            anchor="w",
        ).grid(row=7, column=0, sticky="w", padx=14, pady=(14, 3))
        ctk.CTkOptionMenu(
            totals,
            values=["— auswählen —", "0 %", "7 %", "7,8 %", "19 %"],
            variable=self.vat_variable,
            command=lambda _value: self._refresh_tax_totals(),
            width=115,
        ).grid(row=7, column=1, sticky="e", padx=14, pady=(14, 3))

        for row, key, label, is_total in (
            (8, "tax_amount", "Umsatzsteuer", False),
            (9, "payable_amount", "Auszahlungsbetrag", True),
        ):
            font = FONT_SECTION if is_total else FONT_SMALL
            ctk.CTkLabel(
                totals,
                text=label,
                font=font,
                text_color=TEXT,
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=14, pady=(8, 3))
            value = ctk.CTkLabel(
                totals,
                text="—",
                font=font,
                text_color=TEXT,
                anchor="e",
            )
            value.grid(row=row, column=1, sticky="e", padx=14, pady=(8, 3))
            self.total_rows[key] = value

        ctk.CTkLabel(
            totals,
            text=(
                "Beim Preis-/Kostenabzug bedeutet ein negativer Wert "
                "einen Zuschlag."
            ),
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
            wraplength=270,
            justify="left",
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=14, pady=12)

        self.create_button = button(
            totals,
            "Getreidegutschrift erstellen",
            self.create_credit_note,
            primary=True,
        )
        self.create_button.grid(
            row=11,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(0, 8),
        )
        HoverTooltip(self.create_button, self._credit_note_creation_hint)
        self._refresh_create_button()

        output_buttons = (
            ("PDF erstellen", 12),
            ("HTML erstellen", 13),
        )
        for label, row in output_buttons:
            output_button = button(totals, label, lambda: None)
            output_button.grid(
                row=row,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=14,
                pady=(0, 8 if row < 13 else 14),
            )
            set_button_enabled(output_button, False)

    def create_credit_note(self) -> bool:
        """Erzeugt aus der geprüften Abrechnung eine bearbeitbare Gutschrift."""

        if not self.calculate():
            return False

        try:
            form = self._form_value()
            deliveries, scheme = build_preview_inputs(form)
            vat_rate = parse_vat_rate(form.vat_rate)
            credit_note = grain_credit_note_from_calculation(
                self.document,
                deliveries,
                self._last_result,
                vat_rate,
                scheme,
            )
        except (GrainValidationError, ValueError, ArithmeticError) as exc:
            messagebox.showerror(
                "Gutschrift erstellen",
                str(exc),
                parent=self,
            )
            return False

        if not messagebox.askyesno(
            "Getreidegutschrift erstellen",
            "Die berechneten Werte werden als strukturierte Getreidegutschrift "
            "übernommen und nicht automatisch gespeichert. Fortfahren?",
            parent=self,
        ):
            return False
        self.load_credit_note(credit_note, preserve_document=True)
        if self.on_credit_note_created is not None:
            self.on_credit_note_created(credit_note)
        return True

    def load_credit_note(self, credit_note, *, preserve_document=False):
        """Öffnet einen bestätigten Endbeleg im Getreide-Arbeitsbereich."""

        self.credit_note = credit_note
        self._last_result = None
        if not preserve_document:
            self.document = self.controller.create_empty_invoice(
                DocumentType.SELF_BILLED_INVOICE
            )
        self.document.info.invoice_number = credit_note.credit_note_number
        self.document.info.invoice_date = credit_note.credit_note_date.strftime(
            "%d.%m.%Y"
        )
        for field in credit_note.supplier.__dataclass_fields__:
            setattr(self.document.seller, field, getattr(credit_note.supplier, field))
        for field in credit_note.payment.__dataclass_fields__:
            setattr(self.document.payment, field, getattr(credit_note.payment, field))
        self.vat_variable.set(f"{str(credit_note.vat_rate).replace('.', ',')} %")
        self._render_top_cards()
        self._set_credit_note_mode(True)
        self._render_credit_note_deliveries(credit_note)
        self._show_credit_note_totals(credit_note)
        self.status_label.configure(
            text=f"{len(credit_note.deliveries)} Lieferungen · Getreidegutschrift"
        )

    def edit_credit_note(self):
        if self.credit_note is None:
            return
        try:
            current = replace(
                self.credit_note,
                credit_note_number=self.document.info.invoice_number.strip(),
                credit_note_date=datetime.strptime(
                    self.document.info.invoice_date.strip(),
                    "%d.%m.%Y",
                ).date(),
                supplier=replace(
                    self.credit_note.supplier,
                    **{
                        field: str(getattr(self.document.seller, field)).strip()
                        for field in self.credit_note.supplier.__dataclass_fields__
                    },
                ),
                payment=replace(
                    self.credit_note.payment,
                    **{
                        field: str(getattr(self.document.payment, field)).strip()
                        for field in self.credit_note.payment.__dataclass_fields__
                    },
                ),
            )
        except ValueError:
            messagebox.showerror(
                "Getreidegutschrift bearbeiten",
                "Gutschriftnummer oder Ausstellungsdatum ist ungültig.",
                parent=self,
            )
            return
        review = self.controller.create_settlement_review_from_credit_note(current)
        SettlementReviewDialog(
            self,
            self.controller,
            None,
            lambda note: self.load_credit_note(note, preserve_document=True),
            review=review,
        ).open()

    def _set_credit_note_mode(self, enabled):
        for control in (
            self.add_button,
            self.calculate_button,
            self.rule_button,
            self.example_button,
        ):
            set_button_enabled(control, not enabled)
        self._refresh_create_button()
        if enabled:
            self.edit_credit_note_button.pack(side="left", padx=8)
        else:
            self.edit_credit_note_button.pack_forget()

    def _render_credit_note_deliveries(self, credit_note):
        clear_frame(self.delivery_host)
        headers = (
            "Datum",
            "Lieferschein",
            "Getreideart",
            "Analyse / Abrechnungsposition",
            "Menge kg",
            "Δ Menge kg",
            "Δ Wert EUR",
            "Betrag EUR",
        )
        for column, title in enumerate(headers):
            self.delivery_host.grid_columnconfigure(
                column,
                weight=1 if column == 3 else 0,
            )
            ctk.CTkLabel(
                self.delivery_host,
                text=title,
                font=("Segoe UI", 12, "bold"),
                text_color=TEXT_MUTED,
            ).grid(row=0, column=column, sticky="w", padx=5, pady=4)

        row = 1
        for delivery in credit_note.deliveries:
            base_amount = (
                delivery.gross_quantity_kg
                * delivery.base_price_per_tonne
                / Decimal("1000")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self._render_delivery_values(
                (
                    delivery.delivery_date.strftime("%d.%m.%Y"),
                    delivery.ticket_number,
                    delivery.grain_name,
                    "Ursprungsmenge / Basispreis "
                    f"{format_de(delivery.base_price_per_tonne)} EUR/t",
                    self._quantity(delivery.gross_quantity_kg),
                    "",
                    "",
                    format_de(base_amount),
                ),
                row=row,
                font=("Segoe UI", 12, "bold"),
                text_color=TEXT,
            )
            row += 1
            for detail in delivery.details:
                label = f"↳ {detail.label}: {format_de(detail.analysis_value)}"
                if detail.price_change_per_tonne is not None:
                    label += (
                        " · "
                        f"{self._signed_money(detail.price_change_per_tonne)} EUR/t"
                    )
                self._render_delivery_values(
                    (
                        "",
                        "",
                        "",
                        label,
                        "",
                        (
                            self._quantity(detail.quantity_change_kg)
                            if detail.quantity_change_kg is not None
                            else ""
                        ),
                        (
                            self._signed_money(detail.amount_change)
                            if detail.amount_change is not None
                            else ""
                        ),
                        "",
                    ),
                    row=row,
                    font=FONT_SMALL,
                    text_color=TEXT_MUTED,
                    detail=True,
                )
                row += 1
            self._render_delivery_values(
                (
                    "",
                    "",
                    "",
                    "= Abrechnungsmenge / Abrechnungspreis "
                    f"{format_de(delivery.settlement_price_per_tonne)} EUR/t",
                    self._quantity(delivery.settlement_quantity_kg),
                    "",
                    "",
                    format_de(delivery.net_amount),
                ),
                row=row,
                font=("Segoe UI", 12, "bold"),
                text_color=TEXT,
                detail=True,
            )
            row += 2

    def _show_credit_note_totals(self, credit_note):
        gross = sum(
            (delivery.gross_quantity_kg for delivery in credit_note.deliveries),
            Decimal("0"),
        )
        settlement = sum(
            (
                delivery.settlement_quantity_kg
                for delivery in credit_note.deliveries
            ),
            Decimal("0"),
        )
        base_amount = sum(
            (
                delivery.gross_quantity_kg
                * delivery.base_price_per_tonne
                / Decimal("1000")
                for delivery in credit_note.deliveries
            ),
            Decimal("0"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.total_rows["gross"].configure(text=f"{self._quantity(gross)} kg")
        self.total_rows["deduction"].configure(
            text=f"{self._quantity(gross - settlement)} kg"
        )
        self.total_rows["settlement"].configure(
            text=f"{self._quantity(settlement)} kg"
        )
        self.total_rows["base_amount"].configure(
            text=f"{format_de(base_amount)} EUR"
        )
        self.total_rows["money_deduction"].configure(
            text=f"{format_de(base_amount - credit_note.net_amount)} EUR"
        )
        self.total_rows["net_amount"].configure(
            text=f"{format_de(credit_note.net_amount)} EUR"
        )
        self.total_rows["tax_amount"].configure(
            text=f"{format_de(credit_note.vat_amount)} EUR"
        )
        self.total_rows["payable_amount"].configure(
            text=f"{format_de(credit_note.credit_amount)} EUR"
        )

    def open_supplier_list(self):
        BusinessPartnerListDialog(
            self,
            self.controller,
            required_role=BusinessPartnerRole.SUPPLIER,
            on_selected=lambda profile: self._select_supplier(
                profile.seller,
                profile.payment,
            ),
        ).open()

    def _select_supplier(self, seller, payment):
        self.document.seller = deepcopy(seller)
        self.document.payment = deepcopy(payment)
        self.document.buyer.leitweg_id = (
            seller.buyer_reference or seller.supplier_number
        )
        self._render_top_cards()
        self.calculate()

    def _on_document_field_change(self, _model, _field, _value):
        self._refresh_create_button()

    def reload_own_company(self):
        self.document.buyer = self.controller.load_own_company_buyer()
        self.document.buyer.use_invoice_address_as_delivery = True
        self._render_top_cards()

    def add_delivery(self):
        delivery_id = f"delivery-{self._next_delivery_number}"
        self._next_delivery_number += 1
        DeliveryDialog(
            self,
            delivery_id=delivery_id,
            features=self.features,
            on_save=self._append_delivery,
            default_grain_type_code=self._default_grain_type_code(),
        )

    def _append_delivery(self, value: DeliveryFormValue):
        previous_result = self._last_result
        self.deliveries.append(value)
        if self.calculate():
            return True
        self.deliveries.pop()
        self._restore_calculation(previous_result)
        return False

    def edit_delivery(self, index: int):
        current = self.deliveries[index]
        DeliveryDialog(
            self,
            delivery_id=current.id,
            features=self.features,
            value=current,
            on_save=lambda value: self._replace_delivery(index, value),
        )

    def _replace_delivery(self, index: int, value: DeliveryFormValue):
        previous = self.deliveries[index]
        previous_result = self._last_result
        self.deliveries[index] = value
        if self.calculate():
            return True
        self.deliveries[index] = previous
        self._restore_calculation(previous_result)
        return False

    def remove_delivery(self, index: int):
        del self.deliveries[index]
        if self.deliveries:
            self.calculate()
        else:
            self._last_result = None
            self._render_deliveries()
            self._clear_totals()
            self.status_label.configure(text="")
            self._refresh_create_button()

    def edit_rules(self):
        RuleEditorDialog(
            self,
            grain_type_code=self._default_grain_type_code(),
            harvest_year=self.harvest_year,
            rule_sets=self.rule_sets,
            on_save=self._replace_rule_sets,
        )

    def _replace_rule_sets(
        self,
        rule_sets: dict[
            str,
            tuple[tuple[FeatureFormValue, ...], tuple[RuleFormValue, ...]],
        ],
        activated_grain_type: str | None,
    ) -> bool:
        current_grain_type = self._default_grain_type_code()
        if self.deliveries and current_grain_type in rule_sets:
            missing = missing_required_analyses(
                self.deliveries,
                rule_sets[current_grain_type][0],
            )
            if missing:
                details = "\n".join(
                    f"• Wiegeschein {ticket or 'ohne Nummer'}: {', '.join(labels)}"
                    for ticket, labels in missing
                )
                messagebox.showerror(
                    "Analysewerte fehlen",
                    "Durch die aktiven Regeln sind zusätzliche Analysewerte "
                    "erforderlich:\n\n"
                    + details
                    + "\n\nBitte ergänze die Werte in den betroffenen Lieferungen.",
                    parent=self,
                )
                return False
        payloads = {
            grain_type_code: serialize_rule_set(
                f"{GRAIN_TYPE_LABELS[grain_type_code]} Standard",
                features,
                rules,
            )
            for grain_type_code, (features, rules) in rule_sets.items()
        }
        try:
            self.controller.save_grain_scheme_drafts(
                self.harvest_year,
                payloads,
            )
            activated_version = None
            if activated_grain_type:
                activated_version = self.controller.activate_grain_scheme(
                    activated_grain_type,
                    self.harvest_year,
                    payloads[activated_grain_type],
                )
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showerror("Abrechnungsregeln", str(exc), parent=self)
            return False
        self.rule_sets = dict(rule_sets)
        self.features, self.rules = self._current_rule_set()
        active_rules = sum(rule.enabled for rule in self.rules)
        self.rule_button.configure(
            text=f"Regeln bearbeiten ({active_rules} aktiv)"
        )
        if not self.calculate():
            return False
        if activated_version is not None:
            messagebox.showinfo(
                "Regelwerk aktiviert",
                f"Version {activated_version.display_version} wurde angelegt.",
                parent=self,
            )
        return True

    def calculate(self, *, show_error: bool = True) -> bool:
        try:
            result = calculate_settlement_preview(self._form_value())
        except (GrainValidationError, ValueError, ArithmeticError) as exc:
            self._last_result = None
            self._render_deliveries()
            self._clear_totals()
            self.status_label.configure(text="Eingaben prüfen")
            if show_error:
                messagebox.showerror("Getreideabrechnung", str(exc), parent=self)
            self._refresh_create_button()
            return False
        self._last_result = result
        self._render_deliveries(result)
        self._show_totals(result)
        self.status_label.configure(
            text=f"{len(result.delivery_results)} Lieferungen berechnet"
        )
        self._refresh_create_button()
        return True

    def _restore_calculation(
        self,
        result: SettlementBatchResult | None,
    ) -> None:
        self._last_result = result
        self._render_deliveries(result)
        if result is None:
            self._clear_totals()
            self.status_label.configure(text="")
            self._refresh_create_button()
            return
        self._show_totals(result)
        self.status_label.configure(
            text=f"{len(result.delivery_results)} Lieferungen berechnet"
        )
        self._refresh_create_button()

    def _form_value(self) -> GrainSettlementForm:
        features, rules = self._current_rule_set()
        self.features, self.rules = features, rules
        return GrainSettlementForm(
            supplier_number=self.document.seller.supplier_number,
            features=features,
            rules=rules,
            deliveries=tuple(self.deliveries),
            vat_rate=self.vat_variable.get(),
        )

    def _render_deliveries(self, batch: SettlementBatchResult | None = None):
        clear_frame(self.delivery_host)
        headers = (
            "Datum",
            "Wiegeschein",
            "Getreideart",
            "Analyse / Abrechnungsposition",
            "Menge kg",
            "Δ Menge kg",
            "Δ Wert EUR",
            "Betrag EUR",
            "",
        )
        for column, title in enumerate(headers):
            self.delivery_host.grid_columnconfigure(
                column,
                weight=1 if column == 3 else 0,
            )
            ctk.CTkLabel(
                self.delivery_host,
                text=title,
                font=("Segoe UI", 12, "bold"),
                text_color=TEXT_MUTED,
            ).grid(row=0, column=column, sticky="w", padx=5, pady=4)

        results = {
            result.delivery_id: result
            for result in (batch.delivery_results if batch else ())
        }
        grid_row = 1
        for index, delivery in enumerate(self.deliveries):
            result = results.get(delivery.id)
            values = (
                delivery.delivery_date,
                delivery.ticket_number,
                self._grain_table_label(delivery.grain_type_code),
                self._analysis_summary(delivery),
                (
                    self._quantity(result.gross_quantity_kg)
                    if result
                    else delivery.gross_quantity_kg
                ),
                "",
                "",
                format_de(self._gross_base_amount(result)) if result else "–",
            )
            self._render_delivery_values(
                values,
                row=grid_row,
                font=("Segoe UI", 12, "bold"),
                text_color=TEXT,
            )
            action_frame = ctk.CTkFrame(self.delivery_host, fg_color="transparent")
            action_frame.grid(row=grid_row, column=8, padx=5, pady=4)
            small_button(
                action_frame,
                "✎",
                lambda i=index: self.edit_delivery(i),
            ).pack(side="left")
            small_button(
                action_frame,
                "−",
                lambda i=index: self.remove_delivery(i),
            ).pack(side="left", padx=(4, 0))
            grid_row += 1

            if result:
                for detail_values in self._adjustment_rows(result):
                    self._render_delivery_values(
                        detail_values,
                        row=grid_row,
                        font=FONT_SMALL,
                        text_color=TEXT_MUTED,
                        detail=True,
                    )
                    grid_row += 1

                residual_values = self._residual_row(result)
                self._render_delivery_values(
                    residual_values,
                    row=grid_row,
                    font=("Segoe UI", 12, "bold"),
                    text_color=TEXT,
                    detail=True,
                    pady=(4, 2),
                )
                grid_row += 1

            spacer = ctk.CTkFrame(
                self.delivery_host,
                height=5,
                fg_color="transparent",
            )
            spacer.grid(row=grid_row, column=0, columnspan=len(headers), sticky="ew")
            grid_row += 1

        if not self.deliveries:
            ctk.CTkLabel(
                self.delivery_host,
                text="Noch keine Lieferung erfasst.",
                font=FONT_NORMAL,
                text_color=TEXT_MUTED,
            ).grid(row=1, column=0, columnspan=len(headers), pady=18)

    def _render_delivery_values(
        self,
        values,
        *,
        row,
        font,
        text_color,
        detail=False,
        pady=2,
    ):
        for column, value in enumerate(values):
            if not value:
                continue
            is_detail_label = detail and column == 3
            ctk.CTkLabel(
                self.delivery_host,
                text=value,
                font=font,
                text_color=text_color,
                anchor="w",
                justify="left",
                wraplength=300 if is_detail_label else (220 if column == 3 else 0),
            ).grid(
                row=row,
                column=1 if is_detail_label else column,
                columnspan=3 if is_detail_label else 1,
                sticky="w",
                padx=5,
                pady=pady,
            )

    def _adjustment_rows(self, result: SettlementResult):
        rows = []
        running_amount = self._gross_base_amount(result)
        for deduction in result.quantity_deductions:
            if deduction.deducted_quantity_kg == 0:
                continue
            remaining_amount = (
                deduction.remaining_quantity_kg
                / Decimal("1000")
                * result.base_price_per_tonne
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            amount_delta = remaining_amount - running_amount
            label = f"↳ Mengenabzug · {deduction.label}"
            label += self._measurement_context(
                deduction.measurement_code,
                deduction.measurement_value,
            )
            rows.append(
                (
                    "",
                    "",
                    "",
                    label,
                    self._quantity(deduction.remaining_quantity_kg),
                    f"−{self._quantity(deduction.deducted_quantity_kg)}",
                    self._signed_money(amount_delta),
                    format_de(remaining_amount),
                )
            )
            running_amount = remaining_amount

        for adjustment in result.monetary_adjustments:
            if adjustment.amount_delta == 0:
                continue
            is_surcharge = adjustment.amount_delta > 0
            if adjustment.phase.value == "price_adjustment":
                effect = "Preiszuschlag" if is_surcharge else "Preisabzug"
            else:
                effect = "Kostenzuschlag" if is_surcharge else "Kostenabzug"
            label = f"↳ {effect} · {adjustment.label}"
            label += self._measurement_context(
                adjustment.measurement_code,
                adjustment.measurement_value,
            )
            if adjustment.price_delta_per_tonne is not None:
                label += (
                    " · "
                    + self._signed_money(adjustment.price_delta_per_tonne)
                    + " EUR/t"
                )
            rows.append(
                (
                    "",
                    "",
                    "",
                    label,
                    "",
                    "",
                    self._signed_money(adjustment.amount_delta),
                    format_de(adjustment.resulting_amount),
                )
            )
        return tuple(rows)

    @staticmethod
    def _gross_base_amount(result: SettlementResult) -> Decimal:
        return (
            result.gross_quantity_kg
            / Decimal("1000")
            * result.base_price_per_tonne
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _residual_row(result: SettlementResult):
        return (
            "",
            "",
            "",
            "= Verbleibender Abrechnungsbetrag",
            GrainSettlementView._quantity(result.settlement_quantity_kg),
            "",
            "",
            format_de(result.net_amount),
        )

    def _measurement_context(self, feature_code, value) -> str:
        if not feature_code or value is None:
            return ""
        features = {feature.code: feature for feature in self.features}
        feature = features.get(feature_code)
        label = feature.label if feature else feature_code
        unit = f" {feature.unit}" if feature and feature.unit else ""
        return f" · {label}: {format_de(value)}{unit}"

    @staticmethod
    def _signed_money(value: Decimal) -> str:
        formatted = format_de(value)
        return f"+{formatted}" if value > 0 else formatted

    def _analysis_summary(self, delivery: DeliveryFormValue) -> str:
        labels = {feature.code: feature.label for feature in self.features}
        values = []
        for analysis in delivery.analyses:
            raw = str(analysis.raw_value or "").strip()
            if not raw:
                continue
            effective = str(analysis.corrected_value or "").strip() or raw
            label = labels.get(analysis.feature_code, analysis.feature_code)
            values.append(f"{label}: {effective}")
        return " · ".join(values) or "–"

    @staticmethod
    def _grain_table_label(grain_type_code: str) -> str:
        if grain_type_code == "barley":
            return "Futtergerste"
        return GRAIN_TYPE_LABELS.get(grain_type_code, grain_type_code)

    def _default_grain_type_code(self) -> str:
        return self.deliveries[0].grain_type_code if self.deliveries else "wheat"

    def _current_rule_set(self):
        grain_type_code = self._default_grain_type_code()
        if grain_type_code not in self.rule_sets:
            preset = grain_rule_preset(grain_type_code)
            self.rule_sets[grain_type_code] = (preset.features, preset.rules)
        return self.rule_sets[grain_type_code]

    def _example_analyses(self, **overrides: str) -> tuple[AnalysisFormValue, ...]:
        """Erzeugt vollständige Beispieldaten für das aktuell aktive Regelwerk."""

        return tuple(
            AnalysisFormValue(
                feature.code,
                overrides.get(
                    feature.code,
                    _EXAMPLE_ANALYSIS_VALUES.get(feature.code, "0"),
                ),
            )
            for feature in self.features
            if feature.required or feature.code in overrides
        )

    def _show_totals(self, result: SettlementBatchResult):
        self.total_rows["gross"].configure(
            text=f"{self._quantity(result.gross_quantity_kg)} kg"
        )
        self.total_rows["deduction"].configure(
            text=f"{self._quantity(result.deducted_quantity_kg)} kg"
        )
        self.total_rows["settlement"].configure(
            text=f"{self._quantity(result.settlement_quantity_kg)} kg"
        )
        self.total_rows["base_amount"].configure(
            text=f"{format_de(result.base_amount)} EUR"
        )
        self.total_rows["money_deduction"].configure(
            text=f"{format_de(result.deducted_amount)} EUR"
        )
        self.total_rows["net_amount"].configure(
            text=f"{format_de(result.net_amount)} EUR"
        )
        self._refresh_tax_totals()

    def _refresh_tax_totals(self):
        if self._last_result is None:
            self._refresh_create_button()
            return
        try:
            vat_rate = parse_vat_rate(self.vat_variable.get())
        except GrainValidationError:
            self.total_rows["tax_amount"].configure(text="—")
            self.total_rows["payable_amount"].configure(text="—")
            self._refresh_create_button()
            return
        tax_amount = (
            self._last_result.net_amount * vat_rate / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        payable_amount = self._last_result.net_amount + tax_amount
        self.total_rows["tax_amount"].configure(
            text=f"{format_de(tax_amount)} EUR"
        )
        self.total_rows["payable_amount"].configure(
            text=f"{format_de(payable_amount)} EUR"
        )
        self._refresh_create_button()

    def _creation_issues(self):
        if self.credit_note is not None:
            return (
                "Die Getreidegutschrift wurde bereits erstellt. "
                "Änderungen sind über 'Getreidegutschrift bearbeiten' möglich.",
            )
        return grain_credit_note_creation_issues(
            self.document,
            self.deliveries,
            self._last_result,
            self.vat_variable.get(),
        )

    def _credit_note_creation_hint(self):
        issues = self._creation_issues()
        if not issues:
            return ""
        return "Zum Erstellen fehlt noch:\n- " + "\n- ".join(issues)

    def _refresh_create_button(self):
        if not hasattr(self, "create_button"):
            return
        set_button_enabled(
            self.create_button,
            not self._creation_issues(),
            primary=True,
        )

    def _clear_totals(self):
        for value in self.total_rows.values():
            value.configure(text="–")

    @staticmethod
    def _deduction(result: SettlementResult) -> Decimal:
        return result.gross_quantity_kg - result.settlement_quantity_kg

    @staticmethod
    def _quantity(value: Decimal) -> str:
        return f"{value:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def reset_example(self):
        self.credit_note = None
        self._set_credit_note_mode(False)
        self.document = self.controller.create_empty_invoice(
            DocumentType.SELF_BILLED_INVOICE
        )
        self.document.info.invoice_number = "80001"
        self.document.info.delivery_date = date.today().strftime("%d.%m.%Y")
        self.document.seller.supplier_number = "1001"
        self.document.seller.name = "Musterhof Testlieferant"
        self.document.seller.street = "Feldweg 12"
        self.document.seller.postcode = "54321"
        self.document.seller.city = "Musterdorf"
        self.document.seller.country = "DE"
        self.document.seller.phone = "+49 9876 543210"
        self.document.seller.email = "musterlieferant@example.de"
        self.document.seller.vat = "DE987654321"
        self.document.seller.tax_number = "12/345/67890"
        self.document.seller.registry_number = "HRA 12345"
        self.document.seller.contact_name = "Erika Muster"
        self.document.seller.buyer_reference = "1001"
        self.document.payment.iban = "DE89370400440532013000"
        self.document.payment.bic = "TESTDEFFXXX"
        self.document.payment.account_holder = "Musterhof Testlieferant"
        self.document.payment.payment_means_code = "58"
        self.document.payment.payment_terms = "Auszahlung innerhalb von 14 Tagen."
        self.rule_sets = {}
        for grain_type_code in GRAIN_TYPE_LABELS:
            grain_preset = grain_rule_preset(grain_type_code)
            self.rule_sets[grain_type_code] = (
                grain_preset.features,
                grain_preset.rules,
            )
        invalid_drafts = []
        for draft in self.controller.load_grain_scheme_drafts(self.harvest_year):
            if draft.grain_type_code not in self.rule_sets:
                continue
            try:
                features, rules = deserialize_rule_set(
                    dict(draft.payload)
                )
                self.rule_sets[draft.grain_type_code] = (
                    require_features_used_by_active_rules(features, rules),
                    rules,
                )
            except GrainValidationError:
                invalid_drafts.append(draft.name)
        if invalid_drafts:
            messagebox.showwarning(
                "Abrechnungsregeln",
                "Beschädigte Regelentwürfe wurden nicht geladen: "
                + ", ".join(invalid_drafts),
                parent=self,
            )
        preset = grain_rule_preset("wheat")
        self.features, self.rules = self.rule_sets.get(
            "wheat",
            (preset.features, preset.rules),
        )
        today = date.today().strftime("%d.%m.%Y")
        self.deliveries = [
            DeliveryFormValue(
                id="delivery-1",
                delivery_date=today,
                ticket_number="WS-4711",
                grain_type_code="wheat",
                gross_quantity_kg="10.000",
                base_price_per_tonne="200,00",
                analyses=self._example_analyses(
                    moisture="16,0",
                    dockage="3,0",
                ),
            ),
            DeliveryFormValue(
                id="delivery-2",
                delivery_date=today,
                ticket_number="WS-4712",
                grain_type_code="wheat",
                gross_quantity_kg="8.000",
                base_price_per_tonne="200,00",
                analyses=self._example_analyses(
                    moisture="14,5",
                    dockage="2,0",
                ),
            ),
        ]
        self._next_delivery_number = 3
        self._render_top_cards()
        active_rules = sum(rule.enabled for rule in self.rules)
        self.rule_button.configure(
            text=f"Regeln bearbeiten ({active_rules} aktiv)"
        )
        self.calculate(show_error=False)
