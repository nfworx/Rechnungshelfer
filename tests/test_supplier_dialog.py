import unittest
from unittest.mock import Mock, patch

from rechnungshelfer.domain.business_partner import BusinessPartnerRole
from rechnungshelfer.gui.business_partner_dialog import (
    BusinessPartnerEditDialog,
    BusinessPartnerListDialog,
    new_business_partner_profile,
)


class BusinessPartnerDialogTests(unittest.TestCase):
    def test_new_profile_uses_context_role_and_empty_master_data(self):
        profile = new_business_partner_profile(BusinessPartnerRole.SUPPLIER)

        self.assertEqual(profile.roles, frozenset({BusinessPartnerRole.SUPPLIER}))
        self.assertEqual(profile.name, "")
        self.assertEqual(profile.payment.iban, "")

    def test_partner_is_saved_with_selected_roles_and_returned(self):
        profile = new_business_partner_profile(BusinessPartnerRole.CUSTOMER)
        profile.buyer.name = "Musterhof"
        profile.buyer.customer_number = "0042"
        dialog = BusinessPartnerEditDialog.__new__(BusinessPartnerEditDialog)
        dialog.profile = profile
        dialog.controller = Mock()
        dialog.on_saved = Mock()
        dialog.close = Mock()
        dialog.window = None
        dialog.customer_role = Mock(get=Mock(return_value=True))
        dialog.supplier_role = Mock(get=Mock(return_value=True))

        dialog.save()

        dialog.controller.save_business_partner.assert_called_once_with(profile)
        saved_profile = dialog.on_saved.call_args.args[0]
        self.assertIsNot(saved_profile, profile)
        self.assertEqual(saved_profile.partner_number, "0042")
        self.assertEqual(
            saved_profile.roles,
            frozenset(
                {BusinessPartnerRole.CUSTOMER, BusinessPartnerRole.SUPPLIER}
            ),
        )
        dialog.close.assert_called_once_with()

    def test_context_selection_rejects_missing_role(self):
        profile = new_business_partner_profile(BusinessPartnerRole.CUSTOMER)
        dialog = BusinessPartnerListDialog.__new__(BusinessPartnerListDialog)
        dialog.required_role = BusinessPartnerRole.SUPPLIER
        dialog.on_selected = Mock()
        dialog.window = None

        with patch(
            "rechnungshelfer.gui.business_partner_dialog.messagebox.showwarning"
        ) as warning:
            dialog.load(profile)

        warning.assert_called_once()
        dialog.on_selected.assert_not_called()


if __name__ == "__main__":
    unittest.main()
