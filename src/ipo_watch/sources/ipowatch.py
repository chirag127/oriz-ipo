"""IPOWatch — https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/

VERIFIED 2026-08-04 (httpx, server-rendered, no JS needed). Real header:
  ['IPO Name', 'IPO GMP*', 'Trend', 'Price Band', 'Est. Listing', 'Date',
   'Type', 'Status', 'Last Updated']

KEY QUIRK: the GMP **percentage** lives in the 'Est. Listing' column
(e.g. '₹1,116 (28.13%)'), NOT the 'IPO GMP*' column ('₹245' = absolute rupees).
So parse % from Est. Listing; parse absolute GMP from IPO GMP*.
"""

from __future__ import annotations

from selectolax.parser import HTMLParser

from ..models import Ipo
from ..util import clean, fetch_html, parse_money, parse_pct
from .base import Source, compute_gmp_pct


class IpoWatch(Source):
    name = "ipowatch"
    url = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"

    def fetch(self) -> list[Ipo]:
        tree = HTMLParser(fetch_html(self.url))
        out: list[Ipo] = []
        for table in tree.css("table"):
            rows = table.css("tr")
            if len(rows) < 2:
                continue
            header = [clean(c.text()).lower() for c in rows[0].css("th,td")]
            if not (any("ipo" in h for h in header) and any("gmp" in h for h in header)):
                continue
            idx = {h: i for i, h in enumerate(header)}

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
                name = clean(cells[0].text())
                if not name:
                    continue
                gmp_cell = col(cells, "gmp")           # '₹245' absolute
                est_cell = col(cells, "est. listing", "est listing", "listing")  # '₹1,116 (28.13%)'
                ipo = Ipo(
                    name=name,
                    gmp=parse_money(gmp_cell),
                    gmp_pct=parse_pct(est_cell),        # % is in Est. Listing
                    price_band=col(cells, "price"),
                    est_listing=est_cell,
                    open_date=col(cells, "date"),
                    ipo_type=col(cells, "type"),
                    status=col(cells, "status"),
                    source=self.name,
                )
                compute_gmp_pct(ipo)                     # fallback from band if % missing
                out.append(ipo)
            if out:
                break
        if not out:
            raise ValueError("ipowatch: no GMP table rows parsed")
        return out
