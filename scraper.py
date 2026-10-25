"""Polite scraper for books.toscrape.com (a public sandbox site built for scraping practice).

Collects every book from the catalogue listing pages, then visits each product page for the
details that only live there (UPC, stock count, category, review count, tax).
Raw values are stored exactly as found on the page; cleaning happens in clean.py.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://books.toscrape.com/"
LISTING_URL = BASE_URL + "catalogue/page-{page}.html"
USER_AGENT = "books-scraper-demo/1.0 (portfolio project; polite crawl)"

log = logging.getLogger("scraper")


class PoliteSession:
    """requests.Session with retries, a shared minimum delay between requests and a clear User-Agent."""

    def __init__(self, delay: float = 0.3, timeout: float = 20.0):
        self.delay = delay
        self.timeout = timeout
        self._lock = threading.Lock()
        self._last = 0.0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        retry = Retry(total=4, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504))
        self.session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))

    def get_soup(self, url: str) -> BeautifulSoup:
        with self._lock:  # rate limit across all worker threads
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = "utf-8"  # the site serves UTF-8; avoids "Â£" mojibake
        return BeautifulSoup(response.text, "html.parser")


def parse_listing(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """One catalogue page → list of {title, url, price_raw, rating_raw, availability_raw}."""
    books = []
    for card in soup.select("article.product_pod"):
        link = card.select_one("h3 a")
        rating = card.select_one("p.star-rating")
        books.append({
            "title": link.get("title", "").strip(),
            "url": urljoin(page_url, link["href"]),
            "price_raw": card.select_one("p.price_color").get_text(strip=True),
            "rating_raw": next((c for c in rating.get("class", []) if c != "star-rating"), ""),
            "availability_raw": card.select_one("p.availability").get_text(" ", strip=True),
        })
    return books


def parse_product(soup: BeautifulSoup) -> dict:
    """Product page → raw detail fields."""
    table = {row.th.get_text(strip=True): row.td.get_text(strip=True)
             for row in soup.select("table.table-striped tr")}
    crumbs = soup.select("ul.breadcrumb li a")
    description = soup.select_one("#product_description + p")
    return {
        "upc": table.get("UPC", ""),
        "category": crumbs[2].get_text(strip=True) if len(crumbs) >= 3 else "",
        "price_excl_tax_raw": table.get("Price (excl. tax)", ""),
        "price_incl_tax_raw": table.get("Price (incl. tax)", ""),
        "tax_raw": table.get("Tax", ""),
        "stock_raw": table.get("Availability", ""),
        "reviews_raw": table.get("Number of reviews", ""),
        "description": description.get_text(strip=True) if description else "",
    }


def scrape(out_path: Path, max_pages: int = 50, workers: int = 4, delay: float = 0.3) -> int:
    """Scrape listing pages 1..max_pages and all their product pages. Writes JSON Lines; returns row count."""
    client = PoliteSession(delay=delay)
    listing: list[dict] = []
    for page in range(1, max_pages + 1):
        url = LISTING_URL.format(page=page)
        try:
            soup = client.get_soup(url)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                log.info("no page %s — catalogue ends at page %s", page, page - 1)
                break
            raise
        listing.extend(parse_listing(soup, url))
        log.info("listing page %s: %s books so far", page, len(listing))

    def details(book: dict) -> dict:
        try:
            return {**book, **parse_product(client.get_soup(book["url"])), "error": ""}
        except requests.RequestException as exc:  # keep the row; cleaning reports it
            return {**book, "error": f"{type(exc).__name__}: {exc}"}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with ThreadPoolExecutor(max_workers=workers) as pool, open(out_path, "w", encoding="utf-8") as fh:
        for future in as_completed(pool.submit(details, b) for b in listing):
            fh.write(json.dumps(future.result(), ensure_ascii=False) + "\n")
            rows += 1
            if rows % 100 == 0:
                log.info("product pages: %s/%s", rows, len(listing))
    return rows
