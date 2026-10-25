"""Deliverables: CSV, a formatted Excel workbook, PNG charts and a one-page HTML report."""
from __future__ import annotations

import base64
import html
import io
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ACCENT = "#2563eb"


def category_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby("category")
              .agg(books=("upc", "count"), avg_price_gbp=("price_gbp", "mean"),
                   avg_rating=("rating", "mean"), units_in_stock=("stock", "sum"))
              .round({"avg_price_gbp": 2, "avg_rating": 2})
              .sort_values("books", ascending=False)
              .reset_index())


def _save(fig, path: Path) -> str:
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def charts(df: pd.DataFrame, summary: pd.DataFrame, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    images = {}

    fig, ax = plt.subplots(figsize=(8, 4.5))
    real = summary[summary["category"] != "Uncategorized"]
    uncategorized = int(summary.loc[summary["category"] == "Uncategorized", "books"].sum())
    top = real.head(12).iloc[::-1]
    ax.barh(top["category"], top["books"], color=ACCENT)
    ax.set_title("Top 12 categories by number of books"
                 + (f" ({uncategorized} uncategorized not shown)" if uncategorized else ""))
    ax.set_xlabel("books")
    ax.spines[["top", "right"]].set_visible(False)
    images["categories"] = _save(fig, out_dir / "top_categories.png")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(df["price_gbp"].dropna(), bins=25, color=ACCENT, edgecolor="white")
    ax.set_title("Price distribution")
    ax.set_xlabel("price (GBP, excl. tax)")
    ax.set_ylabel("books")
    ax.spines[["top", "right"]].set_visible(False)
    images["prices"] = _save(fig, out_dir / "price_distribution.png")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    by_rating = df.groupby("rating")["price_gbp"].mean()
    ax.bar(by_rating.index.astype(int), by_rating.values, color=ACCENT)
    ax.set_xticks(by_rating.index.astype(int))
    ax.set_title("Average price by star rating")
    ax.set_xlabel("stars")
    ax.set_ylabel("avg price (GBP)")
    ax.spines[["top", "right"]].set_visible(False)
    images["ratings"] = _save(fig, out_dir / "price_by_rating.png")
    return images


def write_excel(df: pd.DataFrame, summary: pd.DataFrame, quality: dict, path: Path) -> None:
    quality_rows = [(k, v if not isinstance(v, dict) else ", ".join(f"{a}: {b}" for a, b in v.items()) or "none")
                    for k, v in quality.items()]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.drop(columns=["description"]).to_excel(writer, sheet_name="Books", index=False)
        summary.to_excel(writer, sheet_name="By category", index=False)
        pd.DataFrame(quality_rows, columns=["check", "result"]).to_excel(writer, sheet_name="Data quality", index=False)
        for sheet in writer.sheets.values():
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                width = max(len(str(c.value or "")) for c in column[:200])
                sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 60)


def write_html(df: pd.DataFrame, summary: pd.DataFrame, quality: dict, images: dict, path: Path) -> None:
    e = html.escape
    kpis = [("Books", f"{len(df):,}"), ("Categories", f"{df['category'].nunique()}"),
            ("Avg price", f"£{df['price_gbp'].mean():.2f}"), ("Units in stock", f"{int(df['stock'].sum()):,}")]
    kpi_html = "".join(f'<div class="kpi"><span>{e(k)}</span><b>{e(v)}</b></div>' for k, v in kpis)
    rows = "".join(
        f"<tr><td>{e(r.category)}</td><td>{r.books}</td><td>£{r.avg_price_gbp:.2f}</td>"
        f"<td>{r.avg_rating:.2f}</td><td>{int(r.units_in_stock)}</td></tr>"
        for r in summary.head(15).itertuples())
    checks = "".join(f"<li><b>{e(k.replace('_', ' '))}:</b> {e(str(v or 'none'))}</li>" for k, v in quality.items())
    imgs = "".join(f'<figure><img alt="{e(k)}" src="data:image/png;base64,{v}"></figure>' for k, v in images.items())
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Book Catalogue Report</title>
<style>
 :root {{ --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --accent:{ACCENT}; --bg:#f8fafc; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; color:var(--ink); background:var(--bg); }}
 header {{ background:var(--ink); color:#fff; padding:40px 16px; }}
 header div, main {{ max-width:1040px; margin:0 auto; }}
 header h1 {{ margin:0 0 8px; font-size:clamp(1.6rem,4vw,2.4rem); }}
 header p {{ margin:0; color:#cbd5e1; }}
 main {{ padding:24px 16px 48px; }}
 .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-top:-48px; }}
 .kpi {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:16px; }}
 .kpi span {{ display:block; color:var(--muted); font-size:.85rem; }} .kpi b {{ font-size:1.6rem; }}
 section {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:20px; margin-top:20px; }}
 h2 {{ margin:0 0 12px; font-size:1.15rem; }}
 .charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }}
 figure {{ margin:0; }} img {{ width:100%; height:auto; border:1px solid var(--line); border-radius:8px; }}
 .table-wrap {{ overflow-x:auto; }}
 table {{ width:100%; border-collapse:collapse; font-size:.92rem; }}
 th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }}
 th {{ color:var(--muted); font-weight:600; }}
 footer {{ color:var(--muted); font-size:.85rem; text-align:center; padding:0 16px 32px; }}
</style></head><body>
<header><div><h1>Book Catalogue Report</h1>
<p>Scraped from books.toscrape.com, cleaned with pandas · generated {datetime.now():%Y-%m-%d %H:%M}</p></div></header>
<main>
<div class="kpis">{kpi_html}</div>
<section><h2>Charts</h2><div class="charts">{imgs}</div></section>
<section><h2>Top categories</h2><div class="table-wrap"><table>
<thead><tr><th>Category</th><th>Books</th><th>Avg price</th><th>Avg rating</th><th>In stock</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>
<section><h2>Data quality checks</h2><ul>{checks}</ul></section>
</main>
<footer>Demo project: Python · requests · BeautifulSoup · pandas · matplotlib</footer>
</body></html>"""
    path.write_text(page, encoding="utf-8")


def build(df: pd.DataFrame, quality: dict, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = category_summary(df)
    images = charts(df, summary, out_dir / "charts")
    paths = {"csv": out_dir / "books.csv", "excel": out_dir / "books.xlsx", "html": out_dir / "report.html"}
    df.to_csv(paths["csv"], index=False, encoding="utf-8-sig")
    write_excel(df, summary, quality, paths["excel"])
    write_html(df, summary, quality, images, paths["html"])
    return paths
