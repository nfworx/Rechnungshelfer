import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

from rechnungshelfer.gui.report_viewer import show_html_report
from rechnungshelfer.services.export_service import ExportValidationError


class ExportWorkflow:
    """Steuert PDF-/XML-Exporte und ihre Dialoge."""

    def __init__(self, root, controller, invoice_provider):
        self.root = root
        self.controller = controller
        self.invoice_provider = invoice_provider

    def generate_pdf(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Dateien", "*.pdf")],
        )
        if not filepath:
            return

        try:
            self.controller.generate_pdf(self.invoice_provider(), filepath)
            messagebox.showinfo("Export", "PDF wurde erstellt.")
        except Exception as exc:
            messagebox.showerror("Fehler", str(exc))

    def generate_xml(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".xml",
            filetypes=[("XML Dateien", "*.xml")],
        )
        if not filepath:
            return

        progress = self._create_progress_dialog()
        threading.Thread(
            target=self._export_xml,
            args=(progress, filepath),
            daemon=True,
        ).start()

    def _create_progress_dialog(self):
        progress = ctk.CTkToplevel(self.root)
        progress.title("XML Export")
        progress.geometry("360x130")
        progress.resizable(False, False)
        progress.transient(self.root)
        progress.grab_set()

        label = ctk.CTkLabel(
            progress,
            text="XML wird validiert und exportiert...\nBitte warten.",
        )
        label.pack(pady=(24, 12))

        bar = ctk.CTkProgressBar(progress, mode="indeterminate")
        bar.pack(fill="x", padx=30)
        bar.start()
        return progress

    def _export_xml(self, progress, filepath):
        try:
            export_result = self.controller.generate_xml(
                self.invoice_provider(),
                filepath,
            )
            self.root.after(
                0,
                lambda: self._finish_xml_export_success(
                    progress,
                    export_result.validation_result,
                ),
            )
        except ExportValidationError as exc:
            message = str(exc)
            details = exc.details
            report_html = exc.report_html
            self.root.after(
                0,
                lambda: self._finish_xml_export_validation_error(
                    progress,
                    message,
                    details,
                    report_html,
                ),
            )
        except ValueError as exc:
            message = str(exc)
            self.root.after(
                0,
                lambda: self._finish_xml_export_warning(progress, message),
            )
        except Exception as exc:
            message = str(exc)
            self.root.after(
                0,
                lambda: self._finish_xml_export_error(progress, message),
            )

    def can_export_pdf(self):
        try:
            return self.controller.check_pdf_required_fields(
                self.invoice_provider()
            )
        except Exception:
            return False

    def can_export_xml(self):
        try:
            return self.controller.check_xml_required_fields(
                self.invoice_provider()
            )
        except Exception:
            return False

    def pdf_export_hint(self):
        return self._export_hint(for_xml=False, export_name="PDF")

    def xml_export_hint(self):
        return self._export_hint(for_xml=True, export_name="XML")

    def _export_hint(self, for_xml, export_name):
        try:
            missing = self.controller.get_missing_required_fields(
                self.invoice_provider(),
                for_xml=for_xml,
            )
            if not missing:
                return ""
            return self.controller.format_missing_fields(missing, export_name)
        except Exception:
            return f"{export_name}-Export ist derzeit nicht möglich."

    def _finish_xml_export_success(self, progress, validation_result=None):
        self._close_progress(progress)
        if validation_result and validation_result.report_html:
            if messagebox.askyesno(
                "Export",
                "XML wurde erstellt.\n\nPrüfbericht anzeigen?",
            ):
                show_html_report(validation_result.report_html)
        else:
            messagebox.showinfo("Export", "XML wurde erstellt.")

    def _finish_xml_export_warning(self, progress, message):
        self._close_progress(progress)
        messagebox.showwarning("Export abgebrochen", message)

    @staticmethod
    def _close_progress(progress):
        try:
            if progress.winfo_exists():
                progress.destroy()
        except Exception:
            pass

    def _finish_xml_export_error(self, progress, message):
        self._close_progress(progress)
        messagebox.showerror("Fehler", message)

    def _finish_xml_export_validation_error(
        self,
        progress,
        message,
        details,
        report_html,
    ):
        self._close_progress(progress)
        self._show_validation_error_dialog(message, details, report_html)

    def _show_validation_error_dialog(self, message, details, report_html):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Export abgebrochen")
        dialog.geometry("520x230")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        label = ctk.CTkLabel(
            dialog,
            text=message,
            justify="left",
            wraplength=460,
        )
        label.pack(padx=24, pady=(28, 18), anchor="w")

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(fill="x", padx=24, pady=(0, 20))

        def export_log():
            filepath = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Textdatei", "*.txt")],
                initialfile="validation-error-log.txt",
            )
            if not filepath:
                return

            with open(filepath, "w", encoding="utf-8") as file:
                file.write(details)
            messagebox.showinfo("Fehlerlog", "Fehlerlog wurde exportiert.")

        ctk.CTkButton(
            button_frame,
            text="Fehlerlog exportieren",
            command=export_log,
        ).pack(side="left")
        ctk.CTkButton(
            button_frame,
            text="Prüfbericht anzeigen",
            command=lambda: self._show_validation_report(report_html),
        ).pack(side="left", padx=(10, 0))
        ctk.CTkButton(
            button_frame,
            text="OK",
            command=dialog.destroy,
        ).pack(side="right")

    @staticmethod
    def _show_validation_report(html_content):
        if not html_content:
            messagebox.showinfo(
                "Prüfbericht",
                "Kein Prüfbericht verfügbar.",
            )
            return
        show_html_report(html_content)
