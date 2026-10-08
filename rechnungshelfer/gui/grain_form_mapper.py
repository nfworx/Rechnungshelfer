"""Abbildung editierbarer GUI-Werte auf den reinen Getreide-Domainkern."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from rechnungshelfer.domain.grain_calculation import calculate_settlement_quantities
from rechnungshelfer.domain.grain_models import (
    GrainDelivery,
    GrainValidationError,
    QualityFeature,
    QualityMeasurement,
    PriceReference,
    QuantityReference,
    RuleDirection,
    RuleKind,
    RulePhase,
    RuleTier,
    SettlementBatchResult,
    SettlementRule,
    SettlementSchemeVersion,
)
from rechnungshelfer.services.format_service import parse_de


@dataclass(frozen=True)
class FeatureFormValue:
    code: str
    label: str
    required: bool = True


@dataclass(frozen=True)
class AnalysisFormValue:
    feature_code: str
    raw_value: str
    corrected_value: str = ""


@dataclass(frozen=True)
class RuleFormValue:
    code: str
    label: str
    kind: str
    feature_code: str
    quantity_reference: str
    parameters: str = ""
    tiers: str = ""
    order: int = 0
    phase: str = "quantity_deduction"
    direction: str = "deduction"
    price_reference: str = ""


@dataclass(frozen=True)
class DeliveryFormValue:
    id: str
    delivery_date: str
    ticket_number: str
    grain_type_code: str
    gross_quantity_kg: str
    base_price_per_tonne: str
    analyses: tuple[AnalysisFormValue, ...]


@dataclass(frozen=True)
class GrainSettlementForm:
    supplier_number: str
    features: tuple[FeatureFormValue, ...]
    rules: tuple[RuleFormValue, ...]
    deliveries: tuple[DeliveryFormValue, ...]


def calculate_settlement_preview(
    form: GrainSettlementForm,
) -> SettlementBatchResult:
    """Berechnet eine fluechtige Mehrlieferungs-Abrechnung ohne Speicherung."""

    grain_type_code = _settlement_grain_type(form.deliveries)
    scheme = build_preview_scheme(grain_type_code, form.features, form.rules)
    supplier_number = _required_text(form.supplier_number, "Lieferantennummer")
    deliveries = tuple(
        _map_delivery(value, supplier_number, scheme)
        for value in form.deliveries
    )
    return calculate_settlement_quantities(deliveries, scheme)


def build_preview_scheme(
    grain_type_code: str,
    features: tuple[FeatureFormValue, ...],
    rules: tuple[RuleFormValue, ...],
) -> SettlementSchemeVersion:
    """Validiert die aktuell im Regel-Dialog erfasste Konfiguration."""

    return SettlementSchemeVersion(
        id="preview-schema-v1",
        scheme_id="preview-schema",
        version=1,
        name="Unbestätigtes Prüfschema",
        grain_type_code=_required_text(grain_type_code, "Getreideart"),
        quality_features=tuple(
            QualityFeature(
                code=_required_text(value.code, "Merkmalscode"),
                label=_required_text(value.label, "Merkmalsbezeichnung"),
                required=value.required,
            )
            for value in features
        ),
        rules=tuple(_map_rule(value) for value in rules),
    )


def parse_parameters(value: str) -> dict[str, str]:
    """Liest ``name=wert; name=wert`` ohne eine Formelsprache einzufuehren."""

    result: dict[str, str] = {}
    for part in (item.strip() for item in str(value or "").split(";")):
        if not part:
            continue
        if "=" not in part:
            raise GrainValidationError(
                f"Regelparameter '{part}' muss als name=wert angegeben werden."
            )
        name, raw_value = (item.strip() for item in part.split("=", 1))
        if not name or not raw_value:
            raise GrainValidationError("Regelparameter darf nicht leer sein.")
        if name in result:
            raise GrainValidationError(f"Regelparameter {name} ist doppelt.")
        result[name] = _normalize_decimal_if_possible(raw_value)
    return result


def parse_tiers(value: str) -> tuple[RuleTier, ...]:
    """Liest Staffeln im Format ``untergrenze..obergrenze=wert``."""

    tiers = []
    for part in (item.strip() for item in str(value or "").split("|")):
        if not part:
            continue
        if "=" not in part or ".." not in part:
            raise GrainValidationError(
                "Staffel muss als untergrenze..obergrenze=wert angegeben werden."
            )
        interval, raw_value = (item.strip() for item in part.split("=", 1))
        lower, upper = (item.strip() for item in interval.split("..", 1))
        if not raw_value:
            raise GrainValidationError("Staffelwert darf nicht leer sein.")
        tiers.append(
            RuleTier(
                lower_bound=_optional_decimal(lower),
                upper_bound=_optional_decimal(upper),
                value=_required_decimal(raw_value, "Staffelwert"),
            )
        )
    return tuple(tiers)


def _map_delivery(
    value: DeliveryFormValue,
    supplier_number: str,
    scheme: SettlementSchemeVersion,
) -> GrainDelivery:
    return GrainDelivery(
        id=_required_text(value.id, "Lieferungs-ID"),
        supplier_number=supplier_number,
        delivery_date=_parse_date(value.delivery_date),
        ticket_number=_required_text(value.ticket_number, "Wiegescheinnummer"),
        grain_type_code=_required_text(value.grain_type_code, "Getreideart"),
        gross_quantity_kg=_required_decimal(value.gross_quantity_kg, "Bruttomenge"),
        measurements=tuple(
            _map_analysis(analysis)
            for analysis in value.analyses
            if str(analysis.raw_value or "").strip()
        ),
        base_price_per_tonne=_optional_decimal(value.base_price_per_tonne),
    )


def _map_analysis(value: AnalysisFormValue) -> QualityMeasurement:
    corrected_value = _optional_decimal(value.corrected_value)
    return QualityMeasurement(
        feature_code=_required_text(value.feature_code, "Merkmalscode"),
        raw_value=_required_decimal(value.raw_value, "Analysewert"),
        corrected_value=corrected_value,
        correction_reason=(
            "Manuelle Korrektur in der Prüfvorschau"
            if corrected_value is not None
            else ""
        ),
    )


def _settlement_grain_type(
    deliveries: tuple[DeliveryFormValue, ...],
) -> str:
    if not deliveries:
        raise GrainValidationError(
            "Die Abrechnung benoetigt mindestens eine Lieferung."
        )
    grain_types = {
        _required_text(delivery.grain_type_code, "Getreideart")
        for delivery in deliveries
    }
    if len(grain_types) != 1:
        raise GrainValidationError(
            "Eine Abrechnung kann derzeit nur eine Getreideart enthalten."
        )
    return next(iter(grain_types))


def _map_rule(value: RuleFormValue) -> SettlementRule:
    try:
        kind = RuleKind(value.kind)
    except ValueError as exc:
        raise GrainValidationError(f"Unbekannter Regeltyp: {value.kind}") from exc
    phase = _enum_value(RulePhase, value.phase, "Regelphase")
    direction = _enum_value(RuleDirection, value.direction, "Regelrichtung")
    quantity_reference = _optional_enum_value(
        QuantityReference,
        value.quantity_reference,
        "Bezugsmenge",
    )
    price_reference = _optional_enum_value(
        PriceReference,
        value.price_reference,
        "Preisbezug",
    )

    return SettlementRule(
        code=_required_text(value.code, "Regelcode"),
        label=_required_text(value.label, "Regelbezeichnung"),
        phase=phase,
        kind=kind,
        order=value.order,
        feature_code=str(value.feature_code or "").strip() or None,
        direction=direction,
        quantity_reference=quantity_reference,
        price_reference=price_reference,
        parameters=parse_parameters(value.parameters),
        tiers=parse_tiers(value.tiers),
    )


def _enum_value(enum_type, value: str, label: str):
    try:
        return enum_type(value)
    except ValueError as exc:
        raise GrainValidationError(f"Unbekannte {label}: {value}") from exc


def _optional_enum_value(enum_type, value: str, label: str):
    normalized = str(value or "").strip()
    return _enum_value(enum_type, normalized, label) if normalized else None


def _required_text(value: str, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise GrainValidationError(f"{label} fehlt.")
    return result


def _required_decimal(value: str, label: str) -> Decimal:
    if not str(value or "").strip():
        raise GrainValidationError(f"{label} fehlt.")
    try:
        return parse_de(value)
    except ValueError as exc:
        raise GrainValidationError(f"{label} ist keine gültige Zahl.") from exc


def _optional_decimal(value: str) -> Decimal | None:
    if not str(value or "").strip():
        return None
    return _required_decimal(value, "Zahlenwert")


def _normalize_decimal_if_possible(value: str) -> str:
    try:
        return str(parse_de(value))
    except ValueError:
        return value


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(str(value or "").strip(), "%d.%m.%Y").date()
    except ValueError as exc:
        raise GrainValidationError(
            "Lieferdatum muss im Format TT.MM.JJJJ angegeben werden."
        ) from exc
