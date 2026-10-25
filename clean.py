"""Turn raw scraped strings into a typed, validated table with pandas."""
from __future__ import annotations

import re

import pandas as pd

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
# The site files some books under placeholder names instead of a real category.
PLACEHOLDER_CATEGORIES = {"default", "add a comment", ""}
UNCATEGORIZED = "Uncategorized"
_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def parse_price(value) -> float | None:
    """'£51.77' / 'Â£51.77' / ' 51,77 ' → 51.77; anything without a number → None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    match = _NUMBER.search(str(value))
    return float(match.group().replace(",", ".")) if match else None


def parse_rating(value) -> int | None:
    """'Three' → 3."""
    return RATING_WORDS.get(str(value).strip().title()) if value else None


def parse_stock(value) -> int | None:
    """'In stock (22 available)' → 22; 'Out of stock' → 0; unknown → None."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    match = re.search(r"\((\d+)\s+available\)", text)
    if match:
        return int(match.group(1))
    if "out of stock" in text:
        return 0
    return None


def parse_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Raw rows → (clean table, data-quality report)."""
    report = {"rows_scraped": int(len(raw))}
    df = raw.copy()
    for col in ("error", "upc", "category", "description", "price_excl_tax_raw", "price_incl_tax_raw",
                "tax_raw", "stock_raw", "reviews_raw"):
        if col not in df:
            df[col] = ""
    df = df.fillna("")

    failed = df["error"].astype(str).str.len() > 0
    report["rows_failed_download"] = int(failed.sum())
    df = df[~failed]

    out = pd.DataFrame({
        "upc": df["upc"].astype(str).str.strip(),
        "title": df["title"].astype(str).str.strip().str.replace(r"\s+", " ", regex=True),
        "category": df["category"].astype(str).str.strip(),
        "price_gbp": df["price_excl_tax_raw"].where(df["price_excl_tax_raw"] != "", df["price_raw"]).map(parse_price),
        "price_incl_tax_gbp": df["price_incl_tax_raw"].map(parse_price),
        "tax_gbp": df["tax_raw"].map(parse_price),
        "rating": df["rating_raw"].map(parse_rating),
        "stock": df["stock_raw"].where(df["stock_raw"] != "", df["availability_raw"]).map(parse_stock),
        "reviews": df["reviews_raw"].map(parse_int),
        "url": df["url"],
        "description": df["description"].astype(str).str.strip(),
    })

    placeholder = out["category"].str.lower().isin(PLACEHOLDER_CATEGORIES)
    report["placeholder_categories_fixed"] = int(placeholder.sum())
    out.loc[placeholder, "category"] = UNCATEGORIZED

    missing_upc = out["upc"] == ""
    out.loc[missing_upc, "upc"] = out.loc[missing_upc, "url"]  # fall back to URL as the key
    before = len(out)
    out = out.drop_duplicates(subset="upc", keep="first")
    report["duplicates_removed"] = int(before - len(out))

    tax_mismatch = (out["price_incl_tax_gbp"].notna() & out["price_gbp"].notna() & out["tax_gbp"].notna()
                    & ((out["price_gbp"] + out["tax_gbp"] - out["price_incl_tax_gbp"]).abs() > 0.01))
    report["price_tax_mismatches"] = int(tax_mismatch.sum())
    report["missing_values"] = {c: int(n) for c, n in out.isna().sum().items() if n}
    report["rows_clean"] = int(len(out))

    out = out.astype({"rating": "Int64", "stock": "Int64", "reviews": "Int64"})
    out = out.sort_values(["category", "title"]).reset_index(drop=True)
    return out, report
