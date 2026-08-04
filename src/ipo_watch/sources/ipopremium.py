"""IPOPremium — https://ipopremium.in/

VERIFIED 2026-08-04 (httpx, server-rendered). Real header:
  ['Company Name', 'Type', 'GMP (₹)', 'Open', 'Close', 'Price Band (₹)',
   'Listing Date']

GMP is absolute rupees ('249'); price band 'low–high' ('829–871'). Compute the
% from GMP / upper-band. Name carries '(Mainboard)'/'(SME)' suffixes we keep.
"""

from __future__ import annotations

from selectolax.parser import HTMLParser

from ..models import Ipo
from ..util import clean, fetch_html, parse_money
from .base import Source, compute_gmp_pct


class IpoPremium(Source):
    name = "ipopremium"
    url = "https://ipopremium.in/"

    def fetch(self) -> list[Ipo]:
        tree = HTMLParser(fetch_html(self.url))
        out: list[Ipo] = []
        for table in tree.css("table"):
            rows = table.css("tr")
            if len(rows) < 2:
                continue
            header = [clean(c.text()).lower() for c in rows[0].css("th,td")]
            if not (any("gmp" in h for h in header)
                    and any(("company" in h or "name" in h) for h in header)):
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
                ipo = Ipo(
                    name=name,
                    gmp=parse_money(col(cells, "gmp")),
                    price_band=col(cells, "price band", "band", "price"),
                    open_date=col(cells, "open"),
                    close_date=col(cells, "close"),
                    listing_date=col(cells, "listing"),
                    ipo_type=col(cells, "type"),
                    source=self.name,
                )
                compute_gmp_pct(ipo)   # % from GMP / upper band
                out.append(ipo)
            if out:
                break
        if not out:
            raise ValueError("ipopremium: no GMP table rows parsed")
        return out
