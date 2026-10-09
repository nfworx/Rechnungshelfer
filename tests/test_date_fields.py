import unittest

from unittest.mock import Mock

from rechnungshelfer.gui.date_fields import (
    apply_date_selection,
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
        calendar._calendar = Mock()
        callback = Mock()
        scheduler = Mock()

        handler = attach_calendar_double_click(
            calendar,
            callback,
            scheduler=scheduler,
        )
        handler()

        calendar._calendar.bind.assert_called_once_with(
            "<Double-Button-1>",
            handler,
            add="+",
        )
        scheduler.assert_called_once_with(callback)
        callback.assert_not_called()

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
