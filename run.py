"""End-to-end pipeline: scrape -> clean -> deliverables.

    python run.py                 # full catalogue (~1,000 books, ~5 minutes at the default polite delay)
    python run.py --pages 3       # quick sample
    python run.py --skip-scrape   # rebuild outputs from data/raw_books.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

import clean
import report
import scraper

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw_books.jsonl"
OUT = ROOT / "output"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=int, default=50, help="listing pages to scrape (20 books each)")
    parser.add_argument("--workers", type=int, default=4, help="parallel product-page downloads")
    parser.add_argument("--delay", type=float, default=0.3, help="minimum seconds between requests")
    parser.add_argument("--skip-scrape", action="store_true", help="reuse the existing raw file")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    started = time.monotonic()
    if not args.skip_scrape:
        rows = scraper.scrape(RAW, max_pages=args.pages, workers=args.workers, delay=args.delay)
        logging.info("scraped %s rows -> %s", rows, RAW.relative_to(ROOT))
    raw = pd.read_json(RAW, lines=True, dtype=False)
    df, quality = clean.clean(raw)
    logging.info("data quality: %s", json.dumps(quality))
    paths = report.build(df, quality, OUT)
    for kind, path in paths.items():
        logging.info("%-5s -> %s", kind, path.relative_to(ROOT))
    logging.info("done in %.1fs", time.monotonic() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
