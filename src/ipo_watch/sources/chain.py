"""Source failover chain. Try each in order; first that yields GMP% rows wins.

Order (VERIFIED 2026-08-04 — see verify-website-structure-before-scrapers rule):
  1. IPOWatch     httpx  ✓ server-rendered, % in Est. Listing col
  2. IPOPremium   httpx  ✓ server-rendered, % computed from band
  3. InvestorGain Playwright — JS-rendered ('No data available' over plain HTTP);
                  works in CI, may fail in a broken-driver local env (tolerated).
  4. Chittorgarh  Playwright — per-IPO GMP, JS.

Dropped (404 on probe): niftytrader.in/ipo-grey-market-premium, ipocentral.in.
"""

from __future__ import annotations

import logging

from ..models import Ipo
from .base import Source
from .investorgain import InvestorGain
from .ipopremium import IpoPremium
from .ipowatch import IpoWatch
from .playwright_source import PlaywrightTable

log = logging.getLogger("ipo_watch")


def build_chain() -> list[Source]:
    return [
        IpoWatch(),
        IpoPremium(),
        InvestorGain(),  # Playwright-backed (see module)
        PlaywrightTable(
            "chittorgarh",
            "https://www.chittorgarh.com/report/ipo-grey-market-premium-latest-ipo-gmp/74/",
        ),
    ]


def scrape_first_available() -> tuple[str, list[Ipo]]:
    """Return (source_name, ipos) from the first working source. Raise if all fail."""
    errors: list[str] = []
    for src in build_chain():
        try:
            log.info("trying source: %s (%s)", src.name, src.url)
            ipos = src.fetch()
            good = [i for i in ipos if i.name and i.gmp_pct is not None]
            if not good:
                raise ValueError(f"{src.name}: parsed {len(ipos)} rows, none had a GMP%")
            log.info("source %s OK: %d rows (%d with GMP%%)", src.name, len(ipos), len(good))
            return src.name, ipos
        except Exception as e:  # noqa: BLE001 - failover is the point
            log.warning("source %s failed: %s", src.name, e)
            errors.append(f"{src.name}: {e}")
    raise RuntimeError("all IPO GMP sources failed:\n  " + "\n  ".join(errors))
