"""Mehrlieferungs-Vorschau im Layout der Rechnungs- und Gutschriftmaske."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
from tkinter import messagebox

import customtkinter as ctk

from rechnungshelfer.domain.grain_models import (
    GrainValidationError,
    SettlementBatchResult,
    SettlementResult,
)
from rechnungshelfer.domain.models import DocumentType
from rechnungshelfer.services.format_service import format_de

from .components import button, card, clear_frame, set_button_enabled, small_button
from .grain_form_mapper import (
    AnalysisFormValue,
    DeliveryFormValue,
    FeatureFormValue,
    GrainSettlementForm,
    RuleFormValue,
    calculate_settlement_preview,
)
from .grain_settlement_dialogs import (
    GRAIN_TYPE_LABELS,
    DeliveryDialog,
    RuleEditorDialog,
)
from .party_card import PartyCard
from .styles import APP_BG, FONT_NORMAL, FONT_SECTION, FONT_SMALL, TEXT, TEXT_MUTED
from .supplier_edit_dialog import SupplierEditDialog
from .supplier_load_dialog import SupplierLoadDialog


class GrainSettlementView(ctk.CTkFrame):
    """Ordnet Kopfdaten, Lieferungen und Summen wie die Belegmasken an."""

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=APP_BG, corner_radius=0)
        self.controller = controller
        self.document = controller.create_empty_invoice(
            DocumentType.SELF_BILLED_INVOICE
        )
        self.features: tuple[FeatureFormValue, ...] = ()
        self.rules: tuple[RuleFormValue, ...] = ()
        self.deliveries: list[DeliveryFormValue] = []
        self.field_entries = {}
        self._next_delivery_number = 1
        self._last_result: SettlementBatchResult | None = None

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
        ).render()
        info_card.pack(fill="both", expand=True)

    def _build_delivery_card(self):
        delivery_card = card(self.delivery_area, "Lieferungen / Wiegescheine")
        delivery_card.grid(row=0, column=0, sticky="nsew")
        delivery_card.grid_columnconfigure(0, weight=1)
        delivery_card.grid_rowconfigure(2, weight=1)

        actions = ctk.CTkFrame(delivery_card, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        button(actions, "+ Lieferung", self.add_delivery, primary=True).pack(
            side="left"
        )
        button(actions, "Neu berechnen", self.calculate).pack(side="left", padx=8)
        self.rule_button = button(actions, "Regeln bearbeiten", self.edit_rules)
        self.rule_button.pack(side="left")
        button(actions, "Beispiel zurücksetzen", self.reset_example).pack(
            side="left",
            padx=8,
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
            ("net_amount", "Auszahlungsbetrag"),
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
            text=(
                "Beim Preis-/Kostenabzug bedeutet ein negativer Wert "
                "einen Zuschlag."
            ),
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
            wraplength=270,
            justify="left",
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=14, pady=12)

        output_buttons = (
            ("Getreideabrechnung speichern", 8),
            ("PDF erstellen", 9),
            ("HTML erstellen", 10),
        )
        for label, row in output_buttons:
            output_button = button(totals, label, lambda: None)
            output_button.grid(
                row=row,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=14,
                pady=(0, 8 if row < 10 else 14),
            )
            set_button_enabled(output_button, False)

    def open_supplier_list(self):
        SupplierLoadDialog(
            self,
            self.controller,
            on_supplier_selected=self._select_supplier,
            on_create_supplier=self.open_supplier_editor,
        ).open()

    def open_supplier_editor(self):
        SupplierEditDialog(
            self,
            self.controller,
            on_saved=self._select_supplier,
        ).open()

    def _select_supplier(self, seller, payment):
        self.document.seller = deepcopy(seller)
        self.document.payment = deepcopy(payment)
        self._render_top_cards()
        self.calculate()

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
        self.deliveries.append(value)
        if self.calculate():
            return True
        self.deliveries.pop()
        self._render_deliveries(self._last_result)
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
        self.deliveries[index] = value
        if self.calculate():
            return True
        self.deliveries[index] = previous
        self._render_deliveries(self._last_result)
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

    def edit_rules(self):
        RuleEditorDialog(
            self,
            grain_type_code=self._default_grain_type_code(),
            features=self.features,
            rules=self.rules,
            on_save=self._replace_rules,
        )

    def _replace_rules(
        self,
        features: tuple[FeatureFormValue, ...],
        rules: tuple[RuleFormValue, ...],
    ):
        self.features = features
        self.rules = rules
        self.rule_button.configure(text=f"Regeln bearbeiten ({len(rules)})")
        self.calculate()

    def calculate(self) -> bool:
        try:
            result = calculate_settlement_preview(self._form_value())
        except (GrainValidationError, ValueError, ArithmeticError) as exc:
            self._render_deliveries(self._last_result)
            self.status_label.configure(text="Eingaben prüfen")
            messagebox.showerror("Getreideabrechnung", str(exc), parent=self)
            return False
        self._last_result = result
        self._render_deliveries(result)
        self._show_totals(result)
        self.status_label.configure(
            text=f"{len(result.delivery_results)} Lieferungen berechnet"
        )
        return True

    def _form_value(self) -> GrainSettlementForm:
        return GrainSettlementForm(
            supplier_number=self.document.seller.supplier_number,
            features=self.features,
            rules=self.rules,
            deliveries=tuple(self.deliveries),
        )

    def _render_deliveries(self, batch: SettlementBatchResult | None = None):
        clear_frame(self.delivery_host)
        headers = (
            "Datum",
            "Wiegeschein",
            "Getreideart",
            "Brutto kg",
            "Analysewerte",
            "Abzug kg",
            "Abrechnungsmenge kg",
            "Basiswarenwert EUR",
            "Preis-/Kostenabzug EUR",
            "Endbetrag EUR",
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
        for row_number, delivery in enumerate(self.deliveries, start=1):
            result = results.get(delivery.id)
            values = (
                delivery.delivery_date,
                delivery.ticket_number,
                GRAIN_TYPE_LABELS.get(
                    delivery.grain_type_code,
                    delivery.grain_type_code,
                ),
                (
                    self._quantity(result.gross_quantity_kg)
                    if result
                    else delivery.gross_quantity_kg
                ),
                self._analysis_summary(delivery),
                self._quantity(self._deduction(result)) if result else "–",
                self._quantity(result.settlement_quantity_kg) if result else "–",
                format_de(result.base_amount) if result else "–",
                (
                    format_de(result.base_amount - result.net_amount)
                    if result
                    else "–"
                ),
                format_de(result.net_amount) if result else "–",
            )
            for column, value in enumerate(values):
                ctk.CTkLabel(
                    self.delivery_host,
                    text=value,
                    font=FONT_SMALL,
                    text_color=TEXT,
                    anchor="w",
                ).grid(row=row_number, column=column, sticky="w", padx=5, pady=4)
            action_frame = ctk.CTkFrame(self.delivery_host, fg_color="transparent")
            action_frame.grid(row=row_number, column=10, padx=5, pady=4)
            index = row_number - 1
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

        if not self.deliveries:
            ctk.CTkLabel(
                self.delivery_host,
                text="Noch keine Lieferung erfasst.",
                font=FONT_NORMAL,
                text_color=TEXT_MUTED,
            ).grid(row=1, column=0, columnspan=len(headers), pady=18)

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

    def _default_grain_type_code(self) -> str:
        return self.deliveries[0].grain_type_code if self.deliveries else "wheat"

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
        self.document = self.controller.create_empty_invoice(
            DocumentType.SELF_BILLED_INVOICE
        )
        self.document.info.invoice_number = "GS-ENTWURF-001"
        self.document.info.delivery_date = date.today().strftime("%d.%m.%Y")
        self.document.seller.supplier_number = "L0001"
        self.document.seller.name = "Beispiellieferant"
        self.features = (FeatureFormValue("dockage", "Besatz"),)
        self.rules = (
            RuleFormValue(
                code="dockage-deduction",
                label="Besatzabzug",
                kind="percentage_of_measurement",
                feature_code="dockage",
                quantity_reference="gross_quantity",
                parameters="factor=1,1",
            ),
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
                analyses=(AnalysisFormValue("dockage", "3,0"),),
            ),
            DeliveryFormValue(
                id="delivery-2",
                delivery_date=today,
                ticket_number="WS-4712",
                grain_type_code="wheat",
                gross_quantity_kg="8.000",
                base_price_per_tonne="200,00",
                analyses=(AnalysisFormValue("dockage", "2,0"),),
            ),
        ]
        self._next_delivery_number = 3
        self._render_top_cards()
        self.rule_button.configure(text="Regeln bearbeiten (1)")
        self.calculate()
