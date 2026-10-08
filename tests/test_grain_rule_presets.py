import unittest

from rechnungshelfer.gui.grain_form_mapper import build_preview_scheme
from rechnungshelfer.gui.grain_rule_presets import PRESETS, grain_rule_preset
from rechnungshelfer.gui.grain_settlement_dialogs import (
    _tiers_for_display,
    _tiers_for_storage,
)


class GrainRulePresetTests(unittest.TestCase):
    def test_every_supported_grain_type_has_a_valid_preset(self):
        for grain_type, preset in PRESETS.items():
            with self.subTest(grain_type=grain_type):
                scheme = build_preview_scheme(
                    grain_type,
                    preset.features,
                    preset.rules,
                )
                self.assertGreaterEqual(len(preset.features), 6)
                self.assertGreaterEqual(len(scheme.rules), 2)

    def test_common_rules_use_human_labels_and_are_editable(self):
        preset = grain_rule_preset("wheat")
        labels = {rule.label for rule in preset.rules}
        codes = {feature.code for feature in preset.features}

        self.assertIn("Trocknungsschwund", labels)
        self.assertIn("Besatzabzug", labels)
        self.assertIn("Trocknungskosten", labels)
        self.assertIn("moisture", codes)
        self.assertTrue(any(not rule.enabled for rule in preset.rules))

    def test_maize_uses_the_common_higher_shrink_factor(self):
        preset = grain_rule_preset("maize")
        shrink = next(rule for rule in preset.rules if rule.code == "moisture-shrink")

        self.assertIn("factor=1,4", shrink.parameters)

    def test_internal_tier_syntax_is_hidden_behind_readable_text(self):
        stored = "..72=4 | 72..73=3 | 73..=0"

        display = _tiers_for_display(stored)

        self.assertEqual(
            display,
            "unter 72: 4 | 72 bis unter 73: 3 | ab 73: 0",
        )
        self.assertEqual(_tiers_for_storage(display), stored)


if __name__ == "__main__":
    unittest.main()
