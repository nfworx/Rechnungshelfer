"""Flackerarmer Austausch der vollstaendigen Formularoberflaeche.

Das Modul kapselt bewusst sowohl die Formularflaechen als auch den gepufferten
Wechsel. Das bisher sichtbare Formular bleibt dabei vor dem neuen Formular,
bis dessen Widgets vollstaendig aufgebaut und vermessen wurden.
"""

import customtkinter as ctk

from gui_ctk.styles import APP_BG


class FormSurface:
    """Eine vollstaendige, noch leere Formularflaeche."""

    def __init__(self, parent):
        self.frame = ctk.CTkFrame(parent, fg_color=APP_BG, corner_radius=0)
        self.frame.grid_columnconfigure(0, weight=4)
        self.frame.grid_columnconfigure(1, weight=1)
        self.frame.grid_rowconfigure(0, weight=0)
        self.frame.grid_rowconfigure(1, weight=1)

        self.top_grid = ctk.CTkFrame(
            self.frame,
            fg_color=APP_BG,
            corner_radius=0,
        )
        self.top_grid.grid(row=0, column=0, columnspan=2, sticky="ew")

        for column in range(3):
            self.top_grid.grid_columnconfigure(
                column,
                weight=1,
                uniform="top_cards",
            )

        self.buyer_area = ctk.CTkFrame(
            self.top_grid,
            fg_color=APP_BG,
            corner_radius=0,
        )
        self.buyer_area.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.delivery_area = ctk.CTkFrame(
            self.top_grid,
            fg_color=APP_BG,
            corner_radius=0,
        )
        self.delivery_area.grid(row=0, column=1, sticky="nsew", padx=8)

        self.info_area = ctk.CTkFrame(
            self.top_grid,
            fg_color=APP_BG,
            corner_radius=0,
        )
        self.info_area.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        self.items_area = ctk.CTkFrame(
            self.frame,
            fg_color=APP_BG,
            corner_radius=0,
        )
        self.items_area.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 12),
            pady=(14, 0),
        )
        self.items_area.grid_columnconfigure(0, weight=1)
        self.items_area.grid_rowconfigure(0, weight=1)

        self.totals_area = ctk.CTkFrame(
            self.frame,
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


class BufferedFormHost(ctk.CTkFrame):
    """Haelt die alte Form sichtbar, waehrend die neue aufgebaut wird."""

    def __init__(self, parent):
        super().__init__(parent, fg_color=APP_BG, corner_radius=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._active_surface = None
        self._pending_surface = None

        # Verdeckt auch den allerersten Aufbau, fuer den es noch keine alte
        # Formularflaeche als visuellen Puffer gibt.
        self._initial_cover = ctk.CTkFrame(
            self,
            fg_color=APP_BG,
            corner_radius=0,
        )
        self._initial_cover.grid(row=0, column=0, sticky="nsew")

    @property
    def active_surface(self):
        return self._active_surface

    def begin_swap(self):
        if self._pending_surface is not None:
            raise RuntimeError("Ein Formularwechsel wird bereits aufgebaut.")

        surface = FormSurface(self)
        surface.frame.grid(row=0, column=0, sticky="nsew")
        self._pending_surface = surface

        cover = (
            self._active_surface.frame
            if self._active_surface is not None
            else self._initial_cover
        )
        cover.tkraise()
        return surface

    def commit_swap(self):
        if self._pending_surface is None:
            raise RuntimeError("Es gibt keinen vorbereiteten Formularwechsel.")

        new_surface = self._pending_surface
        old_surface = self._active_surface

        # Layoutberechnungen abschliessen, solange noch die alte Form sichtbar
        # ist. Anschliessend wird nur ein kompletter Frame nach vorne geholt.
        new_surface.frame.update_idletasks()
        new_surface.frame.tkraise()

        self._active_surface = new_surface
        self._pending_surface = None

        if self._initial_cover is not None:
            self._initial_cover.destroy()
            self._initial_cover = None

        if old_surface is not None:
            self.after_idle(old_surface.frame.destroy)

    def cancel_swap(self):
        if self._pending_surface is None:
            return
        self._pending_surface.frame.destroy()
        self._pending_surface = None

