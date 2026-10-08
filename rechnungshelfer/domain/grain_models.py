"""Fachliche Datentypen fuer konfigurierbare Getreideabrechnungen.

Das Modul kennt weder GUI noch Datenbank oder Rechnungsformate. Konkrete
Grenzwerte und Geldbetraege werden als Daten in ``SettlementSchemeVersion``
abgelegt und nicht in der Berechnungsengine festgeschrieben.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from types import MappingProxyType
from typing import Mapping


ZERO = Decimal("0")


def decimal_value(value: object) -> Decimal:
    """Konvertiert fachliche Zahlen ohne binaere Float-Arithmetik."""

    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return ZERO
    return Decimal(str(value).replace(",", "."))


def _frozen_parameters(values: Mapping[str, object] | None) -> Mapping[str, object]:
    return MappingProxyType(dict(values or {}))


class GrainValidationError(ValueError):
    """Die Abrechnungseingaben oder das verwendete Schema sind ungueltig."""


class RulePhase(str, Enum):
    QUALITY_DECISION = "quality_decision"
    QUANTITY_DEDUCTION = "quantity_deduction"
    PRICE_ADJUSTMENT = "price_adjustment"
    COST = "cost"

    @property
    def calculation_order(self) -> int:
        return {
            RulePhase.QUALITY_DECISION: 0,
            RulePhase.QUANTITY_DEDUCTION: 1,
            RulePhase.PRICE_ADJUSTMENT: 2,
            RulePhase.COST: 3,
        }[self]


class RuleKind(str, Enum):
    """Geschlossene Menge unterstuetzter Regeln statt freier Formelsprache."""

    PERCENTAGE_OF_MEASUREMENT = "percentage_of_measurement"
    EXCESS_OVER_BASIS = "excess_over_basis"
    FIXED_QUANTITY = "fixed_quantity"
    ABSOLUTE_PER_TONNE = "absolute_per_tonne"
    PERCENTAGE_OF_PRICE = "percentage_of_price"
    FIXED_AMOUNT = "fixed_amount"
    TIERED = "tiered"
    REVIEW_REQUIRED = "review_required"
    REJECT = "reject"


class RuleDirection(str, Enum):
    DEDUCTION = "deduction"
    SURCHARGE = "surcharge"


class QuantityReference(str, Enum):
    GROSS_QUANTITY = "gross_quantity"
    REMAINING_QUANTITY = "remaining_quantity"
    SETTLEMENT_QUANTITY = "settlement_quantity"


class PriceReference(str, Enum):
    BASE_PRICE = "base_price"
    RUNNING_PRICE = "running_price"


class SettlementStatus(str, Enum):
    CALCULATED = "calculated"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RoundingPolicy:
    quantity_kg: Decimal = Decimal("0.001")
    price_per_tonne: Decimal = Decimal("0.01")
    money: Decimal = Decimal("0.01")
    mode: str = ROUND_HALF_UP

    def __post_init__(self) -> None:
        for name in ("quantity_kg", "price_per_tonne", "money"):
            value = decimal_value(getattr(self, name))
            if value <= ZERO:
                raise GrainValidationError(
                    f"Rundungsschritt {name} muss groesser als null sein."
                )
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class QualityFeature:
    code: str
    label: str
    unit: str = "%"
    required: bool = True

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise GrainValidationError("Qualitaetsmerkmal benoetigt einen Code.")
        if not self.label.strip():
            raise GrainValidationError("Qualitaetsmerkmal benoetigt eine Bezeichnung.")


@dataclass(frozen=True)
class QualityMeasurement:
    feature_code: str
    raw_value: Decimal
    corrected_value: Decimal | None = None
    correction_reason: str = ""

    def __post_init__(self) -> None:
        if not self.feature_code.strip():
            raise GrainValidationError("Analysewert benoetigt einen Merkmalscode.")
        object.__setattr__(self, "raw_value", decimal_value(self.raw_value))
        if self.corrected_value is not None:
            object.__setattr__(
                self,
                "corrected_value",
                decimal_value(self.corrected_value),
            )

    @property
    def effective_value(self) -> Decimal:
        return (
            self.corrected_value
            if self.corrected_value is not None
            else self.raw_value
        )


@dataclass(frozen=True)
class RuleTier:
    value: Decimal
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None
    lower_inclusive: bool = True
    upper_inclusive: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", decimal_value(self.value))
        if self.lower_bound is not None:
            object.__setattr__(
                self,
                "lower_bound",
                decimal_value(self.lower_bound),
            )
        if self.upper_bound is not None:
            object.__setattr__(
                self,
                "upper_bound",
                decimal_value(self.upper_bound),
            )
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound >= self.upper_bound
        ):
            raise GrainValidationError(
                "Untere Staffelgrenze muss kleiner als die obere sein."
            )


@dataclass(frozen=True)
class SettlementRule:
    """Eine editierbare Regeldefinition mit einem bekannten Regeltyp.

    ``parameters`` nimmt nur die Parameter des jeweiligen ``kind`` auf. Die
    Engine validiert diese, sobald der Regeltyp ausgefuehrt wird. Damit bleiben
    Werte und Staffeln aenderbar, ohne beliebigen Python-Code oder eine freie
    Formelsprache zu speichern.
    """

    code: str
    label: str
    phase: RulePhase
    kind: RuleKind
    order: int = 0
    feature_code: str | None = None
    direction: RuleDirection = RuleDirection.DEDUCTION
    quantity_reference: QuantityReference | None = None
    price_reference: PriceReference | None = None
    parameters: Mapping[str, object] = field(default_factory=dict)
    tiers: tuple[RuleTier, ...] = ()

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise GrainValidationError("Regel benoetigt einen Code.")
        if not self.label.strip():
            raise GrainValidationError("Regel benoetigt eine Bezeichnung.")
        if self.order < 0:
            raise GrainValidationError("Regelreihenfolge darf nicht negativ sein.")
        object.__setattr__(self, "parameters", _frozen_parameters(self.parameters))
        object.__setattr__(self, "tiers", tuple(self.tiers))


@dataclass(frozen=True)
class SettlementSchemeVersion:
    id: str
    scheme_id: str
    version: int
    name: str
    grain_type_code: str
    quality_features: tuple[QualityFeature, ...] = ()
    rules: tuple[SettlementRule, ...] = ()
    default_base_price_per_tonne: Decimal | None = None
    rounding: RoundingPolicy = field(default_factory=RoundingPolicy)

    def __post_init__(self) -> None:
        for name in ("id", "scheme_id", "name", "grain_type_code"):
            if not str(getattr(self, name)).strip():
                raise GrainValidationError(f"Schemafeld {name} darf nicht leer sein.")
        if self.version < 1:
            raise GrainValidationError("Schema-Version muss mindestens 1 sein.")
        object.__setattr__(self, "quality_features", tuple(self.quality_features))
        object.__setattr__(self, "rules", tuple(self.rules))
        if self.default_base_price_per_tonne is not None:
            price = decimal_value(self.default_base_price_per_tonne)
            if price < ZERO:
                raise GrainValidationError("Basispreis darf nicht negativ sein.")
            object.__setattr__(self, "default_base_price_per_tonne", price)

        feature_codes = [feature.code for feature in self.quality_features]
        if len(feature_codes) != len(set(feature_codes)):
            raise GrainValidationError("Merkmalscodes im Schema muessen eindeutig sein.")
        rule_codes = [rule.code for rule in self.rules]
        if len(rule_codes) != len(set(rule_codes)):
            raise GrainValidationError("Regelcodes im Schema muessen eindeutig sein.")
        unknown_rule_features = sorted(
            {
                rule.feature_code
                for rule in self.rules
                if rule.feature_code is not None
                and rule.feature_code not in feature_codes
            }
        )
        if unknown_rule_features:
            raise GrainValidationError(
                "Regeln verwenden nicht aktive Merkmale: "
                + ", ".join(unknown_rule_features)
            )

    @property
    def ordered_rules(self) -> tuple[SettlementRule, ...]:
        return tuple(
            sorted(
                self.rules,
                key=lambda rule: (rule.phase.calculation_order, rule.order),
            )
        )


@dataclass(frozen=True)
class GrainDelivery:
    id: str
    supplier_number: str
    delivery_date: date
    ticket_number: str
    grain_type_code: str
    gross_quantity_kg: Decimal
    measurements: tuple[QualityMeasurement, ...] = ()
    base_price_per_tonne: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("id", "supplier_number", "ticket_number", "grain_type_code"):
            if not str(getattr(self, name)).strip():
                raise GrainValidationError(f"Lieferfeld {name} darf nicht leer sein.")
        if not isinstance(self.delivery_date, date):
            raise GrainValidationError("Lieferdatum muss ein Datum sein.")
        quantity = decimal_value(self.gross_quantity_kg)
        if quantity <= ZERO:
            raise GrainValidationError("Bruttomenge muss groesser als null sein.")
        object.__setattr__(self, "gross_quantity_kg", quantity)
        object.__setattr__(self, "measurements", tuple(self.measurements))
        if self.base_price_per_tonne is not None:
            price = decimal_value(self.base_price_per_tonne)
            if price < ZERO:
                raise GrainValidationError("Basispreis darf nicht negativ sein.")
            object.__setattr__(self, "base_price_per_tonne", price)

        feature_codes = [value.feature_code for value in self.measurements]
        if len(feature_codes) != len(set(feature_codes)):
            raise GrainValidationError(
                "Je Lieferung darf ein Analysemerkmal nur einmal vorkommen."
            )

    def measurement(self, feature_code: str) -> QualityMeasurement | None:
        return next(
            (
                measurement
                for measurement in self.measurements
                if measurement.feature_code == feature_code
            ),
            None,
        )


@dataclass(frozen=True)
class CalculationStep:
    code: str
    label: str
    category: str
    result: Decimal
    unit: str
    basis: Decimal | None = None
    rule_code: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", decimal_value(self.result))
        if self.basis is not None:
            object.__setattr__(self, "basis", decimal_value(self.basis))
        object.__setattr__(self, "details", _frozen_parameters(self.details))


@dataclass(frozen=True)
class SettlementResult:
    delivery_id: str
    scheme_version_id: str
    gross_quantity_kg: Decimal
    settlement_quantity_kg: Decimal
    base_price_per_tonne: Decimal
    base_amount: Decimal
    net_amount: Decimal
    status: SettlementStatus
    steps: tuple[CalculationStep, ...]
    warnings: tuple[str, ...] = ()
