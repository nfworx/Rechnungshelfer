import unittest

from unittest.mock import Mock

from rechnungshelfer.gui.date_fields import (
    apply_date_selection,
    attach_date_validation,
    attach_calendar_double_click,
    calculate_datepicker_position,
)


class DatepickerPositionTests(unittest.TestCase):
    def test_dialog_is_right_aligned_below_button(self):
        position = calculate_datepicker_position(
            anchor_x=900,
            anchor_y=200,
            anchor_width=30,
            anchor_height=24,
            screen_width=1920,
            screen_height=1080,
        )
        self.assertEqual(position, (630, 230))

    def test_dialog_opens_above_button_when_bottom_space_is_insufficient(self):
        position = calculate_datepicker_position(
            anchor_x=900,
            anchor_y=900,
            anchor_width=30,
            anchor_height=24,
            screen_width=1920,
            screen_height=1080,
        )
        self.assertEqual(position, (630, 574))

    def test_dialog_is_clamped_to_top_left_of_small_screen(self):
        position = calculate_datepicker_position(
            anchor_x=5,
            anchor_y=5,
            anchor_width=30,
            anchor_height=24,
            screen_width=250,
            screen_height=250,
        )
        self.assertEqual(position, (0, 0))


class DatepickerInteractionTests(unittest.TestCase):
    def test_manual_date_is_normalized_and_updates_bound_model_callback(self):
        entry = Mock()
        entry.get.return_value = "1.2.26"
        on_valid = Mock()
        validate = attach_date_validation(
            entry,
            "Rechnungsdatum",
            on_valid=on_valid,
        )

        self.assertTrue(validate())
        entry.delete.assert_called_once_with(0, "end")
        entry.insert.assert_called_once_with(0, "01.02.2026")
        entry.configure.assert_called_once_with(border_color="green")
        on_valid.assert_called_once_with("01.02.2026")

    def test_iso_date_from_import_is_normalized_on_focus_change(self):
        entry = Mock()
        entry.get.return_value = "2026-02-01"
        on_valid = Mock()
        validate = attach_date_validation(entry, "Datum", on_valid=on_valid)

        self.assertTrue(validate())

        entry.insert.assert_called_once_with(0, "01.02.2026")
        on_valid.assert_called_once_with("01.02.2026")

    def test_invalid_manual_date_stays_unchanged_and_does_not_update_model(self):
        entry = Mock()
        entry.get.return_value = "31.02.2026"
        on_valid = Mock()
        validate = attach_date_validation(entry, "Rechnungsdatum", on_valid=on_valid)

        self.assertFalse(validate())

        entry.delete.assert_not_called()
        entry.insert.assert_not_called()
        entry.configure.assert_called_once_with(border_color="red")
        on_valid.assert_not_called()

    def test_optional_empty_delivery_date_updates_model_with_empty_value(self):
        entry = Mock()
        entry.get.return_value = ""
        on_valid = Mock()
        validate = attach_date_validation(
            entry,
            "Lieferdatum",
            required=False,
            on_valid=on_valid,
        )

        self.assertTrue(validate())

        entry.insert.assert_called_once_with(0, "")
        on_valid.assert_called_once_with("")

    def test_selected_date_updates_entry_and_bound_model_callback(self):
        entry = Mock()
        on_selected = Mock()

        selected = apply_date_selection(
            entry,
            "2026-10-09",
            "Ausstellungsdatum",
            on_selected,
        )

        self.assertEqual(selected, "09.10.2026")
        entry.delete.assert_called_once_with(0, "end")
        entry.insert.assert_called_once_with(0, "09.10.2026")
        entry.configure.assert_called_once_with(border_color="green")
        on_selected.assert_called_once_with("09.10.2026")

    def test_selected_date_remains_compatible_without_model_callback(self):
        entry = Mock()

        selected = apply_date_selection(entry, "09.10.2026")

        self.assertEqual(selected, "09.10.2026")
        entry.insert.assert_called_once_with(0, "09.10.2026")

    def test_double_click_is_bound_to_internal_calendar_days(self):
        calendar = Mock()
        first_day = Mock()
        second_day = Mock()
        calendar._calendar = [[[first_day], [second_day]]]
        callback = Mock()
        scheduler = Mock()

        handler = attach_calendar_double_click(
            calendar,
            callback,
            scheduler=scheduler,
        )
        handler()

        for day in (first_day, second_day):
            day.bind.assert_called_once_with(
                "<Double-Button-1>",
                handler,
                add="+",
            )
        scheduler.assert_called_once_with(callback)
        callback.assert_not_called()

    def test_double_click_supports_calendar_versions_with_internal_widget(self):
        calendar = Mock()
        calendar._calendar = Mock()
        callback = Mock()

        handler = attach_calendar_double_click(calendar, callback)

        calendar._calendar.bind.assert_called_once_with(
            "<Double-Button-1>",
            handler,
            add="+",
        )

    def test_double_click_falls_back_to_calendar_widget(self):
        calendar = Mock(spec=["bind"])
        callback = Mock()

        handler = attach_calendar_double_click(calendar, callback)
        handler()

        calendar.bind.assert_called_once_with(
            "<Double-Button-1>",
            handler,
            add="+",
        )
        callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
