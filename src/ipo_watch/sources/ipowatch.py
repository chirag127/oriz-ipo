"""IPOWatch — https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/

VERIFIED 2026-11-02 (httpx, server-rendered, no JS needed). Two stacked tables,
each preceded by an <h3> ('Current Mainboard IPO', 'Current SME IPO'); both are
collected. Real header:
  ['Company', 'GMP*', 'Trend', 'Price Band', 'Est. Gain', 'Date']

Pre-Nov-2026 layout (tests/fixtures/ipowatch.html) used 'IPO Name', 'Est. Listing',
'Type' and 'Status' columns; column keys accept both spellings.

KEY QUIRK: the GMP **percentage** lives in the 'Est. Gain' column
(e.g. '₹109 (15.96%)'), NOT the 'GMP*' column ('₹15' = absolute rupees).
Open/Closed now rides in the name cell as a <span> badge, not a Status column.
"""

from __future__ import annotations

from selectolax.lexbor import LexborHTMLParser

from ..models import Ipo
from ..util import clean, fetch_html, parse_money, parse_pct
from .base import Source, compute_gmp_pct


class IpoWatch(Source):
    name = "ipowatch"
    url = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"

    def fetch(self) -> list[Ipo]:
        tree = LexborHTMLParser(fetch_html(self.url))
        out: list[Ipo] = []
        heading = ""
        for node in tree.css("h2,h3,table"):
            if node.tag in ("h2", "h3"):
                heading = clean(node.text())
                continue
            rows = node.css("tr")
            if len(rows) < 2:
                continue
            header = [clean(c.text()).lower() for c in rows[0].css("th,td")]
            if not (any("gmp" in h for h in header)
                    and any(("company" in h or "ipo" in h or "name" in h) for h in header)):
                continue
            idx = {h: i for i, h in enumerate(header)}
            board = "SME" if "sme" in heading.lower() else (
                "Mainboard" if "mainboard" in heading.lower() else "")

            def col(cells, *keys):
                for k in keys:
                    for h, i in idx.items():
                        if k in h and i < len(cells):
                            return clean(cells[i].text())
                return ""

            for row in rows[1:]:
                cells = row.css("td")
                if len(cells) < 2:
                    continue
                anchor = cells[0].css_first("a")
                name = clean(anchor.text() if anchor else cells[0].text())
                if not name:
                    continue
                badge = cells[0].css_first("span")
                gmp_cell = col(cells, "gmp")           # '₹245' absolute
                est_cell = col(cells, "est. gain", "est gain", "gain",
                                "est. listing", "est listing", "listing")  # '₹1,116 (28.13%)'
                ipo = Ipo(
                    name=name,
                    gmp=parse_money(gmp_cell),
                    gmp_pct=parse_pct(est_cell),        # % is in Est. Gain
                    price_band=col(cells, "price"),
                    est_listing=est_cell,
                    open_date=col(cells, "date"),
                    ipo_type=col(cells, "type") or board,
                    status=col(cells, "status") or clean(badge.text() if badge else ""),
                    source=self.name,
                )
                compute_gmp_pct(ipo)                     # fallback from band if % missing
                out.append(ipo)
        if not out:
            raise ValueError("ipowatch: no GMP table rows parsed")
        return out
