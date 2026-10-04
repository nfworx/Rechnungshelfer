# rechnungshelfer/gui/item_table.py

import customtkinter as ctk

from .styles import *
from .components import (
    card,
    button,
    small_button,
    set_entry_value,
    style_entry,
)
from services.format_service import format_de, parse_de
from services.unit_service import (
    get_unit_options,
    unit_code_to_display,
    unit_display_to_code,
)


class ItemTable:
    REQUIRED_FIELDS = {"name", "qty", "unit", "price_without_discount", "vat"}
    VAT_VALUES = ["0 %", "7 %", "7,8 %", "19 %"]

    def __init__(self, parent, invoice, on_change=None):
        self.parent = parent
        self.invoice = invoice
        self.on_change = on_change

        self.card = None
        self.header = None
        self.table = None

        self.item_entries = {}
        self.item_rows = {}

    def render(self):
        self.item_entries.clear()
        self.item_rows.clear()

        self.card = card(self.parent, "Positionen")
        self.card.grid(row=0, column=0, sticky="nsew")
        self.card.grid_columnconfigure(0, weight=1)
        self.card.grid_rowconfigure(3, weight=1)

        button(self.card, "+ Position", self.add_item).grid(
            row=1,
            column=0,
            sticky="w",
            padx=14,
            pady=(0, 8),
        )

        self.header = ctk.CTkFrame(
            self.card,
            fg_color="#f8fafc",
            corner_radius=8,
        )
        self.header.grid(row=2, column=0, sticky="ew", padx=14)

        self.table = ctk.CTkScrollableFrame(
            self.card,
            fg_color="#f8fafc",
            corner_radius=8,
            height=300,
            width=1100,
        )
        self.table.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 14))

        self._configure_columns(self.header)
        self._configure_columns(self.table)
        self._render_headers()
        self.refresh()

        return self.card

    def _columns(self):
        return [
            ("", 36),
            ("Pos", 45),
            ("Name *", 170),
            ("Detail", 230),
            ("Menge *", 65),
            ("Einheit *", 75),
            ("Preis *", 85),
            ("Rabatt", 75),
            ("MwSt *", 70),
            ("Gesamt", 95),
        ]

    def _fields(self):
        return [
            ("pos", 45),
            ("name", 170),
            ("description", 230),
            ("qty", 65),
            ("unit", 75),
            ("price_without_discount", 85),
            ("discount", 75),
            ("vat", 70),
            ("net", 95),
        ]

    def _numeric_fields(self):
        return {"qty", "price_without_discount", "discount", "vat", "net"}

    def _configure_columns(self, frame):
        for col, (_, width) in enumerate(self._columns()):
            frame.grid_columnconfigure(col, minsize=width)

    def _render_headers(self):
        for col, (header, width) in enumerate(self._columns()):
            ctk.CTkLabel(
                self.header,
                text=header,
                width=width,
                font=("Segoe UI", 11, "bold"),
                text_color=TEXT,
                anchor="center" if col in (0, 1) else "w",
            ).grid(row=0, column=col, sticky="ew", padx=3, pady=(6, 6))

    def _ensure_required_item_fields(self):
        for item in self.invoice.items:
            current = set(getattr(item, "required_fields", []))
            item.required_fields = list(current | self.REQUIRED_FIELDS)

    def refresh(self):
        if not self.invoice.items:
            from rechnungshelfer.domain.models import InvoiceItem

            self.invoice.items.append(InvoiceItem())

        self._ensure_required_item_fields()

        current_ids = {id(item) for item in self.invoice.items}
        existing_ids = set(self.item_rows.keys())

        for removed_id in existing_ids - current_ids:
            self._destroy_item_row(removed_id)

        for idx, item in enumerate(self.invoice.items, start=1):
            item.pos = idx

            if id(item) not in self.item_rows:
                self._create_item_row(idx, item)
            else:
                self._move_item_row(idx, item)
                self._update_item_row_values(item)

        self._notify_change()

    def add_item(self):
        from rechnungshelfer.domain.models import InvoiceItem

        self.invoice.items.append(InvoiceItem())
        self.refresh()

    def _destroy_item_row(self, item_id):
        for widget in self.item_rows.get(item_id, []):
            try:
                widget.destroy()
            except Exception:
                pass

        self.item_rows.pop(item_id, None)

        for key in list(self.item_entries.keys()):
            if key[0] == item_id:
                del self.item_entries[key]

    def _create_item_row(self, row, item):

        widgets = []

        def remove():
            if item in self.invoice.items:
                self.invoice.items.remove(item)
                self.refresh()

        remove_btn = small_button(self.table, "-", remove)
        remove_btn.grid(row=row, column=0, sticky="ew", padx=3, pady=3)
        widgets.append(remove_btn)

        for col, (attr, width) in enumerate(self._fields(), start=1):
            raw_value = getattr(item, attr, "")
            value = format_de(raw_value) if attr in self._numeric_fields() else raw_value
            if attr == "vat":
                value = f"{format(raw_value.normalize(), 'f').replace('.', ',')} %"

            if attr == "unit":
                widget = self._create_option_menu(
                    row=row,
                    col=col,
                    width=width,
                    values=get_unit_options(),
                    value=unit_code_to_display(raw_value),
                    command=lambda selected, it=item: self._update_item_field(
                        it,
                        "unit",
                        unit_display_to_code(selected),
                    ),
                )

            elif attr == "vat":
                widget = self._create_option_menu(
                    row=row,
                    col=col,
                    width=width,
                    values=self.VAT_VALUES,
                    value=str(value or "19,00"),
                    command=lambda selected, it=item: self._update_item_field(
                        it, "vat", selected
                    ),
                )

            else:
                widget = self._create_entry(
                    row=row,
                    col=col,
                    width=width,
                    value=str(value or ""),
                    item=item,
                    attr=attr,
                )

            self.item_entries[(id(item), attr)] = widget
            widgets.append(widget)

        self.item_rows[id(item)] = widgets

    def _create_entry(self, row, col, width, value, item, attr):
        entry = ctk.CTkEntry(
            self.table,
            height=26,
            width=width,
            font=FONT_SMALL,
            corner_radius=5,
            border_width=1,
        )
        entry.insert(0, value)
        entry.grid(row=row, column=col, sticky="ew", padx=3, pady=3)

        is_readonly = attr in getattr(item, "readonly_fields", [])
        is_required = attr in getattr(item, "required_fields", [])
        filled = bool(value)

        if is_readonly:
            entry.configure(state="disabled")
            style_entry(entry, state="disabled")
            return entry

        style_entry(entry, required=is_required, filled=filled)

        entry.bind(
            "<KeyRelease>",
            lambda event, it=item, field=attr, ent=entry: self._update_item_field(
                it,
                field,
                ent.get(),
            ),
        )

        entry.bind(
            "<FocusIn>",
            lambda event, it=item, field=attr, ent=entry: style_entry(
                ent,
                required=field in getattr(it, "required_fields", []),
                filled=bool(ent.get()),
                focused=True,
            ),
        )

        entry.bind(
            "<FocusOut>",
            lambda event, it=item, field=attr, ent=entry: self._on_entry_focus_out(
                it,
                field,
                ent,
            ),
        )

        return entry

    def _create_option_menu(self, row, col, width, values, value, command):
        widget = ctk.CTkOptionMenu(
            self.table,
            values=values,
            height=26,
            width=width,
            font=FONT_SMALL,
            command=command,
            fg_color=ENTRY_BG,
            button_color=ENTRY_BORDER,
            button_hover_color=BTN_HOVER,
            text_color=ENTRY_TEXT,
            dropdown_fg_color=CARD_BG,
            dropdown_text_color=TEXT,
            dropdown_hover_color=BTN_HOVER,
        )

        if value not in values:
            values = values + [value]
            widget.configure(values=values)

        widget.set(value)
        widget.grid(row=row, column=col, sticky="ew", padx=3, pady=3)

        return widget

    def _move_item_row(self, row, item):
        for widget in self.item_rows.get(id(item), []):
            widget.grid_configure(row=row)

        pos_entry = self.item_entries.get((id(item), "pos"))
        if pos_entry:
            set_entry_value(
                pos_entry,
                str(item.pos),
                disabled=("pos" in getattr(item, "readonly_fields", [])),
            )

    def _update_item_row_values(self, item):

        for attr, _ in self._fields():
            widget = self.item_entries.get((id(item), attr))
            if not widget:
                continue

            if (
                hasattr(widget, "focus_get")
                and widget.focus_get() == widget
                and attr not in ("net", "pos")
            ):
                continue

            value = getattr(item, attr, "")

            if attr in self._numeric_fields():
                value = format_de(value)
            if attr == "vat":
                value = f"{format(item.vat.normalize(), 'f').replace('.', ',')} %"

            disabled = attr in getattr(item, "readonly_fields", [])
            set_entry_value(widget, str(value or ""), disabled=disabled)

    def _update_item_field(self, item, field, value):

        try:
            if field in ("qty", "price_without_discount", "discount"):
                setattr(item, field, parse_de(value))
                item.recalculate()

            elif field == "vat":
                item.set_vat(parse_de(str(value).replace("%", "")))

            else:
                setattr(item, field, value)

            self.refresh_calculated_fields(item)
            self._refresh_widget_required_style(item, field, value)
            self._notify_change()

        except ValueError:
            self._refresh_widget_required_style(item, field, value)

    def _on_entry_focus_out(self, item, field, entry):
        self._format_item_field(item, field, entry)

        style_entry(
            entry,
            required=field in getattr(item, "required_fields", []),
            filled=bool(entry.get()),
            focused=False,
        )

    def _format_item_field(self, item, field, entry):

        if field not in ("qty", "price", "discount"):
            return

        try:
            value = getattr(item, field, "")
            disabled = field in getattr(item, "readonly_fields", [])
            set_entry_value(entry, format_de(value), disabled=disabled)
        except Exception:
            pass

    def refresh_calculated_fields(self, item):

        entry = self.item_entries.get((id(item), "net"))
        if not entry:
            return

        disabled = "net" in getattr(item, "readonly_fields", [])
        set_entry_value(entry, format_de(getattr(item, "net", 0)), disabled=disabled)

    def _refresh_widget_required_style(self, item, field, value):
        widget = self.item_entries.get((id(item), field))

        if not widget:
            return

        if isinstance(widget, ctk.CTkOptionMenu):
            return

        try:
            style_entry(
                widget,
                required=field in getattr(item, "required_fields", []),
                filled=bool(value),
                focused=True,
            )
        except Exception:
            pass

    def _notify_change(self):
        if self.on_change:
            self.on_change()
        else:
            self.invoice.calculate(force=True)
