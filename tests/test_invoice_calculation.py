import unittest
from decimal import Decimal

from models import (
    Buyer,
    CalculationMode,
    Delivery,
    Invoice,
    InvoiceInfo,
    InvoiceItem,
    Payment,
    Seller,
)
from rechnungshelfer.domain.calculation import (
    TaxLine,
    calculate_invoice,
    calculate_line,
)


class InvoiceCalculationTests(unittest.TestCase):
    @staticmethod
    def _invoice(items):
        return Invoice(
            seller=Seller(),
            buyer=Buyer(),
            delivery=Delivery(),
            info=InvoiceInfo(),
            payment=Payment(),
            items=items,
        )

    def test_line_discount_and_quantity_are_calculated(self):
        result = calculate_line("12.345", "2.00", "3")

        self.assertEqual(result.price, Decimal("10.35"))
        self.assertEqual(result.net, Decimal("31.05"))

    def test_discount_cannot_make_price_negative(self):
        result = calculate_line("5.00", "8.00", "2")

        self.assertEqual(result.price, Decimal("0.00"))
        self.assertEqual(result.net, Decimal("0.00"))

    def test_tax_is_rounded_after_the_whole_group_is_summed(self):
        result = calculate_invoice(
            [
                TaxLine(Decimal("0.03"), Decimal("19.00"), "S"),
                TaxLine(Decimal("0.03"), Decimal("19.00"), "S"),
            ]
        )

        self.assertEqual(result.tax_groups[0].amount, Decimal("0.01"))
        self.assertEqual(result.payable_amount, Decimal("0.07"))

    def test_tax_rates_are_grouped_and_zero_rate_uses_category_z(self):
        result = calculate_invoice(
            [
                TaxLine(Decimal("100.00"), Decimal("19.00"), "S"),
                TaxLine(Decimal("50.00"), Decimal("7.00"), "S"),
                TaxLine(Decimal("20.00"), Decimal("0.00"), "S"),
            ]
        )

        self.assertEqual(result.tax_categories, ("S", "S", "Z"))
        self.assertEqual(
            [(group.percent, group.amount) for group in result.tax_groups],
            [
                (Decimal("19.00"), Decimal("19.00")),
                (Decimal("7.00"), Decimal("3.50")),
                (Decimal("0.00"), Decimal("0.00")),
            ],
        )
        self.assertEqual(result.line_extension_amount, Decimal("170.00"))
        self.assertEqual(result.tax_inclusive_amount, Decimal("192.50"))
        self.assertEqual(result.payable_amount, Decimal("192.50"))

    def test_empty_invoice_has_zero_totals(self):
        result = calculate_invoice([])

        self.assertEqual(result.tax_groups, ())
        self.assertEqual(result.line_extension_amount, Decimal("0.00"))
        self.assertEqual(result.payable_amount, Decimal("0.00"))

    def test_imported_invoice_is_unchanged_without_force(self):
        invoice = self._invoice(
            [InvoiceItem(pos="1", qty="1", price_without_discount="10.00")]
        )
        invoice.calculation_mode = CalculationMode.IMPORTED
        invoice.items[0].price_without_discount = Decimal("20.00")
        invoice.monetarytotal.payable_amount = Decimal("123.45")

        invoice.calculate()

        self.assertEqual(invoice.items[0].price, Decimal("10.00"))
        self.assertEqual(invoice.monetarytotal.payable_amount, Decimal("123.45"))

    def test_force_recalculates_imported_invoice(self):
        invoice = self._invoice(
            [InvoiceItem(pos="1", qty="2", price_without_discount="10.00", vat="19.00")]
        )
        invoice.calculation_mode = CalculationMode.IMPORTED
        invoice.items[0].price_without_discount = Decimal("20.00")

        invoice.calculate(force=True)

        self.assertEqual(invoice.items[0].net, Decimal("40.00"))
        self.assertEqual(invoice.taxtotal[0].amount, Decimal("7.60"))
        self.assertEqual(invoice.monetarytotal.payable_amount, Decimal("47.60"))
        self.assertEqual(invoice.calculation_mode, CalculationMode.AUTO)


if __name__ == "__main__":
    unittest.main()
