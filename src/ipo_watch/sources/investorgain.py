"""InvestorGain — https://www.investorgain.com/report/live-ipo-gmp/331/

VERIFIED 2026-08-04: plain HTTP returns an EMPTY table ('No data available') —
the rows are JS-rendered. So this source is Playwright-backed (subclass of
PlaywrightTable). Works in CI (official Playwright action); may fail in a
broken-driver local env, in which case the chain falls through — tolerated,
IPOWatch/IPOPremium already cover the data over plain httpx.
"""

from __future__ import annotations

from .playwright_source import PlaywrightTable


class InvestorGain(PlaywrightTable):
    def __init__(self) -> None:
        super().__init__("investorgain", "https://www.investorgain.com/report/live-ipo-gmp/331/")
