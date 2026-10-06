import unittest

from rechnungshelfer.gui.date_fields import calculate_datepicker_position


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


if __name__ == "__main__":
    unittest.main()
