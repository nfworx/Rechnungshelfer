"""Editierbarer Prüfentwurf und rechnerische Kontrolle von Abrechnungen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from rechnungshelfer.services.format_service import parse_de


_CENT = Decimal("0.01")


@dataclass(frozen=True)
class ReviewField:
    value: str
    source: str = ""
    page_number: int | None = None
    confidence: float | None = None

    def with_value(self, value: str) -> "ReviewField":
        return replace(self, value=str(value))


@dataclass(frozen=True)
class SettlementReviewDetail:
    label: ReviewField
    analysis_value: ReviewField
    quantity_change_kg: ReviewField
    price_change_per_tonne: ReviewField


@dataclass(frozen=True)
class SettlementReviewDelivery:
    ticket_number: ReviewField
    delivery_date: ReviewField
    grain_name: ReviewField
    gross_quantity_kg: ReviewField
    base_price_per_tonne: ReviewField
    settlement_quantity_kg: ReviewField
    settlement_price_per_tonne: ReviewField
    net_amount: ReviewField
    details: tuple[SettlementReviewDetail, ...] = ()


@dataclass(frozen=True)
class SettlementReview:
    credit_note_number: ReviewField
    credit_note_date: ReviewField
    deliveries: tuple[SettlementReviewDelivery, ...]
    vat_rate: ReviewField
    net_amount: ReviewField
    vat_amount: ReviewField
    total_amount: ReviewField
    advance_payment: ReviewField
    credit_amount: ReviewField


@dataclass(frozen=True)
class SettlementReviewIssue:
    field_path: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class SettlementReviewResult:
    issues: tuple[SettlementReviewIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


class SettlementReviewService:
    def create_review(self, draft) -> SettlementReview:
        return SettlementReview(
            credit_note_number=self._field(draft.credit_note_number),
            credit_note_date=self._field(draft.credit_note_date, date_value=True),
            deliveries=tuple(
                SettlementReviewDelivery(
                    ticket_number=self._field(delivery.ticket_number),
                    delivery_date=self._field(delivery.delivery_date, date_value=True),
                    grain_name=self._field(delivery.grain_name),
                    gross_quantity_kg=self._field(delivery.gross_quantity_kg),
                    base_price_per_tonne=self._field(delivery.base_price_per_tonne),
                    settlement_quantity_kg=self._field(
                        delivery.settlement_quantity_kg
                    ),
                    settlement_price_per_tonne=self._field(
                        delivery.settlement_price_per_tonne
                    ),
                    net_amount=self._field(delivery.net_amount),
                    details=tuple(
                        SettlementReviewDetail(
                            label=self._field(detail.label),
                            analysis_value=self._field(detail.analysis_value),
                            quantity_change_kg=self._field(
                                detail.quantity_change_kg
                            ),
                            price_change_per_tonne=self._field(
                                detail.price_change_per_tonne
                            ),
                        )
                        for detail in delivery.details
                    ),
                )
                for delivery in draft.deliveries
            ),
            vat_rate=self._field(draft.vat_rate),
            net_amount=self._field(draft.net_amount),
            vat_amount=self._field(draft.vat_amount),
            total_amount=self._field(draft.total_amount),
            advance_payment=self._field(draft.advance_payment, default="0"),
            credit_amount=self._field(draft.credit_amount),
        )

    def validate(self, review: SettlementReview) -> SettlementReviewResult:
        issues: list[SettlementReviewIssue] = []
        self._required_text(
            review.credit_note_number,
            "credit_note_number",
            "Gutschriftnummer",
            issues,
        )
        self._date(
            review.credit_note_date,
            "credit_note_date",
            "Ausstellungsdatum",
            issues,
        )
        if not review.deliveries:
            issues.append(
                SettlementReviewIssue("deliveries", "Mindestens eine Lieferung fehlt.")
            )

        delivery_amounts: list[Decimal] = []
        for index, delivery in enumerate(review.deliveries):
            prefix = f"deliveries.{index}"
            self._required_text(
                delivery.ticket_number,
                f"{prefix}.ticket_number",
                "Lieferscheinnummer",
                issues,
            )
            self._date(
                delivery.delivery_date,
                f"{prefix}.delivery_date",
                "Lieferdatum",
                issues,
            )
            self._required_text(
                delivery.grain_name,
                f"{prefix}.grain_name",
                "Bezeichnung",
                issues,
            )
            gross = self._number(
                delivery.gross_quantity_kg,
                f"{prefix}.gross_quantity_kg",
                "Ursprungsmenge",
                issues,
                positive=True,
            )
            base_price = self._number(
                delivery.base_price_per_tonne,
                f"{prefix}.base_price_per_tonne",
                "Basispreis",
                issues,
                non_negative=True,
            )
            settlement_quantity = self._number(
                delivery.settlement_quantity_kg,
                f"{prefix}.settlement_quantity_kg",
                "Abrechnungsmenge",
                issues,
                positive=True,
            )
            settlement_price = self._number(
                delivery.settlement_price_per_tonne,
                f"{prefix}.settlement_price_per_tonne",
                "Abrechnungspreis",
                issues,
                non_negative=True,
            )
            amount = self._number(
                delivery.net_amount,
                f"{prefix}.net_amount",
                "Lieferbetrag",
                issues,
                non_negative=True,
            )
            if amount is not None:
                delivery_amounts.append(amount)
            if (
                gross is not None
                and settlement_quantity is not None
                and settlement_quantity > gross
            ):
                issues.append(
                    SettlementReviewIssue(
                        f"{prefix}.settlement_quantity_kg",
                        "Abrechnungsmenge ist größer als die Ursprungsmenge.",
                    )
                )
            if (
                settlement_quantity is not None
                and settlement_price is not None
                and amount is not None
            ):
                expected = self._money(
                    settlement_quantity * settlement_price / Decimal("1000")
                )
                if self._money(amount) != expected:
                    issues.append(
                        SettlementReviewIssue(
                            f"{prefix}.net_amount",
                            f"Lieferbetrag stimmt rechnerisch nicht; erwartet {expected} EUR.",
                        )
                    )
            if base_price is not None and settlement_price is not None:
                if settlement_price > base_price:
                    issues.append(
                        SettlementReviewIssue(
                            f"{prefix}.settlement_price_per_tonne",
                            "Abrechnungspreis ist größer als der Basispreis.",
                            severity="warning",
                        )
                    )
            quantity_changes: list[Decimal] = []
            price_changes: list[Decimal] = []
            quantity_changes_valid = True
            price_changes_valid = True
            for detail_index, detail in enumerate(delivery.details):
                detail_prefix = f"{prefix}.details.{detail_index}"
                self._required_text(
                    detail.label,
                    f"{detail_prefix}.label",
                    "Analysebezeichnung",
                    issues,
                )
                self._number(
                    detail.analysis_value,
                    f"{detail_prefix}.analysis_value",
                    "Analysewert",
                    issues,
                )
                if not (
                    detail.quantity_change_kg.value.strip()
                    or detail.price_change_per_tonne.value.strip()
                ):
                    issues.append(
                        SettlementReviewIssue(
                            f"{detail_prefix}.quantity_change_kg",
                            "Analysezeile benötigt eine Mengen- oder Preisänderung.",
                        )
                    )
                for field_name, field, label, values in (
                    (
                        "quantity_change_kg",
                        detail.quantity_change_kg,
                        "Mengenänderung",
                        quantity_changes,
                    ),
                    (
                        "price_change_per_tonne",
                        detail.price_change_per_tonne,
                        "Preisänderung",
                        price_changes,
                    ),
                ):
                    if field.value.strip():
                        change = self._number(
                            field,
                            f"{detail_prefix}.{field_name}",
                            label,
                            issues,
                        )
                        if change is None:
                            if field_name == "quantity_change_kg":
                                quantity_changes_valid = False
                            else:
                                price_changes_valid = False
                        else:
                            values.append(change)

            if (
                gross is not None
                and settlement_quantity is not None
                and quantity_changes_valid
            ):
                expected_quantity = gross + sum(quantity_changes, Decimal("0"))
                if settlement_quantity != expected_quantity:
                    issues.append(
                        SettlementReviewIssue(
                            f"{prefix}.settlement_quantity_kg",
                            "Abrechnungsmenge stimmt nicht mit Ursprungsmenge "
                            f"und Mengenänderungen überein; erwartet {expected_quantity} kg.",
                        )
                    )
            if (
                base_price is not None
                and settlement_price is not None
                and price_changes_valid
            ):
                expected_price = base_price + sum(price_changes, Decimal("0"))
                if settlement_price != expected_price:
                    issues.append(
                        SettlementReviewIssue(
                            f"{prefix}.settlement_price_per_tonne",
                            "Abrechnungspreis stimmt nicht mit Basispreis und "
                            f"Preisänderungen überein; erwartet {expected_price} EUR/t.",
                        )
                    )

        vat_rate = self._number(
            review.vat_rate,
            "vat_rate",
            "Steuersatz",
            issues,
            non_negative=True,
        )
        net = self._number(
            review.net_amount,
            "net_amount",
            "Nettosumme",
            issues,
            non_negative=True,
        )
        vat = self._number(
            review.vat_amount,
            "vat_amount",
            "Umsatzsteuerbetrag",
            issues,
            non_negative=True,
        )
        total = self._number(
            review.total_amount,
            "total_amount",
            "Gesamtbetrag",
            issues,
            non_negative=True,
        )
        advance = self._number(
            review.advance_payment,
            "advance_payment",
            "Abschlagszahlung",
            issues,
            non_negative=True,
        )
        credit = self._number(
            review.credit_amount,
            "credit_amount",
            "Gutschriftbetrag",
            issues,
            non_negative=True,
        )

        if net is not None and len(delivery_amounts) == len(review.deliveries):
            expected_net = self._money(sum(delivery_amounts, Decimal("0")))
            if self._money(net) != expected_net:
                issues.append(
                    SettlementReviewIssue(
                        "net_amount",
                        f"Nettosumme stimmt nicht mit den Lieferbeträgen überein; erwartet {expected_net} EUR.",
                    )
                )
        if net is not None and vat_rate is not None and vat is not None:
            expected_vat = self._money(net * vat_rate / Decimal("100"))
            if self._money(vat) != expected_vat:
                issues.append(
                    SettlementReviewIssue(
                        "vat_amount",
                        f"Umsatzsteuer stimmt rechnerisch nicht; erwartet {expected_vat} EUR.",
                    )
                )
        if net is not None and vat is not None and total is not None:
            expected_total = self._money(net + vat)
            if self._money(total) != expected_total:
                issues.append(
                    SettlementReviewIssue(
                        "total_amount",
                        f"Gesamtbetrag stimmt rechnerisch nicht; erwartet {expected_total} EUR.",
                    )
                )
        if total is not None and advance is not None and credit is not None:
            expected_credit = self._money(total - advance)
            if self._money(credit) != expected_credit:
                issues.append(
                    SettlementReviewIssue(
                        "credit_amount",
                        f"Gutschriftbetrag stimmt rechnerisch nicht; erwartet {expected_credit} EUR.",
                    )
                )
        return SettlementReviewResult(tuple(issues))

    @staticmethod
    def _field(detected, *, date_value=False, default="") -> ReviewField:
        if detected is None:
            return ReviewField(default)
        value = detected.value
        if date_value and hasattr(value, "strftime"):
            rendered = value.strftime("%d.%m.%Y")
        else:
            rendered = format(value, "f") if isinstance(value, Decimal) else str(value)
            rendered = rendered.replace(".", ",") if isinstance(value, Decimal) else rendered
        return ReviewField(
            value=rendered,
            source=detected.raw_text,
            page_number=detected.page_number,
            confidence=detected.confidence,
        )

    @staticmethod
    def _required_text(field, path, label, issues):
        if not field.value.strip():
            issues.append(SettlementReviewIssue(path, f"{label} fehlt."))

    @staticmethod
    def _date(field, path, label, issues):
        if not field.value.strip():
            issues.append(SettlementReviewIssue(path, f"{label} fehlt."))
            return None
        try:
            return datetime.strptime(field.value.strip(), "%d.%m.%Y").date()
        except ValueError:
            issues.append(SettlementReviewIssue(path, f"{label} ist ungültig."))
            return None

    @staticmethod
    def _number(
        field,
        path,
        label,
        issues,
        *,
        positive=False,
        non_negative=False,
    ):
        if not field.value.strip():
            issues.append(SettlementReviewIssue(path, f"{label} fehlt."))
            return None
        try:
            value = parse_de(field.value)
        except ValueError:
            issues.append(SettlementReviewIssue(path, f"{label} ist ungültig."))
            return None
        if positive and value <= 0:
            issues.append(
                SettlementReviewIssue(path, f"{label} muss größer als null sein.")
            )
        elif non_negative and value < 0:
            issues.append(
                SettlementReviewIssue(path, f"{label} darf nicht negativ sein.")
            )
        return value

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(_CENT, rounding=ROUND_HALF_UP)


__all__ = [
    "ReviewField",
    "SettlementReview",
    "SettlementReviewDelivery",
    "SettlementReviewDetail",
    "SettlementReviewIssue",
    "SettlementReviewResult",
    "SettlementReviewService",
]
