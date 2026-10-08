import unittest
from unittest.mock import Mock

from rechnungshelfer.domain.models import Payment, Seller
from rechnungshelfer.gui.supplier_edit_dialog import SupplierEditDialog
from rechnungshelfer.gui.supplier_load_dialog import SupplierLoadDialog


class SupplierDialogTests(unittest.TestCase):
    def test_supplier_list_closes_before_opening_creation_dialog(self):
        events = []
        dialog = SupplierLoadDialog.__new__(SupplierLoadDialog)
        dialog.on_create_supplier = lambda: events.append("create")
        dialog.close = lambda: events.append("close")

        dialog.create_supplier()

        self.assertEqual(events, ["close", "create"])

    def test_new_supplier_is_saved_and_returned_to_caller(self):
        seller = Seller(name="Musterhof", supplier_number="0042")
        payment = Payment()
        dialog = SupplierEditDialog.__new__(SupplierEditDialog)
        dialog.seller = seller
        dialog.payment = payment
        dialog.controller = Mock()
        dialog.on_saved = Mock()
        dialog.close = Mock()
        dialog.window = None

        dialog.save()

        dialog.controller.save_supplier.assert_called_once_with(seller, payment)
        saved_seller, saved_payment = dialog.on_saved.call_args.args
        self.assertIsNot(saved_seller, seller)
        self.assertIsNot(saved_payment, payment)
        self.assertEqual(saved_seller.supplier_number, "0042")
        dialog.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
