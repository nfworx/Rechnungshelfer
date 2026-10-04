"""Nicht blockierender Online-Updatecheck fuer Rechnungshelfer."""

import queue
import os
import threading
import webbrowser
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app_info import APP_VERSION, MAINTAINER_MODE_ENV
from .components import button
from .styles import FONT_NORMAL, FONT_SECTION, TEXT, TEXT_MUTED
from services.update_service import (
    OnlineUpdate,
    check_for_application_update,
    describe_application_update,
    launch_application_update,
)


class UpdateDialog:
    def __init__(self, parent, on_update_started):
        self.parent = parent
        self.on_update_started = on_update_started
        self.window = None
        self.status_label = None
        self.check_button = None
        self.install_button = None
        self.notes_button = None
        self._candidate: OnlineUpdate | None = None
        self._results: queue.SimpleQueue = queue.SimpleQueue()
        self._checking = False

    def open(self, initial_update: OnlineUpdate | None = None):
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            self.window.focus_force()
            if initial_update is not None:
                self._show_candidate(initial_update)
            return
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Rechnungshelfer-Updates")
        self.window.geometry("680x470")
        self.window.resizable(False, False)
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.window,
            text="Rechnungshelfer aktualisieren",
            font=FONT_SECTION,
            text_color=TEXT,
        ).grid(row=0, column=0, padx=24, pady=(24, 8))

        ctk.CTkLabel(
            self.window,
            text=(
                f"Installierte Programmversion: {APP_VERSION}\n\n"
                "Es werden ausschließlich stabile Rechnungshelfer-Releases aus dem "
                "offiziellen GitHub-Repository geprüft. Externe Prüfkomponenten sind "
                "Bestandteil des jeweiligen Programm-Releases. Der portable data-Ordner "
                "wird nicht verändert."
            ),
            font=FONT_NORMAL,
            text_color=TEXT_MUTED,
            justify="left",
            wraplength=610,
        ).grid(row=1, column=0, padx=30, pady=(0, 18), sticky="w")

        self.status_label = ctk.CTkLabel(
            self.window,
            text="Bereit zur Updateprüfung.",
            font=FONT_NORMAL,
            text_color=TEXT,
            justify="left",
            wraplength=610,
        )
        self.status_label.grid(row=2, column=0, padx=30, pady=(0, 18), sticky="w")

        self.check_button = button(self.window, "Jetzt nach Updates suchen", self._start_check, primary=True)
        self.check_button.grid(row=3, column=0, padx=55, pady=(0, 10), sticky="ew")
        self.install_button = button(self.window, "Update installieren", self._install, primary=True)
        self.install_button.grid(row=4, column=0, padx=55, pady=(0, 10), sticky="ew")
        self.install_button.configure(state="disabled")
        self.notes_button = button(self.window, "Versionshinweise öffnen", self._open_release_notes)
        self.notes_button.grid(row=5, column=0, padx=55, pady=(0, 10), sticky="ew")
        self.notes_button.configure(state="disabled")
        if os.environ.get(MAINTAINER_MODE_ENV) == "1":
            button(
                self.window,
                "Herausgeber: lokales Testmanifest auswählen",
                self._select_local_manifest,
            ).grid(row=6, column=0, padx=55, pady=(0, 10), sticky="ew")
        button(self.window, "Schließen", self.close).grid(row=7, column=0)

        if initial_update is not None:
            self._show_candidate(initial_update)
        else:
            self.window.after(150, self._start_check)

    def _start_check(self):
        if self._checking or self.window is None:
            return
        self._checking = True
        self._candidate = None
        self.status_label.configure(text="Updates werden geprüft …")
        self.check_button.configure(state="disabled")
        self.install_button.configure(state="disabled")
        self.notes_button.configure(state="disabled")

        def worker():
            try:
                self._results.put(("result", check_for_application_update()))
            except Exception as exc:
                self._results.put(("error", str(exc)))

        threading.Thread(target=worker, name="Rechnungshelfer-Updatecheck", daemon=True).start()
        self.window.after(100, self._poll_result)

    def _poll_result(self):
        if self.window is None or not self.window.winfo_exists():
            return
        try:
            kind, value = self._results.get_nowait()
        except queue.Empty:
            self.window.after(100, self._poll_result)
            return
        self._checking = False
        self.check_button.configure(state="normal")
        if kind == "error":
            self.status_label.configure(text=f"Updateprüfung fehlgeschlagen:\n{value}")
            return
        if value is None:
            self.status_label.configure(text=f"Rechnungshelfer {APP_VERSION} ist aktuell.")
            return
        self._show_candidate(value)

    def _show_candidate(self, update: OnlineUpdate):
        self._checking = False
        self._candidate = update
        details = "\n".join(update.summary.details)
        self.status_label.configure(text=f"Ein Update ist verfügbar.\n\n{details}")
        self.check_button.configure(state="normal")
        self.install_button.configure(state="normal")
        self.notes_button.configure(state="normal")

    def _install(self):
        if self._candidate is None:
            return
        details = "\n".join(self._candidate.summary.details)
        if not messagebox.askyesno(
            "Update installieren",
            f"{details}\n\nRechnungshelfer wird beendet, aktualisiert und neu gestartet.\n"
            "Der portable data-Ordner bleibt erhalten.\n\nJetzt installieren?",
            parent=self.window,
        ):
            return
        try:
            launch_application_update(self._candidate)
        except Exception as exc:
            messagebox.showerror("Update", str(exc), parent=self.window)
            return
        self.close()
        self.on_update_started()

    def _open_release_notes(self):
        if self._candidate is not None:
            webbrowser.open(self._candidate.release_url)

    def _select_local_manifest(self):
        source = filedialog.askopenfilename(
            parent=self.window,
            title="Lokales Programmmanifest auswählen",
            filetypes=[("JSON-Manifest", "*.json")],
        )
        if not source:
            return
        try:
            summary = describe_application_update(source)
            details = "\n".join(summary.details)
            if not messagebox.askyesno(
                "Lokales Testupdate",
                f"{details}\n\nDieses lokale Testupdate jetzt installieren?",
                parent=self.window,
            ):
                return
            launch_application_update(source)
        except Exception as exc:
            messagebox.showerror("Update", str(exc), parent=self.window)
            return
        self.close()
        self.on_update_started()

    def close(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None
