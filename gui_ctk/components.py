# gui_ctk/components.py

import customtkinter as ctk
from gui_ctk.styles import *


class HoverTooltip:
    def __init__(self, widget, text_provider, delay_ms=350):
        self.widget = widget
        self.text_provider = text_provider
        self.delay_ms = delay_ms
        self._job = None
        self._window = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, event=None):
        self.hide()
        self._job = self.widget.after(self.delay_ms, self.show)

    def show(self):
        self._job = None
        text = str(self.text_provider() or "").strip()
        if not text or not self.widget.winfo_exists():
            return

        self._window = ctk.CTkToplevel(self.widget)
        self._window.withdraw()
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)

        label = ctk.CTkLabel(
            self._window,
            text=text,
            justify="left",
            anchor="w",
            fg_color="#fff7ed",
            text_color=TEXT,
            corner_radius=6,
            wraplength=520,
            padx=10,
            pady=7,
            font=FONT_SMALL,
        )
        label.pack()

        self._window.update_idletasks()
        x = self.widget.winfo_pointerx() + 12
        y = self.widget.winfo_pointery() + 16
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()
        width = self._window.winfo_reqwidth()
        height = self._window.winfo_reqheight()
        x = min(x, max(0, screen_width - width - 8))
        y = min(y, max(0, screen_height - height - 8))
        self._window.geometry(f"+{x}+{y}")
        self._window.deiconify()

    def hide(self, event=None):
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None


def card(parent, title, disabled=False):
    frame = ctk.CTkFrame(
        parent,
        fg_color="#f1f5f9" if disabled else CARD_BG,
        corner_radius=12,
        border_width=1,
        border_color=BORDER,
    )

    frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        frame,
        text=title,
        font=FONT_SECTION,
        text_color=TEXT_MUTED if disabled else TEXT,
        anchor="w",
    ).grid(
        row=0,
        column=0,
        columnspan=2,
        sticky="ew",
        padx=14,
        pady=(10, 7),
    )

    return frame


def button(parent, text, command, primary=False):
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        height=32,
        corner_radius=6,
        fg_color=BTN_PRIMARY_BG if primary else BTN_BG,
        hover_color=BTN_PRIMARY_HOVER if primary else BTN_HOVER,
        text_color=BTN_TEXT,
        border_width=1,
        border_color=BTN_BORDER,
        font=FONT_NORMAL,
    )

def small_button(parent, text, command):
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        width=26,
        height=26,
        corner_radius=5,
        fg_color=BTN_BG,
        hover_color=BTN_HOVER,
        text_color=BTN_TEXT,
        border_width=1,
        border_color=BTN_BORDER,
        font=FONT_SMALL,
    )


def clear_frame(frame):
    for widget in frame.winfo_children():
        widget.destroy()


def set_entry_value(widget, value, disabled=False):
    try:
        if isinstance(widget, ctk.CTkOptionMenu):
            widget.set(value)
            widget.configure(state="disabled" if disabled else "normal")
            return

        current_state = widget.cget("state")

        if current_state == "disabled":
            widget.configure(state="normal")

        if widget.get() != value:
            widget.delete(0, "end")
            widget.insert(0, value)

        widget.configure(state="disabled" if disabled else "normal")

    except Exception:
        pass

def style_entry(entry, state="normal", required=False, filled=True, focused=False):
    if state == "disabled":
        entry.configure(
            fg_color=ENTRY_REQUIRED_BG if required and not filled else ENTRY_DISABLED_BG,
            text_color=ENTRY_DISABLED_TEXT,
            border_color=ENTRY_REQUIRED_BORDER if required and not filled else ENTRY_DISABLED_BORDER,
            border_width=1,
        )
        return

    if required and not filled:
        entry.configure(
            fg_color=ENTRY_REQUIRED_BG,
            text_color=ENTRY_TEXT,
            border_color=ENTRY_REQUIRED_BORDER,
            border_width=1,
        )
        return

    entry.configure(
        fg_color=ENTRY_BG,
        text_color=ENTRY_TEXT,
        border_color=ENTRY_FOCUS_BORDER if focused else ENTRY_BORDER,
        border_width=1,
    )

def set_button_enabled(btn, enabled=True, primary=False):
    if enabled:
        btn.configure(
            state="normal",
            fg_color=BTN_PRIMARY_BG if primary else BTN_BG,
            hover_color=BTN_PRIMARY_HOVER if primary else BTN_HOVER,
            text_color=BTN_TEXT,
            border_color=BTN_BORDER,
        )
    else:
        btn.configure(
            state="disabled",
            fg_color=BTN_DISABLED_BG,
            hover_color=BTN_DISABLED_BG,
            text_color=BTN_DISABLED_TEXT,
            border_color=BTN_DISABLED_BORDER,
        )
