# rechnungshelfer/gui/party_card.py

import customtkinter as ctk

from .styles import *
from .components import card, style_entry
from .date_fields import attach_date_validation, open_datepicker
from .customer_autocomplete import CustomerAutocomplete


class PartyCard:
    def __init__(
        self,
        parent,
        title,
        model,
        on_change=None,
        on_delivery_toggle=None,
        delivery_checked=False,
        disabled=False,
        field_entries=None,
        exclude_fields=None,
        extra_fields=None,
        controller=None,
        on_customer_select=None,
        label_overrides=None,
    ):
        self.parent = parent
        self.title = title
        self.model = model
        self.on_change = on_change
        self.on_delivery_toggle = on_delivery_toggle
        self.delivery_checked = delivery_checked
        self.disabled = disabled
        self.field_entries = field_entries if field_entries is not None else {}
        self.exclude_fields = set(exclude_fields or [])
        self.extra_fields = extra_fields or []
        self.controller = controller
        self.on_customer_select = on_customer_select
        self.label_overrides = label_overrides or {}

        self.frame = None

    def render(self):
        self.frame = card(self.parent, self.title, disabled=self.disabled)

        row = 1
        row = self._render_model_fields(self.model, row)

        for extra_model, fields in self.extra_fields:
            row = self._render_model_fields(extra_model, row, only_fields=fields)

        if self.title == "Kunde":
            self._render_delivery_checkbox(row)
            row += 1

        self.frame.grid_rowconfigure(row, minsize=12)

        return self.frame

    def _render_model_fields(self, model, row, only_fields=None):
        internal_fields = {
            "required_fields",
            "readonly_fields",
            "FIELD_LABELS_DE",
            "use_invoice_address_as_delivery",
        }

        readonly_fields = getattr(model, "readonly_fields", [])

        date_fields = {
            "invoice_date": "Rechnungsdatum",
            "payment_due_date": "Zahlungsziel",
            "delivery_date": "Lieferdatum",
        }

        for field, value in model.__dict__.items():
            if field.startswith("_") or field in internal_fields:
                continue

            if field in self.exclude_fields:
                continue

            if only_fields is not None and field not in only_fields:
                continue

            label_text = model.get_label(field) if hasattr(model, "get_label") else field
            label_text = self.label_overrides.get(field, label_text)

            ctk.CTkLabel(
                self.frame,
                text=label_text,
                font=FONT_SMALL,
                text_color=TEXT_MUTED if self.disabled else TEXT,
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=(14, 8), pady=2)

            entry = ctk.CTkEntry(
                self.frame,
                height=24,
                font=FONT_SMALL,
                corner_radius=6,
                border_width=1,
            )
            entry.insert(0, str(value or ""))
            entry.grid(row=row, column=1, sticky="ew", padx=(0, 6), pady=2)

            if field in ("customer_number", "supplier_number") and not self.disabled:
                validate_number = self.frame.register(
                    lambda proposed: not proposed
                    or (proposed.isascii() and proposed.isdigit())
                )
                entry.configure(
                    validate="key",
                    validatecommand=(validate_number, "%P"),
                )

            if (
                self.title == "Kunde"
                and self.controller
                and self.on_customer_select
                and field in ("customer_number", "name", "email", "leitweg_id")
            ):
                CustomerAutocomplete(
                    self.frame,
                    entry,
                    self.controller,
                    field,
                    self.on_customer_select,
                )

            if field in date_fields and not self.disabled:
                calendar_button = ctk.CTkButton(
                    self.frame,
                    text="📅",
                    width=30,
                    height=24,
                )
                calendar_button.configure(
                    command=(
                        lambda ent=entry,
                        name=label_text,
                        anchor=calendar_button: open_datepicker(ent, name, anchor)
                    )
                )
                calendar_button.grid(row=row, column=2, sticky="e", padx=(0, 14), pady=2)

            self.field_entries[(id(model), field)] = entry

            is_readonly = field in readonly_fields or self.disabled
            is_required = field in getattr(model, "required_fields", [])
            filled = bool(value)

            if is_readonly:
                entry.configure(state="disabled")
                style_entry(
                    entry,
                    state="disabled",
                    required=is_required,
                    filled=filled,
                )
            else:
                entry.configure(state="normal")
                style_entry(entry, required=is_required, filled=filled)

                entry.bind(
                    "<KeyRelease>",
                    lambda event, obj=model, attr=field, ent=entry: self._handle_change(
                        obj,
                        attr,
                        ent.get(),
                    ),
                )

                entry.bind(
                    "<FocusIn>",
                    lambda event, obj=model, attr=field, ent=entry: style_entry(
                        ent,
                        required=attr in getattr(obj, "required_fields", []),
                        filled=bool(ent.get()),
                        focused=True,
                    ),
                )

                entry.bind(
                    "<FocusOut>",
                    lambda event, obj=model, attr=field, ent=entry: style_entry(
                        ent,
                        required=attr in getattr(obj, "required_fields", []),
                        filled=bool(ent.get()),
                        focused=False,
                    ),
                )

                if field in date_fields:
                    attach_date_validation(
                        entry,
                        label_text,
                        required=field != "delivery_date",
                    )

            row += 1

        return row

    def _handle_change(self, obj, attr, value):
        setattr(obj, attr, value)

        entry = self.field_entries.get((id(obj), attr))

        if entry:
            style_entry(
                entry,
                required=attr in getattr(obj, "required_fields", []),
                filled=bool(value),
                focused=True,
            )

        if self.on_change:
            self.on_change(obj, attr, value)

    def _render_delivery_checkbox(self, row):
        chk_var = ctk.BooleanVar(value=bool(self.delivery_checked))

        def toggle():
            if self.on_delivery_toggle:
                self.on_delivery_toggle(bool(chk_var.get()))

        ctk.CTkCheckBox(
            self.frame,
            text="Rechnungsadresse = Lieferadresse",
            variable=chk_var,
            command=toggle,
            font=FONT_SMALL,
            text_color=TEXT,
        ).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="w",
            padx=14,
            pady=(8, 10),
        )
