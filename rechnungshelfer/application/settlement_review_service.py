"""Editierbarer Prüfentwurf und rechnerische Kontrolle von Abrechnungen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from rechnungshelfer.application.grain_credit_note_mapper import (
    grain_credit_note_from_review,
)
from rechnungshelfer.domain.grain_credit_note import (
    GrainCreditNoteBuyer,
    GrainRuleCheck,
    GrainRuleDeviation,
)
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
    amount_change: ReviewField = ReviewField("")
    rule_deviation: GrainRuleDeviation | None = None


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
    grain_type_code: str = ""
    rule_check: GrainRuleCheck = GrainRuleCheck()


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
    supplier_number: ReviewField = ReviewField("")
    supplier_name: ReviewField = ReviewField("")
    supplier_street: ReviewField = ReviewField("")
    supplier_postcode: ReviewField = ReviewField("")
    supplier_city: ReviewField = ReviewField("")
    supplier_country: ReviewField = ReviewField("")
    supplier_phone: ReviewField = ReviewField("")
    supplier_email: ReviewField = ReviewField("")
    supplier_vat: ReviewField = ReviewField("")
    supplier_tax_number: ReviewField = ReviewField("")
    supplier_registry_number: ReviewField = ReviewField("")
    supplier_contact_name: ReviewField = ReviewField("")
    supplier_buyer_reference: ReviewField = ReviewField("")
    iban: ReviewField = ReviewField("")
    bic: ReviewField = ReviewField("")
    account_holder: ReviewField = ReviewField("")
    payment_terms: ReviewField = ReviewField("")
    buyer: GrainCreditNoteBuyer = GrainCreditNoteBuyer()
    payment_due_date: ReviewField = ReviewField("")
    origin: str = "manual"


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
                            amount_change=ReviewField(""),
                        )
                        for detail in delivery.details
                    ),
                    grain_type_code=getattr(delivery, "grain_type_code", ""),
                )
                for delivery in draft.deliveries
            ),
            vat_rate=self._field(draft.vat_rate),
            net_amount=self._field(draft.net_amount),
            vat_amount=self._field(draft.vat_amount),
            total_amount=self._field(draft.total_amount),
            advance_payment=self._field(draft.advance_payment, default="0"),
            credit_amount=self._field(draft.credit_amount),
            supplier_number=self._field(draft.supplier_number),
            supplier_name=self._field(draft.supplier_name),
            supplier_street=self._field(draft.supplier_street),
            supplier_postcode=self._field(draft.supplier_postcode),
            supplier_city=self._field(draft.supplier_city),
            supplier_country=self._field(draft.supplier_country),
            supplier_phone=self._field(draft.supplier_phone),
            supplier_email=self._field(draft.supplier_email),
            supplier_vat=self._field(draft.supplier_vat),
            supplier_tax_number=self._field(draft.supplier_tax_number),
            supplier_registry_number=self._field(draft.supplier_registry_number),
            supplier_contact_name=self._field(draft.supplier_contact_name),
            supplier_buyer_reference=self._field(draft.supplier_buyer_reference),
            iban=self._field(draft.iban),
            bic=self._field(draft.bic),
            account_holder=self._field(draft.account_holder),
            payment_terms=self._field(draft.payment_terms),
            buyer=GrainCreditNoteBuyer(),
            payment_due_date=ReviewField(""),
            origin="pdf_import",
        )

    def create_review_from_credit_note(self, credit_note) -> SettlementReview:
        field = self._plain_field
        return SettlementReview(
            credit_note_number=field(credit_note.credit_note_number),
            credit_note_date=field(credit_note.credit_note_date, date_value=True),
            deliveries=tuple(
                SettlementReviewDelivery(
                    ticket_number=field(delivery.ticket_number),
                    delivery_date=field(delivery.delivery_date, date_value=True),
                    grain_name=field(delivery.grain_name),
                    gross_quantity_kg=field(delivery.gross_quantity_kg),
                    base_price_per_tonne=field(delivery.base_price_per_tonne),
                    settlement_quantity_kg=field(
                        delivery.settlement_quantity_kg
                    ),
                    settlement_price_per_tonne=field(
                        delivery.settlement_price_per_tonne
                    ),
                    net_amount=field(delivery.net_amount),
                    details=tuple(
                        SettlementReviewDetail(
                            label=field(detail.label),
                            analysis_value=field(detail.analysis_value),
                            quantity_change_kg=field(detail.quantity_change_kg),
                            price_change_per_tonne=field(
                                detail.price_change_per_tonne
                            ),
                            amount_change=field(detail.amount_change),
                            rule_deviation=detail.rule_deviation,
                        )
                        for detail in delivery.details
                    ),
                    grain_type_code=delivery.grain_type_code,
                    rule_check=delivery.rule_check,
                )
                for delivery in credit_note.deliveries
            ),
            vat_rate=field(credit_note.vat_rate),
            net_amount=field(credit_note.net_amount),
            vat_amount=field(credit_note.vat_amount),
            total_amount=field(credit_note.total_amount),
            advance_payment=field(credit_note.advance_payment),
            credit_amount=field(credit_note.credit_amount),
            supplier_number=field(credit_note.supplier.supplier_number),
            supplier_name=field(credit_note.supplier.name),
            supplier_street=field(credit_note.supplier.street),
            supplier_postcode=field(credit_note.supplier.postcode),
            supplier_city=field(credit_note.supplier.city),
            supplier_country=field(credit_note.supplier.country),
            supplier_phone=field(credit_note.supplier.phone),
            supplier_email=field(credit_note.supplier.email),
            supplier_vat=field(credit_note.supplier.vat),
            supplier_tax_number=field(credit_note.supplier.tax_number),
            supplier_registry_number=field(credit_note.supplier.registry_number),
            supplier_contact_name=field(credit_note.supplier.contact_name),
            supplier_buyer_reference=field(credit_note.supplier.buyer_reference),
            iban=field(credit_note.payment.iban),
            bic=field(credit_note.payment.bic),
            account_holder=field(credit_note.payment.account_holder),
            payment_terms=field(credit_note.payment.payment_terms),
            buyer=credit_note.buyer,
            payment_due_date=field(
                credit_note.payment_due_date,
                date_value=True,
            ),
            origin=credit_note.origin,
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
        for field, path, label in (
            (review.supplier_number, "supplier_number", "Lieferantennummer"),
            (review.supplier_name, "supplier_name", "Lieferantenname"),
            (review.supplier_street, "supplier_street", "Strasse"),
            (review.supplier_postcode, "supplier_postcode", "PLZ"),
            (review.supplier_city, "supplier_city", "Ort"),
            (review.supplier_country, "supplier_country", "Land"),
            (review.supplier_email, "supplier_email", "E-Mail"),
            (review.iban, "iban", "IBAN"),
            (review.bic, "bic", "BIC"),
            (review.account_holder, "account_holder", "Kontoinhaber"),
            (review.payment_terms, "payment_terms", "Zahlungsbedingungen"),
        ):
            self._required_text(field, path, label, issues)
        if not review.deliveries:
            issues.append(
                SettlementReviewIssue("deliveries", "Mindestens eine Lieferung fehlt.")
            )

        delivery_amounts: list[Decimal] = []
        for index, delivery in enumerate(review.deliveries):
            prefix = f"deliveries.{index}"
            if delivery.rule_check.status == "unavailable":
                issues.append(
                    SettlementReviewIssue(
                        prefix,
                        delivery.rule_check.note
                        or "Für diese Lieferung wurde kein eindeutiges Regelwerk gefunden; "
                        "es wurden nur die finanziellen Zusammenhänge geprüft.",
                        severity="warning",
                    )
                )
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
            amount_changes: list[Decimal] = []
            quantity_changes_valid = True
            price_changes_valid = True
            for detail_index, detail in enumerate(delivery.details):
                detail_prefix = f"{prefix}.details.{detail_index}"
                if detail.rule_deviation is not None:
                    issues.append(
                        SettlementReviewIssue(
                            f"{detail_prefix}.analysis_value",
                            self._deviation_message(detail.rule_deviation),
                            severity="warning",
                        )
                    )
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
                if detail.amount_change.value.strip():
                    amount_change = self._number(
                        detail.amount_change,
                        f"{detail_prefix}.amount_change",
                        "Betragsänderung",
                        issues,
                    )
                    if amount_change is not None:
                        amount_changes.append(amount_change)

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
            if (
                settlement_quantity is not None
                and settlement_price is not None
                and amount is not None
            ):
                expected = self._money(
                    settlement_quantity * settlement_price / Decimal("1000")
                    + sum(amount_changes, Decimal("0"))
                )
                if self._money(amount) != expected:
                    issues.append(
                        self._financial_difference_issue(
                            f"{prefix}.net_amount",
                            "Lieferbetrag",
                            amount,
                            expected,
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
                    self._financial_difference_issue(
                        "net_amount",
                        "Nettosumme",
                        net,
                        expected_net,
                    )
                )
        if net is not None and vat_rate is not None and vat is not None:
            expected_vat = self._money(net * vat_rate / Decimal("100"))
            if self._money(vat) != expected_vat:
                issues.append(
                    self._financial_difference_issue(
                        "vat_amount",
                        "Umsatzsteuer",
                        vat,
                        expected_vat,
                    )
                )
        if net is not None and vat is not None and total is not None:
            expected_total = self._money(net + vat)
            if self._money(total) != expected_total:
                issues.append(
                    self._financial_difference_issue(
                        "total_amount",
                        "Gesamtbetrag",
                        total,
                        expected_total,
                    )
                )
        if total is not None and advance is not None and credit is not None:
            expected_credit = self._money(total - advance)
            if self._money(credit) != expected_credit:
                issues.append(
                    self._financial_difference_issue(
                        "credit_amount",
                        "Auszahlungsbetrag",
                        credit,
                        expected_credit,
                    )
                )
        return SettlementReviewResult(tuple(issues))

    @classmethod
    def _financial_difference_issue(
        cls,
        field_path: str,
        label: str,
        document_value: Decimal,
        expected_value: Decimal,
    ) -> SettlementReviewIssue:
        document_value = cls._money(document_value)
        expected_value = cls._money(expected_value)
        difference = cls._money(document_value - expected_value)
        return SettlementReviewIssue(
            field_path,
            f"{label} ist rechnerisch nicht schlüssig – "
            f"Belegwert: {cls._format_money(document_value)}; "
            f"Prüfwert: {cls._format_money(expected_value)}; "
            "Differenz (Belegwert − Prüfwert): "
            f"{cls._format_money(difference, signed=True)}.",
        )

    @staticmethod
    def _format_money(value: Decimal, *, signed: bool = False) -> str:
        pattern = "+.2f" if signed else ".2f"
        return f"{format(value, pattern).replace('.', ',')} EUR"

    @staticmethod
    def _deviation_message(deviation: GrainRuleDeviation) -> str:
        comparisons = []
        if deviation.document_quantity_change_kg is not None:
            comparisons.append(
                "Mengenänderung Beleg: "
                f"{deviation.document_quantity_change_kg} kg / Regelwerk: "
                f"{deviation.expected_quantity_change_kg} kg"
            )
        if deviation.document_price_change_per_tonne is not None:
            comparisons.append(
                "Preisänderung Beleg: "
                f"{deviation.document_price_change_per_tonne} EUR/t / Regelwerk: "
                f"{deviation.expected_price_change_per_tonne} EUR/t"
            )
        return "Regelwerksabweichung – " + "; ".join(comparisons)

    def recalculate_financials(self, review: SettlementReview) -> SettlementReview:
        """Berechnet Lieferbetraege und Belegsummen aus den editierbaren Werten."""

        deliveries = []
        delivery_amounts = []
        for delivery in review.deliveries:
            quantity = parse_de(delivery.settlement_quantity_kg.value)
            price = parse_de(delivery.settlement_price_per_tonne.value)
            amount_changes = sum(
                (
                    parse_de(detail.amount_change.value)
                    for detail in delivery.details
                    if detail.amount_change.value.strip()
                ),
                Decimal("0"),
            )
            amount = self._money(
                quantity * price / Decimal("1000") + amount_changes
            )
            delivery_amounts.append(amount)
            deliveries.append(
                replace(
                    delivery,
                    net_amount=delivery.net_amount.with_value(
                        self._decimal_text(amount)
                    ),
                )
            )

        net = self._money(sum(delivery_amounts, Decimal("0")))
        vat_rate = parse_de(review.vat_rate.value)
        vat = self._money(net * vat_rate / Decimal("100"))
        total = self._money(net + vat)
        advance = parse_de(review.advance_payment.value)
        credit = self._money(total - advance)
        return replace(
            review,
            deliveries=tuple(deliveries),
            net_amount=review.net_amount.with_value(self._decimal_text(net)),
            vat_amount=review.vat_amount.with_value(self._decimal_text(vat)),
            total_amount=review.total_amount.with_value(self._decimal_text(total)),
            credit_amount=review.credit_amount.with_value(
                self._decimal_text(credit)
            ),
        )

    def create_credit_note(self, review: SettlementReview):
        result = self.validate(review)
        errors = [issue.message for issue in result.issues if issue.severity == "error"]
        if errors:
            raise ValueError(
                "Die Abrechnung kann noch nicht übernommen werden:\n- "
                + "\n- ".join(errors)
            )
        return grain_credit_note_from_review(review)

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
    def _plain_field(value, *, date_value=False) -> ReviewField:
        if value is None:
            return ReviewField("")
        if date_value and hasattr(value, "strftime"):
            return ReviewField(value.strftime("%d.%m.%Y"))
        rendered = format(value, "f") if isinstance(value, Decimal) else str(value)
        if isinstance(value, Decimal):
            rendered = rendered.replace(".", ",")
        return ReviewField(rendered)

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

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        return format(value, "f").replace(".", ",")


__all__ = [
    "ReviewField",
    "SettlementReview",
    "SettlementReviewDelivery",
    "SettlementReviewDetail",
    "SettlementReviewIssue",
    "SettlementReviewResult",
    "SettlementReviewService",
]
