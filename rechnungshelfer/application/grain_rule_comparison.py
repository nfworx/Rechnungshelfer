"""Nicht verändernder Vergleich importierter Abzüge mit freigegebenen Regeln."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import re
import unicodedata

from rechnungshelfer.domain.grain_calculation import calculate_delivery_quantities
from rechnungshelfer.domain.grain_credit_note import (
    GrainRuleCheck,
    GrainRuleDeviation,
    GrainSchemeReference,
)
from rechnungshelfer.domain.grain_models import (
    GrainDelivery,
    GrainValidationError,
    PriceReference,
    QualityFeature,
    QualityMeasurement,
    QuantityReference,
    RuleDirection,
    RuleKind,
    RulePhase,
    RuleTier,
    SettlementRule,
    SettlementSchemeVersion,
)
from rechnungshelfer.services.format_service import parse_de


_GRAIN_NAMES = {
    "braugerste": "malting_barley",
    "futtergerste": "barley",
    "gerste": "barley",
    "weizen": "wheat",
    "hafer": "oats",
    "roggen": "rye",
    "mais": "maize",
    "raps": "rapeseed",
}
_FEATURE_ALIASES = {
    "hl gewicht": "hectolitre_weight",
    "hlgewicht": "hectolitre_weight",
    "hektoliter gewicht": "hectolitre_weight",
}


def compare_import_review(review, repository):
    """Ergänzt einen Importentwurf um reproduzierbare Regelwerksvergleiche."""

    if review.origin != "pdf_import":
        return review
    versions: dict[tuple[str, int], object | None] = {}
    compared_deliveries = []
    for delivery in review.deliveries:
        grain_type_code = _grain_type_code(delivery.grain_name.value)
        harvest_year = _year(delivery.delivery_date.value)
        if not grain_type_code or harvest_year is None:
            compared_deliveries.append(
                replace(
                    delivery,
                    rule_check=_unavailable(
                        "Getreideart oder Erntejahr konnten nicht eindeutig "
                        "bestimmt werden; es wurden nur die finanziellen "
                        "Zusammenhänge geprüft."
                    ),
                )
            )
            continue

        if delivery.rule_check.status == "unavailable":
            compared_deliveries.append(
                replace(delivery, grain_type_code=grain_type_code)
            )
            continue

        existing_scheme = delivery.rule_check.scheme
        version = None
        if existing_scheme is not None:
            version = repository.load_version(existing_scheme.version_id)
            if version is not None and (
                version.grain_type_code != grain_type_code
                or version.harvest_year != harvest_year
            ):
                version = None
            if version is None:
                compared_deliveries.append(
                    replace(
                        delivery,
                        grain_type_code=grain_type_code,
                        rule_check=_unavailable(
                            "Die ursprünglich verwendete Regelwerksversion passt "
                            "nicht mehr zu den geänderten Lieferdaten; es wurden "
                            "nur die finanziellen Zusammenhänge geprüft."
                        ),
                    )
                )
                continue
        if version is None:
            key = (grain_type_code, harvest_year)
            if key not in versions:
                available = repository.list_versions(grain_type_code, harvest_year)
                versions[key] = available[0] if available else None
            version = versions[key]
        if version is None:
            compared_deliveries.append(
                replace(
                    delivery,
                    grain_type_code=grain_type_code,
                    rule_check=_unavailable(
                        "Für Getreideart und Erntejahr ist kein aktiviertes "
                        "Regelwerk verfügbar; es wurden nur die finanziellen "
                        "Zusammenhänge geprüft."
                    ),
                )
            )
            continue

        try:
            compared_deliveries.append(
                _compare_delivery(delivery, grain_type_code, version)
            )
        except (GrainValidationError, ValueError, ArithmeticError):
            compared_deliveries.append(
                replace(
                    delivery,
                    grain_type_code=grain_type_code,
                    rule_check=_unavailable(
                        "Das passende Regelwerk konnte mit den erkannten "
                        "Analysewerten nicht eindeutig angewendet werden; es "
                        "wurden nur die finanziellen Zusammenhänge geprüft."
                    ),
                )
            )
    return replace(review, deliveries=tuple(compared_deliveries))


def _compare_delivery(delivery, grain_type_code: str, version):
    scheme = _scheme_from_version(version)
    feature_codes = _feature_codes(scheme)
    mapped_details = []
    measurements = []
    for detail in delivery.details:
        feature_code = _detail_feature_code(detail.label.value, feature_codes)
        mapped_details.append((detail, feature_code))
        if feature_code:
            measurements.append(
                QualityMeasurement(
                    feature_code=feature_code,
                    raw_value=parse_de(detail.analysis_value.value),
                )
            )

    if len({item.feature_code for item in measurements}) != len(measurements):
        raise GrainValidationError("Analysemerkmale sind nicht eindeutig.")

    measured_codes = {item.feature_code for item in measurements}
    comparable_rules = tuple(
        rule
        for rule in scheme.rules
        if rule.feature_code and rule.feature_code in measured_codes
    )
    if not comparable_rules:
        raise GrainValidationError(
            "Keine Regel kann den erkannten Analysewerten zugeordnet werden."
        )
    comparison_scheme = replace(
        scheme,
        quality_features=tuple(
            replace(feature, required=False)
            for feature in scheme.quality_features
            if feature.code in measured_codes
        ),
        rules=comparable_rules,
    )
    calculation = calculate_delivery_quantities(
        GrainDelivery(
            id=delivery.ticket_number.value.strip(),
            supplier_number="import-comparison",
            delivery_date=datetime.strptime(
                delivery.delivery_date.value.strip(), "%d.%m.%Y"
            ).date(),
            ticket_number=delivery.ticket_number.value.strip(),
            grain_type_code=grain_type_code,
            gross_quantity_kg=parse_de(delivery.gross_quantity_kg.value),
            measurements=tuple(measurements),
            base_price_per_tonne=parse_de(delivery.base_price_per_tonne.value),
        ),
        comparison_scheme,
    )

    quantity_by_feature: dict[str, Decimal] = {}
    for deduction in calculation.quantity_deductions:
        if deduction.measurement_code:
            quantity_by_feature[deduction.measurement_code] = (
                quantity_by_feature.get(deduction.measurement_code, Decimal("0"))
                - deduction.deducted_quantity_kg
            )
    price_by_feature: dict[str, Decimal] = {}
    for adjustment in calculation.monetary_adjustments:
        if adjustment.measurement_code and adjustment.price_delta_per_tonne is not None:
            price_by_feature[adjustment.measurement_code] = (
                price_by_feature.get(adjustment.measurement_code, Decimal("0"))
                + adjustment.price_delta_per_tonne
            )

    compared_details = []
    for detail, feature_code in mapped_details:
        if not feature_code:
            compared_details.append(detail)
            continue
        expected_quantity = quantity_by_feature.get(feature_code)
        expected_price = price_by_feature.get(feature_code)
        document_quantity = _optional_decimal(detail.quantity_change_kg.value)
        document_price = _optional_decimal(detail.price_change_per_tonne.value)
        quantity_differs = (
            expected_quantity is not None
            and (document_quantity or Decimal("0")) != expected_quantity
        )
        price_differs = (
            expected_price is not None
            and (document_price or Decimal("0")) != expected_price
        )
        deviation = None
        if quantity_differs or price_differs:
            deviation = GrainRuleDeviation(
                document_quantity_change_kg=(
                    (document_quantity or Decimal("0"))
                    if quantity_differs
                    else None
                ),
                expected_quantity_change_kg=(
                    expected_quantity if quantity_differs else None
                ),
                document_price_change_per_tonne=(
                    (document_price or Decimal("0")) if price_differs else None
                ),
                expected_price_change_per_tonne=(
                    expected_price if price_differs else None
                ),
            )
        compared_details.append(replace(detail, rule_deviation=deviation))

    reference = GrainSchemeReference(
        version_id=version.id,
        grain_type_code=version.grain_type_code,
        harvest_year=version.harvest_year,
        revision=version.revision,
        name=version.name,
    )
    return replace(
        delivery,
        details=tuple(compared_details),
        grain_type_code=grain_type_code,
        rule_check=GrainRuleCheck(status="checked", scheme=reference),
    )


def _scheme_from_version(version) -> SettlementSchemeVersion:
    payload = dict(version.payload)
    if payload.get("format_version", 1) != 1:
        raise GrainValidationError("Format des Regelwerks wird nicht unterstützt.")
    features = tuple(
        QualityFeature(
            code=str(item.get("code") or "").strip(),
            label=str(item.get("label") or "").strip(),
            unit=str(item.get("unit") or "").strip(),
            required=bool(item.get("required", True)),
        )
        for item in payload.get("features", [])
    )
    rules = tuple(
        _rule(item)
        for item in payload.get("rules", [])
        if item.get("enabled", True)
    )
    return SettlementSchemeVersion(
        id=f"grain-scheme-version-{version.id}",
        scheme_id=f"{version.grain_type_code}-{version.harvest_year}",
        version=version.revision,
        name=version.name,
        grain_type_code=version.grain_type_code,
        quality_features=features,
        rules=rules,
    )


def _rule(item: dict) -> SettlementRule:
    return SettlementRule(
        code=str(item.get("code") or "").strip(),
        label=str(item.get("label") or "").strip(),
        phase=RulePhase(str(item.get("phase") or "quantity_deduction")),
        kind=RuleKind(str(item.get("kind") or "")),
        order=int(item.get("order", 0)),
        feature_code=str(item.get("feature_code") or "").strip() or None,
        direction=RuleDirection(str(item.get("direction") or "deduction")),
        quantity_reference=_optional_enum(
            QuantityReference, item.get("quantity_reference")
        ),
        price_reference=_optional_enum(PriceReference, item.get("price_reference")),
        parameters=_parameters(item.get("parameters")),
        tiers=_tiers(item.get("tiers")),
    )


def _parameters(value) -> dict[str, str]:
    result = {}
    for part in (item.strip() for item in str(value or "").split(";")):
        if not part:
            continue
        if "=" not in part:
            raise GrainValidationError("Regelparameter ist ungültig.")
        name, raw_value = (item.strip() for item in part.split("=", 1))
        if not name or not raw_value:
            raise GrainValidationError("Regelparameter ist unvollständig.")
        try:
            result[name] = str(parse_de(raw_value))
        except ValueError:
            result[name] = raw_value
    return result


def _tiers(value) -> tuple[RuleTier, ...]:
    result = []
    for part in (item.strip() for item in str(value or "").split("|")):
        if not part:
            continue
        interval, raw_value = (item.strip() for item in part.split("=", 1))
        lower, upper = (item.strip() for item in interval.split("..", 1))
        result.append(
            RuleTier(
                lower_bound=parse_de(lower) if lower else None,
                upper_bound=parse_de(upper) if upper else None,
                value=parse_de(raw_value),
            )
        )
    return tuple(result)


def _feature_codes(scheme) -> dict[str, str]:
    result = {_normalized(feature.label): feature.code for feature in scheme.quality_features}
    for alias, feature_code in _FEATURE_ALIASES.items():
        if any(feature.code == feature_code for feature in scheme.quality_features):
            result[_normalized(alias)] = feature_code
    return result


def _detail_feature_code(label: str, feature_codes: dict[str, str]) -> str | None:
    normalized = _normalized(label)
    return feature_codes.get(normalized)


def _grain_type_code(name: str) -> str | None:
    normalized = _normalized(name)
    for label, code in _GRAIN_NAMES.items():
        if label in normalized:
            return code
    return None


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _year(value: str) -> int | None:
    try:
        return datetime.strptime(str(value or "").strip(), "%d.%m.%Y").year
    except ValueError:
        return None


def _optional_decimal(value: str) -> Decimal | None:
    return parse_de(value) if str(value or "").strip() else None


def _optional_enum(enum_type, value):
    normalized = str(value or "").strip()
    return enum_type(normalized) if normalized else None


def _unavailable(note: str) -> GrainRuleCheck:
    return GrainRuleCheck(status="unavailable", note=note)


__all__ = ["compare_import_review"]
