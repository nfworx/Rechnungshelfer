import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from rechnungshelfer.repositories.migrations import DatabaseMigrationError


class MainStartupTests(unittest.TestCase):
    def test_migration_error_is_shown_without_starting_main_window(self):
        root = MagicMock()
        error = DatabaseMigrationError(
            "technical details",
            user_message=(
                "Geschäftspartnernummer 0001 ist mehrfach mit "
                "unterschiedlichen Stammdaten belegt."
            ),
            backup_path=Path("C:/data/invoices.backup.db"),
        )

        with (
            patch.object(main, "cleanup_stale_temp_reports"),
            patch.object(main.ctk, "set_appearance_mode"),
            patch.object(main.ctk, "set_default_color_theme"),
            patch.object(main.ctk, "CTk", return_value=root),
            patch.object(main, "InvoiceController", side_effect=error),
            patch.object(main, "InvoiceGUI") as gui,
            patch.object(main.messagebox, "showerror") as showerror,
        ):
            result = main.main()

        self.assertEqual(result, 1)
        root.withdraw.assert_called_once_with()
        root.destroy.assert_called_once_with()
        gui.assert_not_called()
        message = showerror.call_args.args[1]
        self.assertIn("Geschäftspartnernummer 0001", message)
        self.assertIn("Die Datenbank wurde nicht verändert.", message)
        self.assertIn("invoices.backup.db", message)


if __name__ == "__main__":
    unittest.main()
