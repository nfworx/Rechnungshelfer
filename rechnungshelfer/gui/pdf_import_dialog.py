"""Nicht blockierender PDF-Import mit kontrollierter Formularuebernahme."""

from __future__ import annotations

import queue
import threading
from tkinter import messagebox

import customtkinter as ctk

from .components import button
from .settlement_review_dialog import SettlementReviewDialog
from .styles import FONT_NORMAL, FONT_SECTION, FONT_SMALL, TEXT, TEXT_MUTED
from rechnungshelfer.domain.models import DocumentType
from rechnungshelfer.services.pdf_invoice_parser import BUSINESS_PARTNER_NUMBER_PATH


FIELD_LABELS = {
    "info.invoice_number": "Belegnummer",
    "info.invoice_date": "Belegdatum",
    "info.payment_due_date": "Fälligkeitsdatum",
    "info.delivery_date": "Liefer-/Leistungsdatum",
    "info.delivery_note": "Lieferschein",
    "info.delivery_instruction": "Lieferhinweis",
    "buyer.name": "Kunde/Käufer",
    "seller.name": "Lieferant/Verkäufer",
    "buyer.contact_name": "Ansprechpartner des Kunden",
    "buyer.street": "Straße des Kunden",
    "buyer.postcode": "PLZ des Kunden",
    "buyer.city": "Ort des Kunden",
    "buyer.leitweg_id": "Käuferreferenz / Leitweg-ID (BT-10)",
    "delivery.name": "Leistungsempfänger",
    "delivery.street": "Straße des Leistungsempfängers",
    "delivery.postcode": "PLZ des Leistungsempfängers",
    "delivery.city": "Ort des Leistungsempfängers",
    "delivery.country": "Land des Leistungsempfängers",
    "payment.iban": "IBAN",
    "payment.bic": "BIC",
    "payment.account_holder": "Kontoinhaber",
    "payment.payment_terms": "Zahlungsbedingungen",
}


def format_detected_fields(fields, document_type=DocumentType.INVOICE) -> list[str]:
    number_label = (
        "Geschäftspartnernummer (Lieferant/Kreditor)"
        if document_type is DocumentType.SELF_BILLED_INVOICE
        else "Geschäftspartnernummer (Kunde)"
    )
    return [
        f"{number_label if field.path == BUSINESS_PARTNER_NUMBER_PATH else FIELD_LABELS.get(field.path, field.path)}: "
        f"{field.value} "
        f"(Seite {field.page_number}, {field.confidence:.0%})"
        for field in fields
    ]


def format_settlement_draft(draft) -> list[str]:
    """Kompakte, schreibgeschützte Übersicht einer erkannten Abrechnung."""

    def value(detected, fallback="nicht erkannt"):
        return str(detected.value) if detected is not None else fallback

    lines = [
        "Sammel-Final-Gutschrift erkannt – Übernahme erfordert Prüfung.",
        f"Gutschriftnummer: {value(draft.credit_note_number)}",
        f"Ausstellungsdatum: {value(draft.credit_note_date)}",
        f"Erkannte Lieferungen: {len(draft.deliveries)}",
    ]
    for delivery in draft.deliveries:
        amount = (
            f"{delivery.net_amount.value:.2f} EUR"
            if delivery.net_amount is not None
            else "Betrag nicht erkannt"
        )
        lines.append(
            f"• Lieferschein {delivery.ticket_number.value}: {amount} "
            f"(Seite {delivery.ticket_number.page_number}, "
            f"{delivery.ticket_number.confidence:.0%})"
        )
    lines.extend(
        (
            f"Nettosumme: {value(draft.net_amount)} EUR",
            f"Umsatzsteuer: {value(draft.vat_rate)} % / "
            f"{value(draft.vat_amount)} EUR",
            f"Gutschriftbetrag: {value(draft.credit_amount)} EUR",
        )
    )
    lines.extend(f"• {warning}" for warning in draft.warnings)
    return lines


class PdfImportDialog:
    def __init__(
        self,
        parent,
        controller,
        on_invoice_loaded,
        on_grain_credit_note_loaded=None,
    ):
        self.parent = parent
        self.controller = controller
        self.on_invoice_loaded = on_invoice_loaded
        self.on_grain_credit_note_loaded = (
            on_grain_credit_note_loaded or on_invoice_loaded
        )
        self.window = None
        self.progress = None
        self._results = queue.SimpleQueue()
        self._analysis = None
        self._import = None
        self._grain_credit_note = None
        self._filepath = None
        self._job_id = 0
        self._settlement_review_dialog = None

    def open(self, filepath, *, source_cleanup=None):
        self.close()
        self._job_id += 1
        job_id = self._job_id
        self._filepath = filepath
        self._analysis = None
        self._import = None
        self._grain_credit_note = None
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("PDF einlesen")
        self.window.geometry("560x230")
        self.window.resizable(False, False)
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.window,
            text="PDF wird analysiert",
            font=FONT_SECTION,
            text_color=TEXT,
        ).grid(row=0, column=0, padx=24, pady=(28, 10))
        ctk.CTkLabel(
            self.window,
            text="Textschichten werden gelesen und erforderliche Seiten per OCR verarbeitet.",
            font=FONT_NORMAL,
            text_color=TEXT_MUTED,
            wraplength=500,
        ).grid(row=1, column=0, padx=24, pady=(0, 18))
        self.progress = ctk.CTkProgressBar(self.window, mode="indeterminate")
        self.progress.grid(row=2, column=0, padx=45, pady=(0, 22), sticky="ew")
        self.progress.start()
        button(self.window, "Dialog schließen", self.close).grid(row=3, column=0)

        threading.Thread(
            target=self._analyze,
            args=(job_id, filepath, source_cleanup),
            name="Rechnungshelfer-PDF-Import",
            daemon=True,
        ).start()
        self.parent.after(100, self._poll_result)

    def _analyze(self, job_id, filepath, source_cleanup=None):
        try:
            analysis = self.controller.analyze_pdf(filepath)
            self._results.put((job_id, "result", analysis))
        except Exception as exc:
            self._results.put((job_id, "error", str(exc)))
        finally:
            if source_cleanup is not None:
                try:
                    source_cleanup()
                except Exception:
                    pass

    def _poll_result(self):
        if self.window is None or not self.window.winfo_exists():
            return
        try:
            job_id, kind, value = self._results.get_nowait()
        except queue.Empty:
            self.parent.after(100, self._poll_result)
            return
        if job_id != self._job_id:
            self.parent.after(0, self._poll_result)
            return

        if kind == "error":
            self.close()
            messagebox.showerror("PDF-Import", value, parent=self.parent)
            return

        self._analysis = value
        if value.settlement_draft is None:
            if not value.draft.errors:
                try:
                    if getattr(value, "grain_credit_note", None) is not None:
                        self._grain_credit_note = (
                            self.controller.create_grain_credit_note_from_pdf_analysis(
                                value
                            )
                        )
                    else:
                        self._import = (
                            self.controller.create_invoice_from_pdf_analysis(value)
                        )
                except Exception as exc:
                    self.close()
                    messagebox.showerror("PDF-Import", str(exc), parent=self.parent)
                    return
        self._show_result()

    def _show_result(self):
        if self.progress is not None:
            self.progress.stop()
            self.progress = None
        for widget in self.window.winfo_children():
            widget.destroy()

        analysis = self._analysis
        extraction = analysis.extraction
        self.window.title("PDF-Import prüfen")
        self.window.geometry("920x720")
        self.window.resizable(True, True)
        self.window.grid_rowconfigure(3, weight=1)
        self.window.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.window,
            text="PDF-Import prüfen",
            font=FONT_SECTION,
            text_color=TEXT,
        ).grid(row=0, column=0, padx=24, pady=(20, 6), sticky="w")

        method_lines = [
            f"Seite {page.page_number}: {page.method.value}"
            for page in extraction.pages
        ]
        summary = (
            f"Datei: {extraction.source_file.name}\n"
            f"Seiten: {extraction.page_count}\n"
            + "\n".join(method_lines)
        )
        ctk.CTkLabel(
            self.window,
            text=summary,
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, padx=24, pady=(0, 10), sticky="ew")

        status_messages = [*extraction.warnings, *extraction.errors]
        if analysis.settlement_draft is None:
            status_messages.extend(analysis.draft.warnings)
            status_messages.extend(
                f"BLOCKIERT: {error}" for error in analysis.draft.errors
            )
        detected = len(analysis.draft.fields)
        status = [f"Erkannte Formularfelder: {detected}"]
        if getattr(analysis, "grain_credit_note", None) is not None:
            status.append("Belegtyp: Getreidegutschrift")
        if analysis.settlement_draft is not None:
            status = format_settlement_draft(analysis.settlement_draft)
        elif analysis.draft.embedded_invoice_data is not None:
            item_count = len(analysis.draft.embedded_invoice_data.get("items", []))
            status.append(f"Vollständig eingebettete Positionen: {item_count}")
        elif analysis.draft.items:
            status.append(f"Erkannte Positionen: {len(analysis.draft.items)}")
        if analysis.settlement_draft is None:
            status.extend(
                format_detected_fields(
                    analysis.draft.fields,
                    analysis.draft.document_type,
                )
            )
        status.extend(f"• {message}" for message in status_messages)
        status_box = ctk.CTkTextbox(
            self.window,
            height=120,
            font=FONT_SMALL,
            wrap="word",
        )
        status_box.grid(row=2, column=0, padx=24, pady=(0, 10), sticky="ew")
        self._set_text(status_box, "\n".join(status))

        self.text_box = ctk.CTkTextbox(
            self.window,
            font=("Consolas", 13),
            wrap="word",
        )
        self.text_box.grid(row=3, column=0, padx=24, pady=(0, 14), sticky="nsew")
        self._set_text(
            self.text_box,
            extraction.full_text or "Kein Text konnte extrahiert werden.",
        )

        footer = ctk.CTkFrame(self.window, fg_color="transparent")
        footer.grid(row=4, column=0, padx=24, pady=(0, 20), sticky="ew")
        footer.grid_columnconfigure((0, 1, 2), weight=1)
        button(footer, "Text kopieren", self._copy_text).grid(
            row=0, column=0, padx=(0, 8), sticky="ew"
        )
        apply_button = button(
            footer,
            (
                "Abrechnung prüfen"
                if analysis.settlement_draft is not None
                else "In Formular übernehmen"
            ),
            (
                self._open_settlement_review
                if analysis.settlement_draft is not None
                else self._apply_to_form
            ),
            primary=True,
        )
        apply_button.grid(row=0, column=1, padx=8, sticky="ew")
        if (
            analysis.settlement_draft is None
            and (
                analysis.draft.errors
                or (
                    not analysis.draft.fields
                    and not analysis.draft.items
                    and analysis.draft.embedded_invoice_data is None
                )
            )
        ):
            apply_button.configure(state="disabled")
        button(footer, "Schließen", self.close).grid(
            row=0, column=2, padx=(8, 0), sticky="ew"
        )

    @staticmethod
    def _set_text(widget, value):
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _copy_text(self):
        text = self._analysis.extraction.full_text
        if not text:
            return
        try:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(text)
            self.parent.update_idletasks()
        except Exception as exc:
            messagebox.showerror(
                "PDF-Import",
                f"Text konnte nicht kopiert werden: {exc}",
                parent=self.window,
            )

    def _apply_to_form(self):
        if self._import is None and self._grain_credit_note is None:
            return
        if not messagebox.askyesno(
            "PDF-Daten übernehmen",
            "Die aktuell im Formular sichtbaren, noch nicht gespeicherten Eingaben "
            "werden ersetzt.\n\nDie importierten Daten werden nicht automatisch "
            "gespeichert. Fortfahren?",
            parent=self.window,
        ):
            return
        invoice = self._import.invoice if self._import is not None else None
        grain_credit_note = self._grain_credit_note
        self.close()
        if grain_credit_note is not None:
            self.on_grain_credit_note_loaded(grain_credit_note)
        else:
            self.on_invoice_loaded(invoice)

    def _open_settlement_review(self):
        if self._analysis is None or self._analysis.settlement_draft is None:
            return
        self._settlement_review_dialog = SettlementReviewDialog(
            self.window,
            self.controller,
            self._analysis.settlement_draft,
            self._open_grain_credit_note,
        )
        self._settlement_review_dialog.open()

    def _open_grain_credit_note(self, credit_note):
        self.close()
        self.on_grain_credit_note_loaded(credit_note)

    def close(self):
        if self.window is not None:
            try:
                if self.progress is not None:
                    self.progress.stop()
                self.window.destroy()
            finally:
                self.window = None
                self.progress = None


__all__ = [
    "PdfImportDialog",
    "format_detected_fields",
    "format_settlement_draft",
]
