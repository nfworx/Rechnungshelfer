"""Gemeinsame Liste und Bearbeitung fuer Geschaeftspartner und ihre Rollen."""

from __future__ import annotations

from copy import deepcopy
from tkinter import messagebox

import customtkinter as ctk

from rechnungshelfer.domain.business_partner import (
    BusinessPartnerProfile,
    BusinessPartnerRole,
    COMMON_PARTY_FIELDS,
)
from rechnungshelfer.domain.models import Buyer, Payment, Seller

from .components import button, card
from .party_card import PartyCard
from .styles import (
    APP_BG,
    BORDER,
    FONT_NORMAL,
    FONT_SECTION,
    FONT_SMALL,
    PRIMARY,
    TEXT,
    TEXT_MUTED,
)


ROLE_FILTERS = {
    "Alle": None,
    "Kunden": BusinessPartnerRole.CUSTOMER,
    "Lieferanten": BusinessPartnerRole.SUPPLIER,
    "Beide Rollen": "both",
}


def new_business_partner_profile(
    default_role: BusinessPartnerRole | None = None,
) -> BusinessPartnerProfile:
    buyer = Buyer()
    seller = Seller(
        name="",
        street="",
        postcode="",
        city="",
        country="DE",
        phone="",
        email="",
        vat="",
        tax_number="",
        registry_number="",
        contact_name="",
        supplier_number="",
        buyer_reference="",
    )
    payment = Payment(
        iban="",
        bic="",
        account_holder="",
        payment_means_code="58",
        payment_terms="",
    )
    roles = frozenset({default_role}) if default_role else frozenset()
    return BusinessPartnerProfile(buyer, seller, payment, roles)


class BusinessPartnerEditDialog:
    def __init__(
        self,
        parent,
        controller,
        *,
        profile: BusinessPartnerProfile | None = None,
        default_role: BusinessPartnerRole | None = None,
        on_saved=None,
    ):
        self.parent = parent
        self.controller = controller
        self.profile = deepcopy(profile) if profile else new_business_partner_profile(
            default_role
        )
        self.is_new = profile is None
        self.on_saved = on_saved
        self.window = None
        self.customer_role = None
        self.supplier_role = None
        self.field_entries = {}

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title(
            "Geschäftspartner anlegen"
            if self.is_new
            else "Geschäftspartner bearbeiten"
        )
        self.window.geometry("1120x780")
        self.window.minsize(960, 650)
        self.window.grab_set()
        self.window.configure(fg_color=APP_BG)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(1, weight=1)

        self._render_roles()
        self._render_content()
        self._render_actions()

    def _render_roles(self):
        roles = card(self.window, "Rollen")
        roles.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        roles.grid_columnconfigure(2, weight=1)

        self.customer_role = ctk.BooleanVar(
            value=self.profile.has_role(BusinessPartnerRole.CUSTOMER)
        )
        self.supplier_role = ctk.BooleanVar(
            value=self.profile.has_role(BusinessPartnerRole.SUPPLIER)
        )
        ctk.CTkCheckBox(
            roles,
            text="Kunde",
            variable=self.customer_role,
            font=FONT_NORMAL,
        ).grid(row=1, column=0, sticky="w", padx=(14, 24), pady=(4, 12))
        ctk.CTkCheckBox(
            roles,
            text="Lieferant",
            variable=self.supplier_role,
            font=FONT_NORMAL,
        ).grid(row=1, column=1, sticky="w", padx=(0, 24), pady=(4, 12))
        ctk.CTkLabel(
            roles,
            text=(
                "Ein Geschäftspartner kann gleichzeitig Kunde und Lieferant sein."
            ),
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
        ).grid(row=1, column=2, sticky="w", pady=(4, 12))

    def _render_content(self):
        content = ctk.CTkScrollableFrame(self.window, fg_color=APP_BG)
        content.grid(row=1, column=0, sticky="nsew", padx=18, pady=8)
        content.grid_columnconfigure((0, 1), weight=1, uniform="partner_cards")

        common_card = PartyCard(
            content,
            "Gemeinsame Stammdaten",
            self.profile.buyer,
            field_entries=self.field_entries,
            exclude_fields=["leitweg_id", "use_invoice_address_as_delivery"],
            label_overrides={"customer_number": "Geschäftspartnernummer"},
        ).render()
        common_card.grid(row=0, column=0, sticky="new", padx=(0, 8), pady=(0, 12))

        payment_card = PartyCard(
            content,
            "Bankdaten / Auszahlung (Lieferantenrolle)",
            self.profile.payment,
            field_entries=self.field_entries,
        ).render()
        payment_card.grid(row=0, column=1, sticky="new", padx=(8, 0), pady=(0, 12))

        customer_card = card(content, "Kundenrolle")
        customer_card.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 12))
        customer_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            customer_card,
            text="Käuferreferenz / Leitweg-ID (BT-10)",
            font=FONT_SMALL,
            text_color=TEXT,
        ).grid(row=1, column=0, sticky="w", padx=(14, 8), pady=(4, 12))
        reference_entry = ctk.CTkEntry(customer_card, height=28)
        reference_entry.insert(0, self.profile.buyer.leitweg_id)
        reference_entry.grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(4, 12))
        reference_entry.bind(
            "<KeyRelease>",
            lambda event: setattr(
                self.profile.buyer,
                "leitweg_id",
                reference_entry.get(),
            ),
        )

        supplier_card = card(content, "Lieferantenrolle")
        supplier_card.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 12))
        supplier_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            supplier_card,
            text="Käuferreferenz für Gutschriften (BT-10)",
            font=FONT_SMALL,
            text_color=TEXT,
        ).grid(row=1, column=0, sticky="w", padx=(14, 8), pady=(4, 12))
        buyer_reference_entry = ctk.CTkEntry(supplier_card, height=28)
        buyer_reference_entry.insert(0, self.profile.seller.buyer_reference)
        buyer_reference_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 14),
            pady=(4, 12),
        )
        buyer_reference_entry.bind(
            "<KeyRelease>",
            lambda event: setattr(
                self.profile.seller,
                "buyer_reference",
                buyer_reference_entry.get(),
            ),
        )

    def _render_actions(self):
        actions = ctk.CTkFrame(self.window, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="e", padx=18, pady=(8, 18))
        button(actions, "Speichern", self.save, primary=True).pack(
            side="left",
            padx=(0, 8),
        )
        button(actions, "Abbrechen", self.close).pack(side="left")

    def save(self):
        roles = set()
        if self.customer_role.get():
            roles.add(BusinessPartnerRole.CUSTOMER)
        if self.supplier_role.get():
            roles.add(BusinessPartnerRole.SUPPLIER)
        if not roles:
            messagebox.showerror(
                "Geschäftspartner",
                "Bitte wählen Sie mindestens eine Rolle aus.",
                parent=self.window,
            )
            return

        for field in COMMON_PARTY_FIELDS:
            setattr(
                self.profile.seller,
                field,
                getattr(self.profile.buyer, field),
            )
        number = self.profile.buyer.customer_number
        self.profile.seller.supplier_number = number
        if (
            BusinessPartnerRole.SUPPLIER in roles
            and not str(self.profile.seller.buyer_reference or "").strip()
        ):
            self.profile.seller.buyer_reference = number
        self.profile.roles = frozenset(roles)

        try:
            self.controller.save_business_partner(self.profile)
        except Exception as exc:
            messagebox.showerror("Geschäftspartner", str(exc), parent=self.window)
            return

        if self.on_saved:
            self.on_saved(deepcopy(self.profile))
        self.close()

    def close(self):
        if self.window:
            self.window.destroy()
            self.window = None


class BusinessPartnerListDialog:
    def __init__(
        self,
        parent,
        controller,
        *,
        required_role: BusinessPartnerRole | None = None,
        on_selected=None,
    ):
        self.parent = parent
        self.controller = controller
        self.required_role = required_role
        self.on_selected = on_selected
        self.window = None
        self.search_entry = None
        self.list_frame = None
        self.filter_variable = None
        self.selected_profile = None
        self.selected_row = None
        self._render_job = None

    def open(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Geschäftspartner")
        self.window.geometry("980x680")
        self.window.minsize(820, 560)
        self.window.grab_set()
        self.window.configure(fg_color=APP_BG)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            self.window,
            text="Geschäftspartner",
            font=FONT_SECTION,
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

        initial_filter = {
            BusinessPartnerRole.CUSTOMER: "Kunden",
            BusinessPartnerRole.SUPPLIER: "Lieferanten",
        }.get(self.required_role, "Alle")
        self.filter_variable = ctk.StringVar(value=initial_filter)
        ctk.CTkSegmentedButton(
            self.window,
            values=list(ROLE_FILTERS),
            variable=self.filter_variable,
            command=lambda value: self.render_list(),
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 10))

        self.search_entry = ctk.CTkEntry(
            self.window,
            placeholder_text=(
                "Suche nach Geschäftspartnernummer, Name, Ort oder Steuerdaten..."
            ),
            height=34,
        )
        self.search_entry.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.search_entry.bind("<KeyRelease>", self._schedule_render)

        self.list_frame = ctk.CTkScrollableFrame(self.window, fg_color="#f8fafc")
        self.list_frame.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 14))
        self.list_frame.grid_columnconfigure(0, weight=1)
        self._render_footer()
        self.render_list()

    def _render_footer(self):
        footer = ctk.CTkFrame(self.window, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="e", padx=18, pady=(0, 18))
        button(footer, "Neu", self.create_partner).pack(side="left", padx=(0, 8))
        button(footer, "Bearbeiten", self.edit_selected).pack(
            side="left",
            padx=(0, 8),
        )
        if self.on_selected:
            button(footer, "Übernehmen", self.load_selected, primary=True).pack(
                side="left",
                padx=(0, 8),
            )
        button(footer, "Löschen", self.delete_selected).pack(
            side="left",
            padx=(0, 8),
        )
        button(footer, "Schließen", self.close).pack(side="left")

    def _schedule_render(self, event=None):
        if self._render_job is not None:
            self.window.after_cancel(self._render_job)
        self._render_job = self.window.after(150, self._render_scheduled)

    def _render_scheduled(self):
        self._render_job = None
        self.render_list()

    def render_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.selected_profile = None
        self.selected_row = None

        query = (self.search_entry.get() if self.search_entry else "").casefold().strip()
        selected_filter = self.filter_variable.get() if self.filter_variable else "Alle"
        role_filter = ROLE_FILTERS[selected_filter]
        profiles = []
        for profile in self.controller.list_business_partners():
            if role_filter == "both" and len(profile.roles) != 2:
                continue
            if isinstance(role_filter, BusinessPartnerRole) and not profile.has_role(
                role_filter
            ):
                continue
            searchable = " ".join(
                (
                    profile.partner_number,
                    profile.name,
                    profile.buyer.city,
                    profile.buyer.email,
                    profile.buyer.tax_number,
                    profile.buyer.vat,
                )
            ).casefold()
            if query in searchable:
                profiles.append(profile)

        if not profiles:
            ctk.CTkLabel(
                self.list_frame,
                text="Keine Geschäftspartner gefunden.",
                font=FONT_NORMAL,
                text_color=TEXT_MUTED,
            ).grid(row=0, column=0, sticky="w", padx=14, pady=14)
            return
        for index, profile in enumerate(profiles):
            self._render_row(index, profile)

    def _render_row(self, index: int, profile: BusinessPartnerProfile):
        row = ctk.CTkFrame(
            self.list_frame,
            fg_color="#ffffff" if index % 2 == 0 else "#f8fafc",
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        row.grid(row=index, column=0, sticky="ew", padx=10, pady=5)
        row.grid_columnconfigure(0, weight=1)
        role_text = ", ".join(
            label
            for role, label in (
                (BusinessPartnerRole.CUSTOMER, "Kunde"),
                (BusinessPartnerRole.SUPPLIER, "Lieferant"),
            )
            if profile.has_role(role)
        )
        texts = (
            f"{profile.partner_number} | {profile.name}",
            f"{profile.buyer.street}, {profile.buyer.postcode} {profile.buyer.city}",
            f"Rollen: {role_text}    Steuernummer: {profile.buyer.tax_number or '-'}",
        )
        for line, text in enumerate(texts):
            label = ctk.CTkLabel(
                row,
                text=text,
                font=FONT_NORMAL if line == 0 else FONT_SMALL,
                text_color=TEXT if line < 2 else TEXT_MUTED,
                anchor="w",
            )
            label.grid(row=line, column=0, sticky="ew", padx=14, pady=3)
            label.bind(
                "<Button-1>",
                lambda event, value=profile, widget=row: self.select(value, widget),
            )
            label.bind(
                "<Double-Button-1>",
                lambda event, value=profile: self.activate(value),
            )
        row.bind(
            "<Button-1>",
            lambda event, value=profile, widget=row: self.select(value, widget),
        )

    def select(self, profile: BusinessPartnerProfile, row):
        if self.selected_row and self.selected_row.winfo_exists():
            self.selected_row.configure(border_color=BORDER)
        self.selected_profile = profile
        self.selected_row = row
        row.configure(border_color=PRIMARY)

    def create_partner(self):
        default_role = self.required_role or BusinessPartnerRole.CUSTOMER
        BusinessPartnerEditDialog(
            self.window,
            self.controller,
            default_role=default_role,
            on_saved=lambda profile: self.render_list(),
        ).open()

    def edit_selected(self):
        if not self.selected_profile:
            messagebox.showwarning(
                "Auswahl fehlt",
                "Bitte wählen Sie einen Geschäftspartner aus.",
                parent=self.window,
            )
            return
        BusinessPartnerEditDialog(
            self.window,
            self.controller,
            profile=self.selected_profile,
            on_saved=lambda profile: self.render_list(),
        ).open()

    def load_selected(self):
        if not self.selected_profile:
            messagebox.showwarning(
                "Auswahl fehlt",
                "Bitte wählen Sie einen Geschäftspartner aus.",
                parent=self.window,
            )
            return
        self.load(self.selected_profile)

    def activate(self, profile: BusinessPartnerProfile):
        if self.on_selected:
            self.load(profile)
            return
        self.selected_profile = profile
        self.edit_selected()

    def load(self, profile: BusinessPartnerProfile):
        if self.required_role and not profile.has_role(self.required_role):
            role_name = (
                "Kundenrolle"
                if self.required_role is BusinessPartnerRole.CUSTOMER
                else "Lieferantenrolle"
            )
            messagebox.showwarning(
                "Rolle fehlt",
                f"Dieser Geschäftspartner besitzt noch keine {role_name}. "
                "Bitte bearbeiten Sie zuerst seine Rollen.",
                parent=self.window,
            )
            return
        if self.on_selected:
            self.on_selected(profile)
            self.close()

    def delete_selected(self):
        if not self.selected_profile:
            messagebox.showwarning(
                "Auswahl fehlt",
                "Bitte wählen Sie einen Geschäftspartner aus.",
                parent=self.window,
            )
            return
        profile = self.selected_profile
        if not messagebox.askyesno(
            "Geschäftspartner löschen",
            f"Geschäftspartner {profile.partner_number} | {profile.name} wirklich löschen?",
            parent=self.window,
        ):
            return
        try:
            self.controller.delete_business_partner(profile.partner_number)
        except Exception as exc:
            messagebox.showerror("Geschäftspartner", str(exc), parent=self.window)
            return
        self.render_list()

    def close(self):
        if self._render_job is not None and self.window:
            self.window.after_cancel(self._render_job)
            self._render_job = None
        if self.window:
            self.window.destroy()
            self.window = None
