"""Editierbare Praxisvorlagen fuer Getreide-Abrechnungsregeln.

Die Werte sind bewusst keine fest verdrahteten Branchenvorgaben. Sie bilden
haeufige Abrechnungsarten und veroeffentlichte Erntebedingungen als
Startkonfiguration ab und muessen gegen den jeweiligen Vertrag geprueft werden.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .grain_form_mapper import FeatureFormValue, RuleFormValue


@dataclass(frozen=True)
class GrainRulePreset:
    label: str
    note: str
    features: tuple[FeatureFormValue, ...]
    rules: tuple[RuleFormValue, ...]

    def __post_init__(self):
        object.__setattr__(
            self,
            "rules",
            tuple(replace(rule, order=index) for index, rule in enumerate(self.rules)),
        )


def _feature(code: str, label: str, unit: str, required: bool = False):
    return FeatureFormValue(code, label, required=required, unit=unit)


def _rule(
    code: str,
    label: str,
    kind: str,
    feature: str = "",
    *,
    parameters: str,
    phase: str = "quantity_deduction",
    quantity_reference: str = "gross_quantity",
    price_reference: str = "",
    tiers: str = "",
    enabled: bool = True,
):
    return RuleFormValue(
        code=code,
        label=label,
        kind=kind,
        feature_code=feature,
        quantity_reference=quantity_reference,
        parameters=parameters,
        tiers=tiers,
        phase=phase,
        price_reference=price_reference,
        enabled=enabled,
    )


def _common_features(*extras: FeatureFormValue):
    return (
        _feature("moisture", "Feuchtigkeit", "%", True),
        _feature("dockage", "Besatz", "%", True),
        *extras,
    )


def _common_rules(*, shrink_factor: str = "1,3"):
    return (
        _rule(
            "moisture-shrink",
            "Trocknungsschwund",
            "excess_over_basis",
            "moisture",
            parameters=f"basis_value=14,5; factor={shrink_factor}",
        ),
        _rule(
            "dockage-deduction",
            "Besatzabzug",
            "excess_over_basis",
            "dockage",
            parameters="basis_value=2; factor=1",
        ),
        _rule(
            "drying-cost",
            "Trocknungskosten",
            "excess_over_basis",
            "moisture",
            parameters="basis_value=14,5; amount_per_unit=8",
            phase="price_adjustment",
            quantity_reference="",
            enabled=False,
        ),
        _rule(
            "quality-assurance-cost",
            "Qualitaetssicherung / Probenahme",
            "absolute_per_tonne",
            parameters="amount_per_tonne=0,50",
            phase="price_adjustment",
            quantity_reference="",
            enabled=False,
        ),
    )


def _quality_price_rule(
    code: str,
    label: str,
    feature: str,
    tiers: str,
):
    return _rule(
        code,
        label,
        "tiered",
        feature,
        parameters="result_kind=percentage_of_price",
        tiers=tiers,
        phase="price_adjustment",
        quantity_reference="",
        price_reference="base_price",
        enabled=False,
    )


_NOTE = (
    "Praxis-Startwerte; Grenzwerte, Faktoren und Preise vor Verwendung mit "
    "Kaufvertrag bzw. Erntebedingungen abgleichen."
)


PRESETS = {
    "wheat": GrainRulePreset(
        "Weizen",
        _NOTE,
        _common_features(
            _feature("hectolitre_weight", "Hektolitergewicht", "kg/hl"),
            _feature("protein", "Rohprotein", "%"),
            _feature("falling_number", "Fallzahl", "s"),
            _feature("sprouted", "Auswuchs", "%"),
            _feature("foreign_grain", "Fremdgetreide", "%"),
            _feature("broken_shrunken", "Bruch- und Schmachtkorn", "%"),
            _feature("ergot", "Mutterkorn", "%"),
            _feature("don", "DON", "mg/kg"),
            _feature("zea", "ZEA", "mg/kg"),
        ),
        _common_rules()
        + (
            _quality_price_rule(
                "hectolitre-price",
                "Minderpreis Hektolitergewicht",
                "hectolitre_weight",
                "..72=4 | 72..73=3 | 73..74=2 | 74..75=1 | 75..=0",
            ),
            _quality_price_rule(
                "protein-price",
                "Minderpreis Rohprotein",
                "protein",
                "..11=3 | 11..11,5=2 | 11,5..12=1 | 12..=0",
            ),
            _quality_price_rule(
                "falling-number-price",
                "Minderpreis Fallzahl",
                "falling_number",
                "..180=3 | 180..220=1 | 220..=0",
            ),
        ),
    ),
    "barley": GrainRulePreset(
        "Gerste",
        _NOTE,
        _common_features(
            _feature("hectolitre_weight", "Hektolitergewicht", "kg/hl"),
            _feature("protein", "Rohprotein", "%"),
            _feature("germination", "Keimfaehigkeit", "%"),
            _feature("whole_grain", "Vollgerstenanteil", "%"),
            _feature("premalting", "Vermalzung", "%"),
            _feature("don", "DON", "mg/kg"),
        ),
        _common_rules()
        + (
            _quality_price_rule(
                "hectolitre-price",
                "Minderpreis Hektolitergewicht",
                "hectolitre_weight",
                "..62=3 | 62..64=2 | 64..66=1 | 66..=0",
            ),
            _quality_price_rule(
                "protein-price",
                "Minderpreis Rohprotein",
                "protein",
                "..9,5=2 | 9,5..11,5=0 | 11,5..12=1 | 12..=3",
            ),
        ),
    ),
    "rye": GrainRulePreset(
        "Roggen",
        _NOTE,
        _common_features(
            _feature("hectolitre_weight", "Hektolitergewicht", "kg/hl"),
            _feature("falling_number", "Fallzahl", "s"),
            _feature("amylogram_temperature", "Amylogramm-Verkleisterung", "°C"),
            _feature("amylogram_viscosity", "Amylogramm-Maximum", "AE"),
            _feature("ergot", "Mutterkorn", "%"),
            _feature("don", "DON", "mg/kg"),
        ),
        _common_rules()
        + (
            _quality_price_rule(
                "hectolitre-price",
                "Minderpreis Hektolitergewicht",
                "hectolitre_weight",
                "..68=3 | 68..70=2 | 70..72=1 | 72..=0",
            ),
            _quality_price_rule(
                "falling-number-price",
                "Minderpreis Fallzahl",
                "falling_number",
                "..100=3 | 100..120=1 | 120..=0",
            ),
        ),
    ),
    "triticale": GrainRulePreset(
        "Triticale",
        _NOTE,
        _common_features(
            _feature("hectolitre_weight", "Hektolitergewicht", "kg/hl"),
            _feature("sprouted", "Auswuchs", "%"),
            _feature("ergot", "Mutterkorn", "%"),
            _feature("don", "DON", "mg/kg"),
        ),
        _common_rules()
        + (
            _quality_price_rule(
                "hectolitre-price",
                "Minderpreis Hektolitergewicht",
                "hectolitre_weight",
                "..66=3 | 66..68=2 | 68..70=1 | 70..=0",
            ),
        ),
    ),
    "maize": GrainRulePreset(
        "Mais",
        _NOTE,
        _common_features(
            _feature("broken_grain", "Bruchkorn", "%"),
            _feature("foreign_grain", "Fremdgetreide", "%"),
            _feature("don", "DON", "mg/kg"),
            _feature("zea", "ZEA", "mg/kg"),
            _feature("aflatoxin_b1", "Aflatoxin B1", "µg/kg"),
        ),
        _common_rules(shrink_factor="1,4"),
    ),
}


def grain_rule_preset(grain_type_code: str) -> GrainRulePreset:
    """Liefert eine vollstaendige, unveraenderliche Praxisvorlage."""

    return PRESETS.get(grain_type_code, PRESETS["wheat"])
