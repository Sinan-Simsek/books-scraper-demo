"""Offline tests: parsing, cleaning rules and HTML parsing on saved snippets. Run: python -m unittest"""
import sys
import unittest
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clean  # noqa: E402
import scraper  # noqa: E402

LISTING_HTML = """
<article class="product_pod"><h3><a href="a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light...</a></h3>
<p class="star-rating Three"></p><div class="product_price"><p class="price_color">£51.77</p>
<p class="instock availability"><i class="icon-ok"></i> In stock</p></div></article>"""

PRODUCT_HTML = """
<ul class="breadcrumb"><li><a href="/">Home</a></li><li><a href="/books">Books</a></li><li><a href="/poetry">Poetry</a></li><li class="active">A Light in the Attic</li></ul>
<div id="product_description"><h2>Product Description</h2></div><p>It's hard to imagine a world without A Light in the Attic.</p>
<table class="table table-striped">
<tr><th>UPC</th><td>a897fe39b1053632</td></tr><tr><th>Price (excl. tax)</th><td>£51.77</td></tr>
<tr><th>Price (incl. tax)</th><td>£51.77</td></tr><tr><th>Tax</th><td>£0.00</td></tr>
<tr><th>Availability</th><td>In stock (22 available)</td></tr><tr><th>Number of reviews</th><td>0</td></tr></table>"""


class Parsing(unittest.TestCase):
    def test_price(self):
        self.assertEqual(clean.parse_price("£51.77"), 51.77)
        self.assertEqual(clean.parse_price("Â£13.99"), 13.99)
        self.assertEqual(clean.parse_price(" 7,50 "), 7.5)
        self.assertIsNone(clean.parse_price("n/a"))

    def test_rating_and_stock(self):
        self.assertEqual(clean.parse_rating("Three"), 3)
        self.assertIsNone(clean.parse_rating("Ten"))
        self.assertEqual(clean.parse_stock("In stock (22 available)"), 22)
        self.assertEqual(clean.parse_stock("Out of stock"), 0)
        self.assertIsNone(clean.parse_stock("In stock"))

    def test_listing_and_product_pages(self):
        books = scraper.parse_listing(BeautifulSoup(LISTING_HTML, "html.parser"),
                                      "https://books.toscrape.com/catalogue/page-1.html")
        self.assertEqual(books[0]["title"], "A Light in the Attic")
        self.assertEqual(books[0]["url"], "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html")
        self.assertEqual(books[0]["rating_raw"], "Three")
        product = scraper.parse_product(BeautifulSoup(PRODUCT_HTML, "html.parser"))
        self.assertEqual((product["upc"], product["category"], product["stock_raw"]),
                         ("a897fe39b1053632", "Poetry", "In stock (22 available)"))
        self.assertTrue(product["description"].startswith("It's hard"))


class Cleaning(unittest.TestCase):
    def row(self, **over):
        base = {"title": "  A  Book ", "url": "u1", "price_raw": "£10.00", "rating_raw": "Four",
                "availability_raw": "In stock", "upc": "X1", "category": "Poetry",
                "price_excl_tax_raw": "£10.00", "price_incl_tax_raw": "£10.00", "tax_raw": "£0.00",
                "stock_raw": "In stock (3 available)", "reviews_raw": "0", "description": "d", "error": ""}
        return {**base, **over}

    def test_types_duplicates_and_failures(self):
        raw = pd.DataFrame([self.row(), self.row(), self.row(upc="X2", url="u2", error="Timeout"),
                            self.row(upc="X3", url="u3", price_incl_tax_raw="£12.00")])
        df, report = clean.clean(raw)
        self.assertEqual(report["rows_scraped"], 4)
        self.assertEqual(report["rows_failed_download"], 1)
        self.assertEqual(report["duplicates_removed"], 1)
        self.assertEqual(report["price_tax_mismatches"], 1)
        self.assertEqual(len(df), 2)
        first = df.iloc[0]
        self.assertEqual((first["title"], first["price_gbp"], first["rating"], first["stock"]), ("A Book", 10.0, 4, 3))

    def test_placeholder_categories(self):
        raw = pd.DataFrame([self.row(category="Default"), self.row(upc="X2", url="u2", category="Add a comment"),
                            self.row(upc="X3", url="u3", category="Poetry")])
        df, report = clean.clean(raw)
        self.assertEqual(report["placeholder_categories_fixed"], 2)
        self.assertEqual(sorted(df["category"]), ["Poetry", "Uncategorized", "Uncategorized"])


if __name__ == "__main__":
    unittest.main()
