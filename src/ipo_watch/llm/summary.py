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

# Best models first, then fall back down the list. g4f routes each to whichever
# provider currently serves it; if one model/provider fails we try the next.
# Override with IPO_LLM_MODELS="a,b,c". (g4f docs: gpt-4o / gpt-4.1 / deepseek-v3
# are the strong keyless models; gpt-4o-mini is the reliable fallback.)
_DEFAULT_MODELS = ["gpt-4o", "gpt-4.1", "deepseek-v3", "gpt-4o-mini"]


def _models() -> list[str]:
    env = os.environ.get("IPO_LLM_MODELS", "").strip()
    return [m.strip() for m in env.split(",") if m.strip()] or _DEFAULT_MODELS


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
    """Best-effort g4f call, trying best models first with fallback. None if all fail."""
    if os.environ.get("IPO_DISABLE_LLM") == "1":
        return None
    try:
        from g4f.client import Client  # lazy — g4f may be absent
    except Exception as e:  # noqa: BLE001
        log.info("g4f unavailable: %s", e)
        return None
    client = Client()
    for model in _models():
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=45,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                log.info("g4f: %s answered", model)
                return text
        except Exception as e:  # noqa: BLE001 - try next model
            log.info("g4f model %s failed: %s", model, e)
            continue
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


def _template_comment_analysis(ipo: Ipo) -> str:
    if not ipo.videos:
        return "No YouTube reviews found yet for this IPO."
    n = len(ipo.videos)
    total_views = sum(v.views for v in ipo.videos)
    tone = (
        "broadly positive" if ipo.review_score >= 0.6
        else "mixed" if ipo.review_score >= 0.4
        else "cautious"
    )
    return (
        f"{n} reviewer{'s' if n != 1 else ''} covered this IPO "
        f"({total_views:,} combined views); overall reviewer tone reads {tone} "
        f"(review score {ipo.review_score:.2f}/1)."
    )


def analyse_comments(ipo: Ipo) -> str:
    """Analyse the YouTube review-video signals into a short reviewer-consensus
    paragraph. LLM if available, else a deterministic template."""
    if not ipo.videos:
        return _template_comment_analysis(ipo)
    lines = "\n".join(
        f"- {v.title} ({v.channel}, {v.views:,} views)" for v in ipo.videos[:8]
    )
    prompt = (
        "You are an equity-desk analyst. Given these YouTube review-video titles "
        "for an Indian IPO, summarise the REVIEWER CONSENSUS in 2-3 sentences: "
        "do reviewers lean apply/avoid, what themes recur (valuation, GMP, "
        "fundamentals, listing-gain vs long-term). Neutral tone, no disclaimer.\n\n"
        f"IPO: {ipo.name} (GMP ~{ipo.gmp_pct:.1f}%)\nReviews:\n{lines}"
    )
    return _g4f_complete(prompt) or _template_comment_analysis(ipo)
