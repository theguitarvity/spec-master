import unittest

from shop.prices import apply_discount, format_brl


class FormatTests(unittest.TestCase):
    def test_formats_reais_and_centavos(self):
        self.assertEqual(format_brl(123456), "R$ 1.234,56")
        self.assertEqual(format_brl(5), "R$ 0,05")
        self.assertEqual(format_brl(-990), "-R$ 9,90")


class DiscountTests(unittest.TestCase):
    def test_rounds_to_the_nearest_centavo(self):
        self.assertEqual(apply_discount(1999, 10), 1799)
        self.assertEqual(apply_discount(1000, 0), 1000)
        self.assertEqual(apply_discount(1000, 100), 0)

    def test_rejects_discounts_outside_the_range(self):
        with self.assertRaises(ValueError):
            apply_discount(1000, 101)


if __name__ == "__main__":
    unittest.main()
