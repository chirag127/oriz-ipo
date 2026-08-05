"""Subscription + issue-size enrichment (best-effort).

Subscription (times subscribed, category-wise) and issue size are NOT on the
GMP pages — they live on separate, JS-rendered pages. We render the
InvestorGain subscription report with Playwright (retrying the flaky launch),
match rows to our picks by fuzzy name, and fill sub_total/qib/nii/retail +
issue_size. Everything here is best-effort: on any failure the fields stay
None and the pipeline continues (verified-source rule: we parse the real DOM,
we never fabricate numbers).
"""

from __future__ import annotations

import logging
import re
import time

from ..models import Ipo
from ..util import clean, parse_money

log = logging.getLogger("ipo_watch")

SUBS_URL = "https://www.investorgain.com/report/ipo-subscription-live/333/"


def _norm(name: str) -> str:
    """Loose key for matching names across sources."""
    n = re.sub(r"\b(ltd|limited|ipo|mainboard|sme|nse|bse|eq)\b", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", n)


def _to_times(text: str) -> float | None:
    """'12.45x' / '12.45' / '12.45 times' -> 12.45."""
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def _render_rows() -> list[list[str]]:
    """Playwright-render the subscription table -> list of [header?...] rows.
    Returns [] on any failure (flaky driver, no table, etc.)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        log.info("playwright unavailable for subscription: %s", e)
        return []

    launch_args = ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
    with sync_playwright() as p:
        browser = None
        for attempt in range(3):
            try:
                browser = p.chromium.launch(headless=True, args=launch_args)
                break
            except Exception as e:  # noqa: BLE001
                log.info("subscription playwright launch retry %d: %s", attempt, e)
                time.sleep(2)
        if browser is None:
            return []
        try:
            page = browser.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0")
            page.goto(SUBS_URL, wait_until="networkidle", timeout=45000)
            try:
                page.wait_for_selector("table tr td", timeout=10000)
            except Exception:  # noqa: BLE001
                pass
            for t in page.query_selector_all("table"):
                rows = t.query_selector_all("tr")
                if len(rows) < 2:
                    continue
                header = [clean(c.inner_text()).lower() for c in rows[0].query_selector_all("th,td")]
                if not any("subscri" in h or "times" in h or "qib" in h for h in header):
                    continue
                out = [header]
                for row in rows[1:]:
                    out.append([clean(c.inner_text()) for c in row.query_selector_all("td")])
                return out
            return []
        finally:
            browser.close()


def enrich_subscription(picks: list[Ipo]) -> int:
    """Fill sub_* + issue_size on picks from the subscription report. Best-effort.
    Returns how many picks were enriched."""
    if not picks:
        return 0
    rows = _render_rows()
    if not rows:
        log.info("subscription: no data rendered (skipped)")
        return 0
    header, *data = rows
    idx = {h: i for i, h in enumerate(header)}

    def col(cells: list[str], *keys: str) -> str:
        for k in keys:
            for h, i in idx.items():
                if k in h and i < len(cells):
                    return cells[i]
        return ""

    by_name = {_norm(row[0]): row for row in data if row}
    n = 0
    for ipo in picks:
        row = by_name.get(_norm(ipo.name))
        if not row:
            # loose contains-match fallback
            key = _norm(ipo.name)
            row = next((r for k, r in by_name.items() if key and (key in k or k in key)), None)
        if not row:
            continue
        ipo.sub_total = _to_times(col(row, "total", "times", "sub"))
        ipo.sub_qib = _to_times(col(row, "qib"))
        ipo.sub_nii = _to_times(col(row, "nii", "hni", "non institutional"))
        ipo.sub_retail = _to_times(col(row, "retail", "rii"))
        size = col(row, "issue size", "size")
        if size:
            ipo.issue_size = size
        n += 1
    log.info("subscription: enriched %d/%d picks", n, len(picks))
    return n
