"""Reine Mengen- und Ausgangswertberechnung fuer Getreideabrechnungen."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

from .grain_models import (
    CalculationStep,
    GrainDelivery,
    GrainValidationError,
    MonetaryAdjustment,
    PriceReference,
    QuantityDeduction,
    QuantityReference,
    RuleDirection,
    RuleKind,
    RulePhase,
    RuleTier,
    SettlementRule,
    SettlementBatchResult,
    SettlementResult,
    SettlementSchemeVersion,
    SettlementStatus,
)


THOUSAND = Decimal("1000")
HUNDRED = Decimal("100")
ONE = Decimal("1")
ZERO = Decimal("0")

QUANTITY_RULE_KINDS = frozenset(
    {
        RuleKind.PERCENTAGE_OF_MEASUREMENT,
        RuleKind.EXCESS_OVER_BASIS,
        RuleKind.FIXED_QUANTITY,
        RuleKind.TIERED,
    }
)
MEASUREMENT_RULE_KINDS = frozenset(
    {
        RuleKind.PERCENTAGE_OF_MEASUREMENT,
        RuleKind.EXCESS_OVER_BASIS,
        RuleKind.TIERED,
    }
)
PRICE_RULE_KINDS = frozenset(
    {
        RuleKind.ABSOLUTE_PER_TONNE,
        RuleKind.EXCESS_OVER_BASIS,
        RuleKind.PERCENTAGE_OF_PRICE,
        RuleKind.TIERED,
    }
)


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

    Die Funktion bleibt fuer Tests und Vorschauen erhalten, die bewusst noch
    keine konfigurierten Mengenregeln anwenden sollen.
    """

    return _calculate_delivery(delivery, scheme, apply_quantity_rules=False)


def calculate_delivery_quantities(
    delivery: GrainDelivery,
    scheme: SettlementSchemeVersion,
) -> SettlementResult:
    """Wendet Mengen-, Preis- und Kostenregeln in Reihenfolge an."""

    return _calculate_delivery(delivery, scheme, apply_quantity_rules=True)


def calculate_settlement_quantities(
    deliveries: tuple[GrainDelivery, ...],
    scheme: SettlementSchemeVersion,
) -> SettlementBatchResult:
    """Berechnet und summiert alle Lieferungen einer Abrechnung."""

    if not deliveries:
        raise GrainValidationError("Die Abrechnung benoetigt mindestens eine Lieferung.")

    supplier_numbers = {delivery.supplier_number for delivery in deliveries}
    if len(supplier_numbers) != 1:
        raise GrainValidationError(
            "Alle Lieferungen einer Abrechnung muessen denselben Lieferanten haben."
        )
    delivery_ids = [delivery.id for delivery in deliveries]
    if len(delivery_ids) != len(set(delivery_ids)):
        raise GrainValidationError("Lieferungs-IDs muessen eindeutig sein.")
    ticket_numbers = [delivery.ticket_number for delivery in deliveries]
    if len(ticket_numbers) != len(set(ticket_numbers)):
        raise GrainValidationError("Wiegescheinnummern muessen eindeutig sein.")

    results = tuple(
        calculate_delivery_quantities(delivery, scheme)
        for delivery in deliveries
    )
    gross_quantity = sum(
        (result.gross_quantity_kg for result in results),
        ZERO,
    )
    settlement_quantity = sum(
        (result.settlement_quantity_kg for result in results),
        ZERO,
    )
    base_amount = sum((result.base_amount for result in results), ZERO).quantize(
        scheme.rounding.money,
        rounding=scheme.rounding.mode,
    )
    net_amount = sum((result.net_amount for result in results), ZERO).quantize(
        scheme.rounding.money,
        rounding=scheme.rounding.mode,
    )
    return SettlementBatchResult(
        supplier_number=next(iter(supplier_numbers)),
        scheme_version_id=scheme.id,
        delivery_results=results,
        gross_quantity_kg=gross_quantity,
        deducted_quantity_kg=gross_quantity - settlement_quantity,
        settlement_quantity_kg=settlement_quantity,
        base_amount=base_amount,
        net_amount=net_amount,
        deducted_amount=(base_amount - net_amount).quantize(
            scheme.rounding.money,
            rounding=scheme.rounding.mode,
        ),
        status=_combined_status(results),
    )


def _combined_status(
    results: tuple[SettlementResult, ...],
) -> SettlementStatus:
    statuses = {result.status for result in results}
    if SettlementStatus.REJECTED in statuses:
        return SettlementStatus.REJECTED
    if SettlementStatus.REVIEW_REQUIRED in statuses:
        return SettlementStatus.REVIEW_REQUIRED
    return SettlementStatus.CALCULATED


def _calculate_delivery(
    delivery: GrainDelivery,
    scheme: SettlementSchemeVersion,
    *,
    apply_quantity_rules: bool,
) -> SettlementResult:
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
    steps = [
        CalculationStep(
            code="gross_quantity",
            label="Bruttomenge",
            category="quantity",
            result=quantity,
            unit="kg",
        )
    ]
    deductions: list[QuantityDeduction] = []
    settlement_quantity = quantity

    if apply_quantity_rules:
        quantity_rules = tuple(
            rule
            for rule in scheme.ordered_rules
            if rule.phase is RulePhase.QUANTITY_DEDUCTION
        )
        _validate_quantity_rules(quantity_rules)
        for rule in quantity_rules:
            reference_quantity = _reference_quantity(
                rule,
                gross_quantity=quantity,
                remaining_quantity=settlement_quantity,
            )
            measurement_value = _measurement_value(delivery, rule)
            unrounded_deduction = _calculate_quantity_deduction(
                rule,
                reference_quantity,
                measurement_value,
            )
            deduction = unrounded_deduction.quantize(
                rounding.quantity_kg,
                rounding=rounding.mode,
            )
            if deduction < ZERO:
                raise GrainValidationError(
                    f"Mengenabzug {rule.label} darf nicht negativ sein."
                )
            if deduction > settlement_quantity:
                raise GrainValidationError(
                    f"Mengenabzug {rule.label} ist groesser als die Restmenge."
                )
            settlement_quantity = (settlement_quantity - deduction).quantize(
                rounding.quantity_kg,
                rounding=rounding.mode,
            )
            deductions.append(
                QuantityDeduction(
                    rule_code=rule.code,
                    label=rule.label,
                    reference_quantity_kg=reference_quantity,
                    deducted_quantity_kg=deduction,
                    remaining_quantity_kg=settlement_quantity,
                    measurement_code=rule.feature_code,
                    measurement_value=measurement_value,
                )
            )
            steps.append(
                CalculationStep(
                    code=f"quantity_deduction:{rule.code}",
                    label=rule.label,
                    category="quantity_deduction",
                    basis=reference_quantity,
                    unrounded_result=unrounded_deduction,
                    result=deduction,
                    unit="kg",
                    rule_code=rule.code,
                    details={
                        "reference": rule.quantity_reference.value,
                        "reference_quantity_kg": str(reference_quantity),
                        "measurement_code": rule.feature_code or "",
                        "measurement_value": (
                            str(measurement_value)
                            if measurement_value is not None
                            else ""
                        ),
                    },
                )
            )

        steps.append(
            CalculationStep(
                code="settlement_quantity",
                label="Abrechnungsmenge",
                category="quantity",
                result=settlement_quantity,
                unit="kg",
            )
        )

    price = base_price.quantize(
        rounding.price_per_tonne,
        rounding=rounding.mode,
    )
    unrounded_amount = settlement_quantity / THOUSAND * price
    amount = unrounded_amount.quantize(
        rounding.money,
        rounding=rounding.mode,
    )

    steps.extend(
        (
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
                basis=settlement_quantity,
                unrounded_result=unrounded_amount,
                result=amount,
                unit="EUR",
            ),
        )
    )
    settlement_price = price
    net_amount = amount
    monetary_adjustments: list[MonetaryAdjustment] = []
    if apply_quantity_rules:
        settlement_price, net_amount, monetary_adjustments = _apply_money_rules(
            delivery=delivery,
            scheme=scheme,
            settlement_quantity=settlement_quantity,
            base_price=price,
            base_amount=amount,
            steps=steps,
        )

    return SettlementResult(
        delivery_id=delivery.id,
        scheme_version_id=scheme.id,
        gross_quantity_kg=quantity,
        settlement_quantity_kg=settlement_quantity,
        base_price_per_tonne=price,
        base_amount=amount,
        net_amount=net_amount,
        status=SettlementStatus.CALCULATED,
        steps=tuple(steps),
        quantity_deductions=tuple(deductions),
        settlement_price_per_tonne=settlement_price,
        monetary_adjustments=tuple(monetary_adjustments),
    )


def _apply_money_rules(
    *,
    delivery: GrainDelivery,
    scheme: SettlementSchemeVersion,
    settlement_quantity: Decimal,
    base_price: Decimal,
    base_amount: Decimal,
    steps: list[CalculationStep],
) -> tuple[Decimal, Decimal, list[MonetaryAdjustment]]:
    price_rules = tuple(
        rule
        for rule in scheme.ordered_rules
        if rule.phase is RulePhase.PRICE_ADJUSTMENT
    )
    cost_rules = tuple(
        rule
        for rule in scheme.ordered_rules
        if rule.phase is RulePhase.COST
    )
    _validate_price_rules(price_rules)
    _validate_cost_rules(cost_rules)

    rounding = scheme.rounding
    running_price = base_price
    running_amount = base_amount
    adjustments: list[MonetaryAdjustment] = []
    for rule in price_rules:
        measurement_value = _measurement_value(delivery, rule)
        magnitude = _price_adjustment_per_tonne(
            rule,
            base_price=base_price,
            running_price=running_price,
            measurement_value=measurement_value,
        ).quantize(rounding.price_per_tonne, rounding=rounding.mode)
        price_delta = _signed_adjustment(rule, magnitude)
        resulting_price = (running_price + price_delta).quantize(
            rounding.price_per_tonne,
            rounding=rounding.mode,
        )
        if resulting_price < ZERO:
            raise GrainValidationError(
                f"Preisabzug {rule.label} fuehrt zu einem negativen Preis."
            )
        resulting_amount = (
            settlement_quantity / THOUSAND * resulting_price
        ).quantize(rounding.money, rounding=rounding.mode)
        amount_delta = resulting_amount - running_amount
        adjustments.append(
            MonetaryAdjustment(
                rule_code=rule.code,
                label=rule.label,
                phase=rule.phase,
                direction=rule.direction,
                price_delta_per_tonne=price_delta,
                resulting_price_per_tonne=resulting_price,
                amount_delta=amount_delta,
                resulting_amount=resulting_amount,
                measurement_code=rule.feature_code,
                measurement_value=measurement_value,
            )
        )
        steps.append(
            CalculationStep(
                code=f"price_adjustment:{rule.code}",
                label=rule.label,
                category="price_adjustment",
                basis=running_price,
                result=price_delta,
                unit="EUR/t",
                rule_code=rule.code,
                details={
                    "direction": rule.direction.value,
                    "amount_delta": str(amount_delta),
                    "measurement_code": rule.feature_code or "",
                    "measurement_value": (
                        str(measurement_value)
                        if measurement_value is not None
                        else ""
                    ),
                },
            )
        )
        running_price = resulting_price
        running_amount = resulting_amount

    for rule in cost_rules:
        magnitude = _decimal_parameter(rule, "amount").quantize(
            rounding.money,
            rounding=rounding.mode,
        )
        amount_delta = _signed_adjustment(rule, magnitude)
        resulting_amount = (running_amount + amount_delta).quantize(
            rounding.money,
            rounding=rounding.mode,
        )
        if resulting_amount < ZERO:
            raise GrainValidationError(
                f"Kostenregel {rule.label} fuehrt zu einem negativen Betrag."
            )
        adjustments.append(
            MonetaryAdjustment(
                rule_code=rule.code,
                label=rule.label,
                phase=rule.phase,
                direction=rule.direction,
                amount_delta=amount_delta,
                resulting_amount=resulting_amount,
            )
        )
        steps.append(
            CalculationStep(
                code=f"cost:{rule.code}",
                label=rule.label,
                category="cost",
                basis=running_amount,
                result=amount_delta,
                unit="EUR",
                rule_code=rule.code,
                details={"direction": rule.direction.value},
            )
        )
        running_amount = resulting_amount

    steps.append(
        CalculationStep(
            code="net_amount",
            label="Abrechnungsbetrag",
            category="amount",
            result=running_amount,
            unit="EUR",
        )
    )
    return running_price, running_amount, adjustments


def _validate_price_rules(rules: tuple[SettlementRule, ...]) -> None:
    for rule in rules:
        if rule.kind not in PRICE_RULE_KINDS:
            raise GrainValidationError(
                f"Regeltyp {rule.kind.value} ist keine Preisregel."
            )
        if rule.kind is RuleKind.PERCENTAGE_OF_PRICE and rule.price_reference not in {
            PriceReference.BASE_PRICE,
            PriceReference.RUNNING_PRICE,
        }:
            raise GrainValidationError(
                f"Preisregel {rule.label} benoetigt einen Preisbezug."
            )
        if rule.kind in {RuleKind.EXCESS_OVER_BASIS, RuleKind.TIERED}:
            if not rule.feature_code:
                raise GrainValidationError(
                    f"Preisregel {rule.label} benoetigt ein Analysemerkmal."
                )
        if rule.kind is RuleKind.TIERED:
            _validate_tiers(rule)


def _validate_cost_rules(rules: tuple[SettlementRule, ...]) -> None:
    for rule in rules:
        if rule.kind is not RuleKind.FIXED_AMOUNT:
            raise GrainValidationError(
                f"Regeltyp {rule.kind.value} ist keine feste Kostenregel."
            )


def _price_adjustment_per_tonne(
    rule: SettlementRule,
    *,
    base_price: Decimal,
    running_price: Decimal,
    measurement_value: Decimal | None,
) -> Decimal:
    if rule.kind is RuleKind.ABSOLUTE_PER_TONNE:
        return _decimal_parameter(rule, "amount_per_tonne")
    if rule.kind is RuleKind.EXCESS_OVER_BASIS:
        if measurement_value is None:
            raise GrainValidationError(
                f"Analysewert fuer Preisregel {rule.label} fehlt."
            )
        basis_value = _decimal_parameter(rule, "basis_value")
        amount_per_unit = _decimal_parameter(rule, "amount_per_unit")
        return max(measurement_value - basis_value, ZERO) * amount_per_unit
    reference_price = (
        running_price
        if rule.price_reference is PriceReference.RUNNING_PRICE
        else base_price
    )
    if rule.kind is RuleKind.PERCENTAGE_OF_PRICE:
        percentage = _decimal_parameter(rule, "percentage")
        return reference_price * percentage / HUNDRED
    tier = _matching_tier(rule, measurement_value)
    result_kind = str(rule.parameters.get("result_kind", "absolute_per_tonne"))
    if result_kind == "absolute_per_tonne":
        return tier.value
    if result_kind == "percentage_of_price":
        return reference_price * tier.value / HUNDRED
    raise GrainValidationError(
        f"Preisstaffel {rule.label} hat eine unbekannte Ergebnisart."
    )


def _signed_adjustment(rule: SettlementRule, magnitude: Decimal) -> Decimal:
    return magnitude if rule.direction is RuleDirection.SURCHARGE else -magnitude


def _validate_quantity_rules(rules: tuple[SettlementRule, ...]) -> None:
    for rule in rules:
        if rule.kind not in QUANTITY_RULE_KINDS:
            raise GrainValidationError(
                f"Regeltyp {rule.kind.value} ist kein Mengenabzug."
            )
        if rule.direction is not RuleDirection.DEDUCTION:
            raise GrainValidationError(
                f"Mengenregel {rule.label} muss ein Abzug sein."
            )
        if rule.quantity_reference not in {
            QuantityReference.GROSS_QUANTITY,
            QuantityReference.REMAINING_QUANTITY,
        }:
            raise GrainValidationError(
                f"Mengenregel {rule.label} benoetigt eine gueltige Bezugsmenge."
            )
        if rule.kind in MEASUREMENT_RULE_KINDS and not rule.feature_code:
            raise GrainValidationError(
                f"Mengenregel {rule.label} benoetigt ein Analysemerkmal."
            )
        if rule.kind is RuleKind.TIERED:
            _validate_tiers(rule)


def _reference_quantity(
    rule: SettlementRule,
    *,
    gross_quantity: Decimal,
    remaining_quantity: Decimal,
) -> Decimal:
    if rule.quantity_reference is QuantityReference.GROSS_QUANTITY:
        return gross_quantity
    return remaining_quantity


def _measurement_value(
    delivery: GrainDelivery,
    rule: SettlementRule,
) -> Decimal | None:
    if rule.kind not in MEASUREMENT_RULE_KINDS:
        return None
    measurement = delivery.measurement(rule.feature_code or "")
    if measurement is None:
        raise GrainValidationError(
            f"Analysewert fuer Regel {rule.label} fehlt."
        )
    value = measurement.effective_value
    if value < ZERO:
        raise GrainValidationError(
            f"Analysewert fuer Regel {rule.label} darf nicht negativ sein."
        )
    return value


def _calculate_percentage_of_measurement(
    rule: SettlementRule,
    reference_quantity: Decimal,
    measurement_value: Decimal | None,
) -> Decimal:
    if measurement_value is None:
        raise GrainValidationError(
            f"Analysewert fuer Mengenregel {rule.label} ist ungueltig."
        )
    factor = _decimal_parameter(rule, "factor", default=ONE)
    return _percentage_of_quantity(reference_quantity, measurement_value, factor)


def _calculate_excess_over_basis(
    rule: SettlementRule,
    reference_quantity: Decimal,
    measurement_value: Decimal | None,
) -> Decimal:
    if measurement_value is None:
        raise GrainValidationError(
            f"Analysewert fuer Mengenregel {rule.label} fehlt."
        )
    basis_value = _decimal_parameter(rule, "basis_value")
    factor = _decimal_parameter(rule, "factor", default=ONE)
    excess = max(measurement_value - basis_value, ZERO)
    return _percentage_of_quantity(reference_quantity, excess, factor)


def _calculate_fixed_quantity(
    rule: SettlementRule,
    _reference_quantity: Decimal,
    _measurement_value: Decimal | None,
) -> Decimal:
    return _decimal_parameter(rule, "amount_kg")


def _calculate_tiered_quantity(
    rule: SettlementRule,
    reference_quantity: Decimal,
    measurement_value: Decimal | None,
) -> Decimal:
    if measurement_value is None:
        raise GrainValidationError(
            f"Analysewert fuer Mengenregel {rule.label} fehlt."
        )
    tier = _matching_tier(rule, measurement_value)
    result_kind = str(rule.parameters.get("result_kind", "percentage"))
    if result_kind == "percentage":
        return _percentage_of_quantity(reference_quantity, tier.value)
    if result_kind == "fixed_quantity_kg":
        return tier.value
    raise GrainValidationError(
        f"Mengenstaffel {rule.label} hat eine unbekannte Ergebnisart."
    )


def _matching_tier(
    rule: SettlementRule,
    measurement_value: Decimal | None,
) -> RuleTier:
    if measurement_value is None:
        raise GrainValidationError(
            f"Analysewert fuer Staffel {rule.label} fehlt."
        )
    tier = next(
        (
            candidate
            for candidate in rule.tiers
            if _tier_contains(candidate, measurement_value)
        ),
        None,
    )
    if tier is None:
        raise GrainValidationError(
            f"Analysewert {measurement_value} ist durch die Staffel "
            f"{rule.label} nicht abgedeckt."
        )
    return tier


def _percentage_of_quantity(
    quantity: Decimal,
    percentage: Decimal,
    factor: Decimal = ONE,
) -> Decimal:
    return quantity * percentage / HUNDRED * factor


QuantityCalculator = Callable[
    [SettlementRule, Decimal, Decimal | None],
    Decimal,
]
QUANTITY_CALCULATORS: dict[RuleKind, QuantityCalculator] = {
    RuleKind.PERCENTAGE_OF_MEASUREMENT: _calculate_percentage_of_measurement,
    RuleKind.EXCESS_OVER_BASIS: _calculate_excess_over_basis,
    RuleKind.FIXED_QUANTITY: _calculate_fixed_quantity,
    RuleKind.TIERED: _calculate_tiered_quantity,
}


def _calculate_quantity_deduction(
    rule: SettlementRule,
    reference_quantity: Decimal,
    measurement_value: Decimal | None,
) -> Decimal:
    return QUANTITY_CALCULATORS[rule.kind](
        rule,
        reference_quantity,
        measurement_value,
    )


def _decimal_parameter(
    rule: SettlementRule,
    name: str,
    *,
    default: Decimal | None = None,
) -> Decimal:
    value = rule.parameters.get(name, default)
    if value is None:
        raise GrainValidationError(
            f"Parameter {name} fuer Regel {rule.label} fehlt."
        )
    try:
        result = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise GrainValidationError(
            f"Parameter {name} fuer Regel {rule.label} ist keine Zahl."
        ) from exc
    if result < ZERO:
        raise GrainValidationError(
            f"Parameter {name} fuer Regel {rule.label} darf nicht negativ sein."
        )
    return result


def _validate_tiers(rule: SettlementRule) -> None:
    if not rule.tiers:
        raise GrainValidationError(
            f"Mengenstaffel {rule.label} enthaelt keine Stufen."
        )
    previous: RuleTier | None = None
    for tier in rule.tiers:
        if tier.value < ZERO:
            raise GrainValidationError(
                f"Staffelwert fuer Regel {rule.label} darf nicht negativ sein."
            )
        if previous is not None:
            if previous.upper_bound is None or tier.lower_bound is None:
                raise GrainValidationError(
                    f"Staffeln fuer Regel {rule.label} sind nicht eindeutig sortiert."
                )
            overlaps = tier.lower_bound < previous.upper_bound or (
                tier.lower_bound == previous.upper_bound
                and previous.upper_inclusive
                and tier.lower_inclusive
            )
            if overlaps:
                raise GrainValidationError(
                    f"Staffeln fuer Regel {rule.label} ueberlappen sich."
                )
        previous = tier


def _tier_contains(tier: RuleTier, value: Decimal) -> bool:
    lower_matches = tier.lower_bound is None or (
        value >= tier.lower_bound
        if tier.lower_inclusive
        else value > tier.lower_bound
    )
    upper_matches = tier.upper_bound is None or (
        value <= tier.upper_bound
        if tier.upper_inclusive
        else value < tier.upper_bound
    )
    return lower_matches and upper_matches
