"""g4f (GPT4Free) summariser — keyless, best-effort. Deterministic fallback so a
missing/failed LLM never blocks the pipeline or the notification.

Public g4f API drifts; we import lazily and catch everything. If g4f is absent
or every provider fails, `summarise` returns a clean template blurb built from
the structured fields — the pipeline never depends on the LLM succeeding.
"""

from __future__ import annotations

import logging
import os

from ..models import Ipo

log = logging.getLogger("ipo_watch")


def _template_blurb(ipo: Ipo) -> str:
    parts = [f"{ipo.name} — grey-market premium ~{ipo.gmp_pct:.1f}%"]
    if ipo.price_band:
        parts.append(f"band {ipo.price_band}")
    if ipo.ipo_type:
        parts.append(ipo.ipo_type)
    if ipo.status:
        parts.append(ipo.status)
    if ipo.videos:
        parts.append(f"{len(ipo.videos)} YouTube reviews (score {ipo.review_score:.2f})")
    tail = (
        "Above the 5% GMP watch threshold." if (ipo.gmp_pct or 0) > 5
        else "Below the 5% GMP threshold."
    )
    return ". ".join([", ".join(parts), tail])


def _g4f_complete(prompt: str) -> str | None:
    """One best-effort g4f call. None on any failure."""
    if os.environ.get("IPO_DISABLE_LLM") == "1":
        return None
    try:
        from g4f.client import Client  # lazy — g4f may be absent
    except Exception as e:  # noqa: BLE001
        log.info("g4f unavailable: %s", e)
        return None
    try:
        client = Client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=45,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception as e:  # noqa: BLE001 - any provider failure -> fallback
        log.info("g4f completion failed: %s", e)
        return None


def summarise(ipo: Ipo) -> str:
    """Two-sentence retail-investor take. LLM if available, else template."""
    titles = "; ".join(v.title for v in ipo.videos[:4]) or "no reviews found"
    prompt = (
        "You are an equity-desk analyst. In exactly 2 concise sentences, give a "
        "neutral take on this Indian IPO for a retail investor. No hype, no "
        "financial advice disclaimer.\n\n"
        f"Name: {ipo.name}\nGMP: ~{ipo.gmp_pct:.1f}% (₹{ipo.gmp})\n"
        f"Price band: {ipo.price_band}\nType: {ipo.ipo_type}\nStatus: {ipo.status}\n"
        f"YouTube review titles: {titles}\n"
        f"Review score (0-1): {ipo.review_score:.2f}"
    )
    return _g4f_complete(prompt) or _template_blurb(ipo)
