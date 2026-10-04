"""Kleines, unabhaengiges Fortschrittsfenster fuer den Programm-Updater."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Callable


ProgressCallback = Callable[[int, str], None]


class UpdateProgressWindow:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.events: queue.SimpleQueue[tuple] = queue.SimpleQueue()
        self.result = 1
        self.root = tk.Tk()
        self.root.title("Rechnungshelfer wird aktualisiert")
        self.root.geometry("500x215")
        self.root.resizable(False, False)
        self.root.configure(bg="#f8fafc")
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        tk.Label(
            self.root,
            text="Rechnungshelfer-Update",
            bg="#f8fafc",
            fg="#1f2933",
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=(24, 8))
        self.status = tk.Label(
            self.root,
            text="Updater wird gestartet ...",
            bg="#f8fafc",
            fg="#475569",
            font=("Segoe UI", 10),
        )
        self.status.pack(pady=(0, 14))

        self.bar = tk.Canvas(
            self.root,
            width=420,
            height=22,
            bg="#dbe3ea",
            highlightthickness=0,
        )
        self.bar.pack()
        self.fill = self.bar.create_rectangle(0, 0, 0, 22, fill="#22a447", outline="")
        self.percent = tk.Label(
            self.root,
            text="0 %",
            bg="#f8fafc",
            fg="#1f2933",
            font=("Segoe UI", 10, "bold"),
        )
        self.percent.pack(pady=(7, 0))
        tk.Label(
            self.root,
            text="Bitte schliessen Sie dieses Fenster nicht.",
            bg="#f8fafc",
            fg="#64748b",
            font=("Segoe UI", 9),
        ).pack(pady=(8, 0))

        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - self.root.winfo_width()) // 2
        y = (self.root.winfo_screenheight() - self.root.winfo_height()) // 2
        self.root.geometry(f"+{max(0, x)}+{max(0, y)}")

    def report(self, percent: int, message: str) -> None:
        """Darf aus dem Worker-Thread aufgerufen werden."""
        acknowledgement = threading.Event() if percent >= 100 else None
        self.events.put(("progress", percent, message, acknowledgement))
        if acknowledgement is not None:
            # Der Neustart erfolgt erst, nachdem 100 % sichtbar gezeichnet wurden.
            acknowledgement.wait(timeout=2)

    def _set_progress(self, percent: int, message: str) -> None:
        value = max(0, min(100, int(percent)))
        self.bar.coords(self.fill, 0, 0, 420 * value / 100, 22)
        self.percent.configure(text=f"{value} %")
        self.status.configure(text=message)
        self.root.update_idletasks()

    def _worker(self, operation: Callable[[ProgressCallback], int]) -> None:
        try:
            result = operation(self.report)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if code == 0:
                self.events.put(("done", 0))
            else:
                self.events.put(("error", "Der Updater wurde mit ungueltigen Parametern gestartet."))
        except Exception as exc:
            logging.exception("Update fehlgeschlagen")
            self.events.put(("error", str(exc)))
        else:
            self.events.put(("done", result))

    def _poll(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "progress":
                _, percent, message, acknowledgement = event
                self._set_progress(percent, message)
                if acknowledgement is not None:
                    acknowledgement.set()
            elif event[0] == "done":
                self.result = int(event[1])
                self.root.after(650, self.root.destroy)
                return
            elif event[0] == "error":
                self.result = 1
                self.status.configure(text="Update fehlgeschlagen – vorherige Version wird beibehalten.")
                messagebox.showerror(
                    "Rechnungshelfer-Updater",
                    f"Update fehlgeschlagen:\n\n{event[1]}\n\nProtokoll: {self.log_path}",
                    parent=self.root,
                )
                self.root.destroy()
                return
        self.root.after(50, self._poll)

    def run(self, operation: Callable[[ProgressCallback], int]) -> int:
        threading.Thread(
            target=self._worker,
            args=(operation,),
            name="Rechnungshelfer-Updater-Worker",
            daemon=True,
        ).start()
        self.root.after(50, self._poll)
        self.root.mainloop()
        return self.result


def run_with_progress(operation: Callable[[ProgressCallback], int], log_path: Path) -> int:
    return UpdateProgressWindow(log_path).run(operation)
