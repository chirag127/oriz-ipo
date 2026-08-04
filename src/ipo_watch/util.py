"""Shared helpers: HTTP fetch, number parsing, slugs, logging."""

from __future__ import annotations

import logging
import re
import sys
import unicodedata

import httpx

log = logging.getLogger("ipo_watch")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def fetch_html(url: str, timeout: float = 25.0) -> str:
    """GET a page as text. Raises httpx.HTTPError on failure (caller falls over)."""
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(
        headers=headers, timeout=timeout, follow_redirects=True
    ) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def parse_money(text: str | None) -> float | None:
    """'₹154' / '154' / '- (Ni)' -> float or None."""
    if not text:
        return None
    m = _NUM.search(text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def parse_pct(text: str | None) -> float | None:
    """'(30.51%)' / '30.51%' -> 30.51; None if absent."""
    if not text:
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) if m else None


def upper_band(price_band: str | None) -> float | None:
    """'₹100-108' / '100 to 108' -> 108.0 (highest number found)."""
    if not price_band:
        return None
    nums = [float(n.replace(",", "")) for n in _NUM.findall(price_band.replace(",", ""))]
    return max(nums) if nums else None


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text) or "ipo"


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()
