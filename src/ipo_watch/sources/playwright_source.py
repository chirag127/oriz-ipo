"""Playwright JS-rendered fallback — last resort when a site guards its table
behind JavaScript (Chittorgarh's per-IPO GMP tabs, some SPA sites).

Only imported/used if the httpx sources all fail AND playwright is installed.
Renders the page, extracts the first table that has a GMP-ish header.
"""

from __future__ import annotations

from ..models import Ipo
from ..util import clean, parse_money, parse_pct
from .base import Source, compute_gmp_pct


class PlaywrightTable(Source):
    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self.url = url

    def fetch(self) -> list[Ipo]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:  # playwright not installed in this env
            raise RuntimeError("playwright not available") from e

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0")
            try:
                page.goto(self.url, wait_until="networkidle", timeout=45000)
                # data tables often hydrate after networkidle; give rows a beat
                try:
                    page.wait_for_selector("table tr td", timeout=8000)
                except Exception:  # noqa: BLE001
                    pass
                tables = page.query_selector_all("table")
                out: list[Ipo] = []
                for t in tables:
                    rows = t.query_selector_all("tr")
                    if len(rows) < 2:
                        continue
                    header = [clean(c.inner_text()).lower() for c in rows[0].query_selector_all("th,td")]
                    if not (any("gmp" in h or "premium" in h for h in header)
                            and any("ipo" in h or "name" in h for h in header)):
                        continue
                    idx = {h: i for i, h in enumerate(header)}

                    def col(cells, *keys):
                        for k in keys:
                            for h, i in idx.items():
                                if k in h and i < len(cells):
                                    return clean(cells[i].inner_text())
                        return ""

                    for row in rows[1:]:
                        cells = row.query_selector_all("td")
                        if len(cells) < 2:
                            continue
                        name = clean(cells[0].inner_text())
                        if not name:
                            continue
                        gmp_cell = col(cells, "gmp", "premium")
                        ipo = Ipo(
                            name=name,
                            gmp=parse_money(gmp_cell),
                            gmp_pct=parse_pct(gmp_cell),
                            price_band=col(cells, "price", "band"),
                            est_listing=col(cells, "est", "listing"),
                            ipo_type=col(cells, "type"),
                            status=col(cells, "status"),
                            source=self.name,
                        )
                        compute_gmp_pct(ipo)
                        out.append(ipo)
                    if out:
                        break
                if not out:
                    raise ValueError(f"{self.name}: playwright found no GMP table")
                return out
            finally:
                browser.close()
