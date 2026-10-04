# gui_ctk/main_window.py

import customtkinter as ctk
from tkinter import filedialog, messagebox
from copy import deepcopy
import queue
import sys
import threading

from app_info import APP_NAME, APP_VERSION
from gui_ctk.styles import *
from gui_ctk.components import button, clear_frame
from gui_ctk.party_card import PartyCard
from gui_ctk.item_table import ItemTable
from gui_ctk.totals_card import TotalsCard
from gui_ctk.show_seller_dialog import SellerDialog
from gui_ctk.invoice_load_dialog import InvoiceLoadDialog
from gui_ctk.customer_load_dialog import CustomerLoadDialog
from gui_ctk.supplier_load_dialog import SupplierLoadDialog
from gui_ctk.test_document_dialog import TestDocumentDialog
from gui_ctk.update_dialog import UpdateDialog
from gui_ctk.buffered_form import BufferedFormHost
from services.validation_service import ExportValidationError
from services.kosit_validation_service import show_html_report
from services.update_service import check_for_application_update
from models import DocumentType

class InvoiceGUI:
    def __init__(self, root, controller, on_ready=None):
        self.root = root
        self.controller = controller
        self.on_ready = on_ready

        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1600x900")
        self.root.configure(fg_color=APP_BG)

        self.invoice = self.controller.create_empty_invoice()

        self.field_entries = {}

        self.item_table = None
        self.totals_card = None
        self.document_type_menu = None
        self.party_list_button = None
        self.master_data_button = None
        self.save_button = None
        self.load_button = None
        self.update_dialog = UpdateDialog(self.root, on_update_started=self._shutdown_for_update)
        self._startup_update_results = queue.SimpleQueue()
        self._startup_update_check_started = False

        self._build_layout()

        self.root.after(100, self._do_startup_tasks)

    def _do_startup_tasks(self):
        self.controller.migrate_customers_from_invoices_if_empty()
        self.load_latest_invoice()
        if self.on_ready:
            self.on_ready()
        if getattr(sys, "frozen", False):
            self.root.after(1000, self._start_startup_update_check)

    def _start_startup_update_check(self):
        if self._startup_update_check_started:
            return
        self._startup_update_check_started = True

        def worker():
            try:
                self._startup_update_results.put(("result", check_for_application_update()))
            except Exception as exc:
                # Startpruefungen bleiben bei Netzwerkfehlern bewusst still.
                self._startup_update_results.put(("error", str(exc)))

        threading.Thread(
            target=worker,
            name="Rechnungshelfer-Startupdatecheck",
            daemon=True,
        ).start()
        self.root.after(100, self._poll_startup_update_check)

    def _poll_startup_update_check(self):
        try:
            kind, value = self._startup_update_results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_startup_update_check)
            return
        if kind == "result" and value is not None:
            self.update_dialog.open(initial_update=value)

    # ============================
    # Layout
    # ============================
    def _build_layout(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        self._build_body()

    def _build_body(self):
        self.body = ctk.CTkFrame(self.root, fg_color=APP_BG, corner_radius=0)
        self.body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))

        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=0)
        self.body.grid_rowconfigure(1, weight=1)

        self._build_top_toolbar()
        self._build_action_bar()
        self._build_content_area()

    def _build_top_toolbar(self):
        toolbar = ctk.CTkFrame(self.body, fg_color=APP_BG, corner_radius=0)
        toolbar.grid(row=0, column=0, sticky="w", pady=(14, 14))

        button(toolbar, "XML einlesen", self.load_xml).grid(
            row=0,
            column=0,
            padx=(0, 10),
        )

        self.party_list_button = button(toolbar, "Kundenliste", self.show_party_list)
        self.party_list_button.grid(
            row=0,
            column=1,
            padx=(0, 10),
        )

        self.master_data_button = button(toolbar, "Verkäufer", self.show_seller)
        self.master_data_button.grid(
            row=0,
            column=2,
            padx=(0, 10),
        )

        button(toolbar, "Testbeleg laden", self.load_test_document).grid(
            row=0,
            column=3,
            padx=(0, 10),
        )

        self.document_type_menu = ctk.CTkOptionMenu(
            toolbar,
            values=[item.label for item in DocumentType],
            command=self._on_document_type_selected,
            width=285,
        )
        self.document_type_menu.grid(row=0, column=4)

    def _build_action_bar(self):
        action_bar = ctk.CTkFrame(self.body, fg_color=APP_BG, corner_radius=0)
        action_bar.grid(row=0, column=1, sticky="e", pady=(14, 14))

        self.save_button = button(action_bar, "Rechnung speichern", self.save_invoice)
        self.save_button.grid(
            row=0,
            column=0,
            padx=(0, 10),
        )

        self.load_button = button(action_bar, "Rechnung laden", self.load_invoice_from_list)
        self.load_button.grid(
            row=0,
            column=1,
            padx=(0, 10),
        )

        button(action_bar, "Formular löschen", self.clear_form).grid(
            row=0,
            column=2,
            padx=(0, 10),
        )

        button(action_bar, "Updates", self.show_updates).grid(row=0, column=3)

    def _build_content_area(self):
        self.form_host = BufferedFormHost(self.body)
        self.form_host.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="nsew",
        )

    def _use_form_surface(self, surface):
        self.top_grid = surface.top_grid
        self.buyer_area = surface.buyer_area
        self.delivery_area = surface.delivery_area
        self.info_area = surface.info_area
        self.items_area = surface.items_area
        self.totals_area = surface.totals_area

    def _payment_fields_in_invoice_info(self):
        return ["payment_terms"]

    # ============================
    # Render
    # ============================
    def show_form(self):
        old_surface = self.form_host.active_surface
        old_field_entries = self.field_entries
        old_item_table = self.item_table
        old_totals_card = self.totals_card

        new_surface = self.form_host.begin_swap()
        self._use_form_surface(new_surface)
        self.field_entries = {}
        self.item_table = None
        self.totals_card = None

        try:
            self._render_top_cards()
            self._render_totals()
            self._render_items()
            self._refresh_document_labels()
            self.form_host.commit_swap()
        except Exception:
            self.form_host.cancel_swap()
            if old_surface is not None:
                self._use_form_surface(old_surface)
            self.field_entries = old_field_entries
            self.item_table = old_item_table
            self.totals_card = old_totals_card
            raise

    def _render_top_cards(self):
        if self.invoice.is_self_billed:
            PartyCard(
                self.buyer_area,
                "Lieferant",
                self.invoice.seller,
                on_change=self._on_field_change,
                field_entries=self.field_entries,
                exclude_fields=["country", "buyer_reference"],
                extra_fields=[
                    (
                        self.invoice.payment,
                        ["iban", "bic", "account_holder"],
                    )
                ],
            ).render().pack(fill="both", expand=True)
        else:
            PartyCard(
                self.buyer_area,
                "Kunde",
                self.invoice.buyer,
                on_change=self._on_field_change,
                on_delivery_toggle=self._on_delivery_toggle,
                delivery_checked=self.invoice.buyer.use_invoice_address_as_delivery,
                field_entries=self.field_entries,
                exclude_fields=["country", "phone", "vat", "tax_number", "registry_number"],
                label_overrides={"leitweg_id": "Leitweg-ID"},
                controller=self.controller,
                on_customer_select=self._on_customer_selected,
            ).render().pack(fill="both", expand=True)

        self._render_delivery_card()

        PartyCard(
            self.info_area,
            "Gutschriftsdaten" if self.invoice.is_self_billed else "Rechnungsdaten",
            self.invoice.info,
            on_change=self._on_field_change,
            field_entries=self.field_entries,
            extra_fields=[
                (
                    self.invoice.payment,
                    self._payment_fields_in_invoice_info(),
                )
            ],
            exclude_fields=[
                "customization_id",
                "profile_id",
                "currency",
                "invoice_type_code",
            ],
            label_overrides={
                "invoice_number": "Gutschriftnummer",
                "invoice_date": "Ausstellungsdatum",
                "payment_due_date": "Auszahlungsdatum",
                "payment_terms": "Auszahlungsbedingungen",
            } if self.invoice.is_self_billed else {},
        ).render().pack(fill="both", expand=True)

    def _render_delivery_card(self):
        clear_frame(self.delivery_area)

        for key in list(self.field_entries.keys()):
            if key[0] == id(self.invoice.delivery):
                del self.field_entries[key]

        if self.invoice.is_self_billed:
            PartyCard(
                self.delivery_area,
                "Käufer / Belegersteller (über „Eigener Betrieb“ bearbeiten)",
                self.invoice.buyer,
                disabled=True,
                field_entries=self.field_entries,
                exclude_fields=["country", "customer_number", "use_invoice_address_as_delivery"],
                label_overrides={"leitweg_id": "Käuferreferenz (BT-10)"},
            ).render().pack(fill="both", expand=True)
        else:
            PartyCard(
                self.delivery_area,
                "Leistungsempfänger",
                self.invoice.delivery,
                on_change=self._on_field_change,
                disabled=self.invoice.buyer.use_invoice_address_as_delivery,
                field_entries=self.field_entries,
                exclude_fields=[
                    "country",
                ],
            ).render().pack(fill="both", expand=True)

    def _render_items(self):
        self.item_table = ItemTable(
            self.items_area,
            self.invoice,
            on_change=self.refresh_totals,
        )
        self.item_table.render()

    def _render_totals(self):
        self.totals_card = TotalsCard(
            self.totals_area,
            self.invoice,
            on_pdf=self.generate_pdf,
            on_xml=self.generate_xml,
            can_export_pdf=self.can_export_pdf,
            can_export_xml=self.can_export_xml,
            pdf_export_hint=self.pdf_export_hint,
            xml_export_hint=self.xml_export_hint,
        )
        self.totals_card.render()

    # ============================
    # Events
    # ============================
    def _on_field_change(self, obj, attr, value):
        self.refresh_totals()

    def _on_document_type_selected(self, label):
        selected = next(
            document_type for document_type in DocumentType
            if document_type.label == label
        )
        if selected is self.invoice.document_type:
            return

        if not messagebox.askyesno(
            "Belegtyp wechseln",
            "Beim Wechsel des Belegtyps wird ein neues leeres Formular angelegt.\n\n"
            "Nicht gespeicherte Eingaben gehen verloren. Fortfahren?",
        ):
            self.document_type_menu.set(self.invoice.document_type.label)
            return

        self.invoice = self.controller.create_empty_invoice(selected)
        self.show_form()

    def _refresh_document_labels(self):
        document_name = "Gutschrift" if self.invoice.is_self_billed else "Rechnung"
        self.root.title(f"{APP_NAME} {APP_VERSION} - {document_name}")
        if self.document_type_menu:
            self.document_type_menu.set(self.invoice.document_type.label)
        if self.party_list_button:
            self.party_list_button.configure(
                text="Lieferantenliste" if self.invoice.is_self_billed else "Kundenliste"
            )
        if self.master_data_button:
            self.master_data_button.configure(text="Eigener Betrieb")
        if self.save_button:
            self.save_button.configure(text=f"{document_name} speichern")
        if self.load_button:
            self.load_button.configure(text="Beleg laden")

    def _on_delivery_toggle(self, checked):
        self.invoice.buyer.use_invoice_address_as_delivery = bool(checked)

        if checked:
            buyer = self.invoice.buyer
            delivery = self.invoice.delivery

            delivery.name = buyer.name
            delivery.street = buyer.street
            delivery.postcode = buyer.postcode
            delivery.city = buyer.city
            delivery.country = buyer.country
            delivery.update_required_fields(buyer)
        else:
            self.invoice.delivery.update_required_fields(self.invoice.buyer)

        self._render_delivery_card()
        self.refresh_totals()

    def refresh_totals(self):
        if self.totals_card:
            self.totals_card.refresh()

    # ============================
    # Actions
    # ============================
    def load_latest_invoice(self):
        invoice = self.controller.load_latest_invoice()

        if invoice is None:
            self.invoice = self.controller.create_empty_invoice()
        else:
            self.invoice = invoice
            self.invoice.calculate(force=True)

        self.show_form()

    def save_invoice(self):
        invoice_number = self.invoice.info.invoice_number

        if not invoice_number or not str(invoice_number).strip():
            messagebox.showerror("Fehler", "Belegnummer fehlt.")
            return

        invoice_number = str(invoice_number).strip()

        try:
            exists = self.controller.invoice_exists(invoice_number)

            if exists:
                overwrite = messagebox.askyesno(
                    "Beleg überschreiben",
                    f"Beleg {invoice_number} existiert bereits.\n\n"
                    "Soll sie überschrieben werden?",
                )

                if not overwrite:
                    return

            self.controller.save_invoice(self.invoice)

            messagebox.showinfo(
                "Gespeichert",
                f"{self.invoice.document_type.label} {invoice_number} wurde gespeichert.",
            )

        except ValueError as e:
            msg = str(e)

            if msg.startswith("CUSTOMER_DUPLICATE_FOUND"):
                duplicates = msg.replace("CUSTOMER_DUPLICATE_FOUND", "").strip()

                ok = messagebox.askyesno(
                    "Möglicher doppelter Kunde",
                    "Es wurde ein möglicher doppelter Kunde gefunden:\n\n"
                    f"{duplicates}\n\n"
                    "Trotzdem speichern?"
                )

                if ok:
                    try:
                        self.controller.save_invoice(
                            self.invoice,
                            allow_customer_duplicate=True,
                        )
                        messagebox.showinfo("Gespeichert", "Beleg wurde gespeichert.")
                    except Exception as e2:
                        messagebox.showerror("Fehler", str(e2))

                return

            messagebox.showerror("Fehler", msg)

        except Exception as e:
            messagebox.showerror(
                "Fehler",
                f"Beleg konnte nicht gespeichert werden:\n{e}",
            )

    def clear_form(self):
        self.invoice = self.controller.create_empty_invoice(self.invoice.document_type)
        self.show_form()

    def show_updates(self):
        self.update_dialog.open()

    def _shutdown_for_update(self):
        self.controller.close()
        self.root.destroy()

    def generate_pdf(self):
        fp = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Dateien", "*.pdf")],
        )

        if not fp:
            return

        try:
            self.controller.generate_pdf(self.invoice, fp)
            messagebox.showinfo("Export", "PDF wurde erstellt.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def generate_xml(self):
        fp = filedialog.asksaveasfilename(
            defaultextension=".xml",
            filetypes=[("XML Dateien", "*.xml")],
        )

        if not fp:
            return

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

        bar = ctk.CTkProgressBar(
            progress,
            mode="indeterminate"
        )
        bar.pack(fill="x", padx=30)
        bar.start()

        def worker():
            try:
                self.controller.generate_xml(self.invoice, fp)
                validation_result = self.controller.last_validation_result
                
                self.root.after(
                    0,
                    lambda: self._finish_xml_export_success(
                        progress,
                        validation_result,
                    )
                )

            except ExportValidationError as e:
                message = str(e)
                details = e.details
                report_html = e.report_html

                self.root.after(
                    0,
                    lambda message=message, details=details, report_html=report_html: (
                        self._finish_xml_export_validation_error(
                            progress,
                            message,
                            details,
                            report_html,
                        )
                    )
                )

            except ValueError as e:
                message = str(e)

                self.root.after(
                    0,
                    lambda message=message: self._finish_xml_export_warning(
                        progress,
                        message,
                    )
                )

            except Exception as e:
                message = str(e)

                self.root.after(
                    0,
                    lambda message=message: self._finish_xml_export_error(
                        progress,
                        message,
                    )
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def load_xml(self):
        fp = filedialog.askopenfilename(filetypes=[("XML Dateien", "*.xml")])

        if not fp:
            return

        try:
            self.invoice = self.controller.load_from_xml(fp)
            self.show_form()
        except (ValueError, RuntimeError) as e:
            messagebox.showerror("Fehler", str(e))

    def load_test_document(self):
        dialog = TestDocumentDialog(
            self.root,
            on_document_selected=self._on_test_document_selected,
        )
        dialog.open()

    def _on_test_document_selected(self, invoice):
        self.invoice = invoice
        self.invoice.calculate(force=True)
        self.show_form()

    def load_invoice_from_list(self):
        dialog = InvoiceLoadDialog(
            self.root,
            self.controller,
            on_invoice_loaded=self._on_invoice_loaded,
        )
        dialog.open()

    def _on_invoice_loaded(self, invoice):
        self.invoice = invoice
        self.invoice.calculate(force=True)
        self.show_form()

    def _on_customer_selected(self, buyer):
        self.invoice.buyer = deepcopy(buyer)

        self.invoice.delivery.update_required_fields(self.invoice.buyer)

        if self.invoice.buyer.use_invoice_address_as_delivery:
            self.invoice.delivery.name = self.invoice.buyer.name
            self.invoice.delivery.street = self.invoice.buyer.street
            self.invoice.delivery.postcode = self.invoice.buyer.postcode
            self.invoice.delivery.city = self.invoice.buyer.city
            self.invoice.delivery.country = self.invoice.buyer.country

        self.show_form()
        self.refresh_totals()

    def _on_supplier_selected(self, seller, payment):
        self.invoice.seller = deepcopy(seller)
        self.invoice.payment = deepcopy(payment)
        self.invoice.seller.required_fields = [
            "name", "street", "postcode", "city", "country", "email"
        ]
        self.invoice.payment.required_fields = [
            "iban", "bic", "account_holder", "payment_means_code"
        ]
        self.show_form()

    def show_party_list(self):
        if self.invoice.is_self_billed:
            dialog = SupplierLoadDialog(
                self.root,
                self.controller,
                on_supplier_selected=self._on_supplier_selected,
            )
            dialog.open()
        else:
            self.show_customer_list()

    def show_customer_list(self):
        dialog = CustomerLoadDialog(
            self.root,
            self.controller,
            on_customer_selected=self._on_customer_selected,
        )
        dialog.open()

    def show_seller(self):
        dialog_invoice = self.invoice
        on_saved = None
        if self.invoice.is_self_billed:
            dialog_invoice = self.controller.create_empty_invoice(DocumentType.INVOICE)
            on_saved = self._reload_own_company
        dialog = SellerDialog(
            self.root,
            self.controller,
            dialog_invoice,
            on_saved=on_saved,
        )
        dialog.open()

    def _reload_own_company(self):
        self.invoice.buyer = self.controller.load_own_company_buyer()
        self.invoice.buyer.use_invoice_address_as_delivery = True
        self.show_form()

    def can_export_pdf(self):
        try:
            return self.controller.check_pdf_required_fields(self.invoice)
        except Exception:
            return False

    def can_export_xml(self):
        try:
            return self.controller.check_xml_required_fields(self.invoice)
        except Exception:
            return False

    def pdf_export_hint(self):
        return self._export_hint(for_xml=False, export_name="PDF")

    def xml_export_hint(self):
        return self._export_hint(for_xml=True, export_name="XML")

    def _export_hint(self, for_xml, export_name):
        try:
            missing = self.controller.get_missing_required_fields(
                self.invoice,
                for_xml=for_xml,
            )
            if not missing:
                return ""
            return self.controller.format_missing_fields(missing, export_name)
        except Exception:
            return f"{export_name}-Export ist derzeit nicht möglich."
        
    def _finish_xml_export_success(
        self,
        progress,
        validation_result=None,
    ):
        self._close_progress(progress)

        if (
            validation_result
            and validation_result.report_html
        ):
            if messagebox.askyesno(
                "Export",
                "XML wurde erstellt.\n\nPrüfbericht anzeigen?"
            ):
                show_html_report(
                    validation_result.report_html
                )
        else:
            messagebox.showinfo(
                "Export",
                "XML wurde erstellt."
            )


    def _finish_xml_export_warning(self, progress, message):
        self._close_progress(progress)
        messagebox.showwarning("Export abgebrochen", message)

    def _close_progress(self, progress):
        try:
            if progress.winfo_exists():
                progress.destroy()
        except Exception:
            pass

    def _finish_xml_export_error(self, progress, message):
        self._close_progress(progress)
        messagebox.showerror("Fehler", message)

    def _finish_xml_export_validation_error(self, progress, message, details, report_html):
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

        def show_report():
            self._show_validation_report(report_html)

        def export_log():
            fp = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Textdatei", "*.txt")],
                initialfile="validation-error-log.txt",
            )

            if not fp:
                return

            with open(fp, "w", encoding="utf-8") as f:
                f.write(details)

            messagebox.showinfo("Fehlerlog", "Fehlerlog wurde exportiert.")

        ctk.CTkButton(
            button_frame,
            text="Fehlerlog exportieren",
            command=export_log,
        ).pack(side="left")

        ctk.CTkButton(
            button_frame,
            text="Prüfbericht anzeigen",
            command=show_report,
        ).pack(side="left", padx=(10, 0))

        ctk.CTkButton(
            button_frame,
            text="OK",
            command=dialog.destroy,
        ).pack(side="right")

    def _show_validation_report(self, html_content):
        if not html_content:
            messagebox.showinfo(
                "Prüfbericht",
                "Kein Prüfbericht verfügbar.",
            )
            return

        show_html_report(html_content)
