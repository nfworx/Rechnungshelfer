"""Reiner Berechnungsvertrag fuer Getreideabrechnungen."""

from __future__ import annotations

from decimal import Decimal

from .grain_models import (
    CalculationStep,
    GrainDelivery,
    GrainValidationError,
    SettlementResult,
    SettlementSchemeVersion,
    SettlementStatus,
)


THOUSAND = Decimal("1000")


def validate_delivery_for_scheme(
    delivery: GrainDelivery,
    scheme: SettlementSchemeVersion,
) -> None:
    """Prueft nur schemabezogene Eingaben, ohne Ergebnisse zu veraendern."""

    if delivery.grain_type_code != scheme.grain_type_code:
        raise GrainValidationError(
            "Getreideart der Lieferung passt nicht zum Abrechnungsschema."
        )

    missing = [
        feature.label
        for feature in scheme.quality_features
        if feature.required and delivery.measurement(feature.code) is None
    ]
    if missing:
        raise GrainValidationError(
            "Erforderliche Analysewerte fehlen: " + ", ".join(missing)
        )

    configured_features = {feature.code for feature in scheme.quality_features}
    unknown = sorted(
        measurement.feature_code
        for measurement in delivery.measurements
        if measurement.feature_code not in configured_features
    )
    if unknown:
        raise GrainValidationError(
            "Analysewerte sind im Schema nicht aktiv: " + ", ".join(unknown)
        )


def calculate_delivery_baseline(
    delivery: GrainDelivery,
    scheme: SettlementSchemeVersion,
) -> SettlementResult:
    """Berechnet den neutralen Ausgangsfall vor Anwendung einzelner Regeln.

    Schritt 1 legt damit Einheiten, Rundung und Ergebnisstruktur fest. Die
    regelbasierte Mengen-, Preis- und Kostenberechnung wird darauf aufbauend in
    den folgenden freizugebenden Schritten ergaenzt.
    """

    validate_delivery_for_scheme(delivery, scheme)
    base_price = (
        delivery.base_price_per_tonne
        if delivery.base_price_per_tonne is not None
        else scheme.default_base_price_per_tonne
    )
    if base_price is None:
        raise GrainValidationError("Basispreis fuer die Lieferung fehlt.")

    rounding = scheme.rounding
    quantity = delivery.gross_quantity_kg.quantize(
        rounding.quantity_kg,
        rounding=rounding.mode,
    )
    price = base_price.quantize(
        rounding.price_per_tonne,
        rounding=rounding.mode,
    )
    unrounded_amount = quantity / THOUSAND * price
    amount = unrounded_amount.quantize(
        rounding.money,
        rounding=rounding.mode,
    )

    steps = (
        CalculationStep(
            code="gross_quantity",
            label="Bruttomenge",
            category="quantity",
            result=quantity,
            unit="kg",
        ),
        CalculationStep(
            code="base_price",
            label="Basispreis",
            category="price",
            result=price,
            unit="EUR/t",
        ),
        CalculationStep(
            code="base_amount",
            label="Basiswarenwert",
            category="amount",
            basis=unrounded_amount,
            result=amount,
            unit="EUR",
        ),
    )

    return SettlementResult(
        delivery_id=delivery.id,
        scheme_version_id=scheme.id,
        gross_quantity_kg=quantity,
        settlement_quantity_kg=quantity,
        base_price_per_tonne=price,
        base_amount=amount,
        net_amount=amount,
        status=SettlementStatus.CALCULATED,
        steps=steps,
    )

