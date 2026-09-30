import unittest

from shop.catalog import page, page_count


class PageCountTests(unittest.TestCase):
    def test_counts_partial_and_full_pages(self):
        self.assertEqual(page_count(list(range(25)), 10), 3)
        self.assertEqual(page_count(list(range(20)), 10), 2)
        self.assertEqual(page_count([], 10), 0)


class PageTests(unittest.TestCase):
    def test_pages_start_at_one(self):
        with self.assertRaises(ValueError):
            page([1, 2, 3], 0)

    def test_size_must_be_positive(self):
        with self.assertRaises(ValueError):
            page([1, 2, 3], 1, 0)

    def test_a_page_past_the_end_is_empty(self):
        self.assertEqual(page(list(range(5)), 3, 10), [])


if __name__ == "__main__":
    unittest.main()
