# rechnungshelfer/gui/main_window.py

import customtkinter as ctk
from tkinter import Menu, StringVar, filedialog, messagebox
from copy import deepcopy
import queue
import sys
import threading

from app_info import APP_NAME, APP_VERSION
from .styles import *
from .components import clear_frame
from .party_card import PartyCard
from .item_table import ItemTable
from .totals_card import TotalsCard
from .show_seller_dialog import SellerDialog
from .invoice_load_dialog import InvoiceLoadDialog
from .business_partner_dialog import BusinessPartnerListDialog
from .test_document_dialog import TestDocumentDialog
from .pdf_import_dialog import PdfImportDialog
from .update_dialog import UpdateDialog
from .buffered_form import BufferedFormHost
from .export_workflow import ExportWorkflow
from .grain_settlement_view import GrainSettlementView
from rechnungshelfer.services.update_service import check_for_application_update
from rechnungshelfer.services.sample_settlement_pdf_service import (
    create_temporary_test_settlement_pdf,
    remove_temporary_test_settlement_pdf,
)
from rechnungshelfer.application.errors import CustomerDuplicateError
from rechnungshelfer.domain.business_partner import BusinessPartnerRole
from rechnungshelfer.domain.models import DocumentType

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
        self.active_workspace = "invoice"
        self.update_dialog = UpdateDialog(self.root, on_update_started=self._shutdown_for_update)
        self.pdf_import_dialog = PdfImportDialog(
            self.root,
            self.controller,
            on_invoice_loaded=self._on_invoice_loaded,
        )
        self.export_workflow = ExportWorkflow(
            self.root,
            self.controller,
            lambda: self.invoice,
        )
        self._startup_update_results = queue.SimpleQueue()
        self._startup_update_check_started = False

        self._build_layout()

        self.root.after(100, self._do_startup_tasks)

    def _do_startup_tasks(self):
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
        self.root.grid_rowconfigure(0, weight=1)

        self._build_menu_bar()
        self._build_body()

    def _build_body(self):
        self.body = ctk.CTkFrame(self.root, fg_color=APP_BG, corner_radius=0)
        self.body.grid(row=0, column=0, sticky="nsew", padx=14, pady=10)

        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        self._build_content_area()

    def _build_menu_bar(self):
        self.menu_bar = Menu(self.root)

        self.file_menu = Menu(self.menu_bar, tearoff=False)
        self.file_menu.add_command(label="Beleg laden", command=self.load_invoice_from_list)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="XML einlesen", command=self.load_xml)
        self.file_menu.add_command(label="PDF einlesen", command=self.load_pdf)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Speichern", command=self.save_invoice)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Beenden", command=self.root.destroy)
        self.menu_bar.add_cascade(label="Datei", menu=self.file_menu)

        self.document_menu = Menu(self.menu_bar, tearoff=False)
        self.workspace_variable = StringVar(
            master=self.root,
            value=self.active_workspace,
        )
        self.document_menu.add_radiobutton(
            label="Rechnung",
            value="invoice",
            variable=self.workspace_variable,
            command=self._open_invoice_workspace,
        )
        self.document_menu.add_radiobutton(
            label="Gutschrift",
            value="self_billed",
            variable=self.workspace_variable,
            command=self._open_self_billed_workspace,
        )
        self.document_menu.add_radiobutton(
            label="Getreideabrechnung",
            value="grain",
            variable=self.workspace_variable,
            command=self._open_grain_workspace,
        )
        self.document_menu.add_separator()
        self.document_menu.add_command(
            label="Formular leeren",
            command=self._clear_current_form,
        )
        self.menu_bar.add_cascade(label="Beleg", menu=self.document_menu)

        self.master_data_menu = Menu(self.menu_bar, tearoff=False)
        self.master_data_menu.add_command(
            label="Geschäftspartnerliste",
            command=self._show_current_party_list,
        )
        self.master_data_menu.add_separator()
        self.master_data_menu.add_command(
            label="Eigener Betrieb",
            command=self.show_seller,
        )
        self.menu_bar.add_cascade(label="Stammdaten", menu=self.master_data_menu)

        tools_menu = Menu(self.menu_bar, tearoff=False)
        tools_menu.add_command(label="Testbeleg laden", command=self.load_test_document)
        tools_menu.add_command(label="Updates", command=self.show_updates)
        self.menu_bar.add_cascade(label="Werkzeuge", menu=tools_menu)

        self.root.configure(menu=self.menu_bar)
        self._refresh_application_menu()

    def _build_content_area(self):
        self.form_host = BufferedFormHost(self.body)
        self.form_host.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.grain_view = GrainSettlementView(
            self.body,
            self.controller,
            on_invoice_created=self._open_grain_credit_note,
        )
        self.grain_view.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.grain_view.grid_remove()

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
        self._activate_invoice_workspace()
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
                label_overrides={
                    "supplier_number": "Geschäftspartnernummer (Lieferant/Kreditor)"
                },
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
                label_overrides={
                    "leitweg_id": "Käuferreferenz / Leitweg-ID (BT-10)",
                    "customer_number": "Geschäftspartnernummer (Kunde)",
                },
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
            on_pdf=self.export_workflow.generate_pdf,
            on_xml=self.export_workflow.generate_xml,
            can_export_pdf=self.export_workflow.can_export_pdf,
            can_export_xml=self.export_workflow.can_export_xml,
            pdf_export_hint=self.export_workflow.pdf_export_hint,
            xml_export_hint=self.export_workflow.xml_export_hint,
        )
        self.totals_card.render()

    # ============================
    # Events
    # ============================
    def _on_field_change(self, obj, attr, value):
        self.refresh_totals()

    def _open_invoice_workspace(self):
        self._open_document_workspace(DocumentType.INVOICE)

    def _open_self_billed_workspace(self):
        self._open_document_workspace(DocumentType.SELF_BILLED_INVOICE)

    def _open_document_workspace(self, document_type):
        if document_type is self.invoice.document_type:
            self._activate_invoice_workspace()
            return

        if not messagebox.askyesno(
            "Belegmaske wechseln",
            "Für diese Belegart wird ein neues leeres Formular angelegt.\n\n"
            "Nicht gespeicherte Eingaben im aktuellen Beleg gehen verloren. Fortfahren?",
        ):
            self._refresh_application_menu()
            return

        self.invoice = self.controller.create_empty_invoice(document_type)
        self.show_form()

    def _open_grain_workspace(self):
        self.active_workspace = "grain"
        self.form_host.grid_remove()
        self.grain_view.grid()
        self.root.title(f"{APP_NAME} {APP_VERSION} - Getreideabrechnung")
        self._refresh_application_menu()

    def _open_grain_credit_note(self, invoice):
        self.invoice = invoice
        self.show_form()

    def _activate_invoice_workspace(self):
        self.active_workspace = (
            "self_billed" if self.invoice.is_self_billed else "invoice"
        )
        if hasattr(self, "grain_view"):
            self.grain_view.grid_remove()
        if hasattr(self, "form_host"):
            self.form_host.grid()
        self._refresh_application_menu()

    def _refresh_application_menu(self):
        if not hasattr(self, "file_menu"):
            return
        is_grain = self.active_workspace == "grain"
        is_self_billed = self.active_workspace == "self_billed"
        document_state = "disabled" if is_grain else "normal"
        for index in (0, 2, 3, 5):
            self.file_menu.entryconfigure(index, state=document_state)
        self.file_menu.entryconfigure(
            5,
            label=(
                "Speichern"
                if is_grain
                else f"{'Gutschrift' if is_self_billed else 'Rechnung'} speichern"
            ),
        )
        self.document_menu.entryconfigure(4, state=document_state)
        self.workspace_variable.set(self.active_workspace)

    def _refresh_document_labels(self):
        document_name = "Gutschrift" if self.invoice.is_self_billed else "Rechnung"
        self.root.title(f"{APP_NAME} {APP_VERSION} - {document_name}")
        self._refresh_application_menu()

    def _on_delivery_toggle(self, checked):
        self.invoice.set_use_invoice_address_as_delivery(checked)

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

        except CustomerDuplicateError as error:
            ok = messagebox.askyesno(
                "Möglicher doppelter Kunde",
                "Es wurde ein möglicher doppelter Kunde gefunden:\n\n"
                f"{error.format_duplicates()}\n\n"
                "Trotzdem speichern?",
            )

            if ok:
                try:
                    self.controller.save_invoice(
                        self.invoice,
                        allow_customer_duplicate=True,
                    )
                    messagebox.showinfo("Gespeichert", "Beleg wurde gespeichert.")
                except Exception as retry_error:
                    messagebox.showerror("Fehler", str(retry_error))

        except ValueError as error:
            messagebox.showerror("Fehler", str(error))

        except Exception as e:
            messagebox.showerror(
                "Fehler",
                f"Beleg konnte nicht gespeichert werden:\n{e}",
            )

    def clear_form(self):
        self.invoice = self.controller.create_empty_invoice(self.invoice.document_type)
        self.show_form()

    def _clear_current_form(self):
        if self.active_workspace != "grain":
            self.clear_form()

    def show_updates(self):
        self.update_dialog.open()

    def _shutdown_for_update(self):
        self.controller.close()
        self.root.destroy()

    def load_xml(self):
        fp = filedialog.askopenfilename(filetypes=[("XML Dateien", "*.xml")])

        if not fp:
            return

        try:
            self.invoice = self.controller.load_from_xml(fp)
            self.show_form()
        except (ValueError, RuntimeError) as e:
            messagebox.showerror("Fehler", str(e))

    def load_pdf(self):
        filepath = filedialog.askopenfilename(
            parent=self.root,
            title="PDF einlesen",
            filetypes=[("PDF-Dateien", "*.pdf")],
        )
        if filepath:
            self.pdf_import_dialog.open(filepath)

    def load_test_document(self):
        dialog = TestDocumentDialog(
            self.root,
            on_document_selected=self._on_test_document_selected,
            on_ocr_test_selected=self._open_ocr_test_document,
        )
        dialog.open()

    def _on_test_document_selected(self, invoice):
        self.invoice = invoice
        self.invoice.calculate(force=True)
        self.show_form()

    def _open_ocr_test_document(self):
        try:
            filepath = create_temporary_test_settlement_pdf()
            self.pdf_import_dialog.open(
                filepath,
                source_cleanup=(
                    lambda path=filepath: remove_temporary_test_settlement_pdf(path)
                ),
            )
        except Exception as exc:
            if "filepath" in locals():
                remove_temporary_test_settlement_pdf(filepath)
            messagebox.showerror(
                "OCR-Testabrechnung",
                f"Testabrechnung konnte nicht erstellt werden: {exc}",
                parent=self.root,
            )

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
        self.invoice.replace_buyer(deepcopy(buyer))

        self.show_form()
        self.refresh_totals()

    def _on_supplier_selected(self, seller, payment):
        self.invoice.seller = deepcopy(seller)
        self.invoice.payment = deepcopy(payment)
        self.invoice.buyer.leitweg_id = (
            seller.buyer_reference or seller.supplier_number
        )
        self.invoice.seller.required_fields = [
            "name", "street", "postcode", "city", "country", "email"
        ]
        self.invoice.payment.required_fields = [
            "iban", "bic", "account_holder", "payment_means_code"
        ]
        self.show_form()

    def show_party_list(self):
        required_role = (
            BusinessPartnerRole.SUPPLIER
            if self.invoice.is_self_billed
            else BusinessPartnerRole.CUSTOMER
        )

        def select(profile):
            if required_role is BusinessPartnerRole.SUPPLIER:
                self._on_supplier_selected(profile.seller, profile.payment)
            else:
                self._on_customer_selected(profile.buyer)

        BusinessPartnerListDialog(
            self.root,
            self.controller,
            required_role=required_role,
            on_selected=select,
        ).open()

    def _show_current_party_list(self):
        if self.active_workspace == "grain":
            self.grain_view.open_supplier_list()
            return
        self.show_party_list()

    def show_seller(self):
        dialog_invoice = self.invoice
        on_saved = None
        if self.active_workspace == "grain":
            dialog_invoice = self.controller.create_empty_invoice(
                DocumentType.INVOICE
            )
            on_saved = self._reload_grain_own_company
        elif self.invoice.is_self_billed:
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

    def _reload_grain_own_company(self):
        self.grain_view.reload_own_company()

