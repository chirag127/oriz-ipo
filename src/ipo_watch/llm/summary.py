"""LLM summariser — NVIDIA NIM (server-side, keyed) FIRST, g4f keyless as last
resort. Deterministic fallback so a missing/failed LLM never blocks the pipeline
or the notification.

NVIDIA NIM is OpenAI-compatible; when NVIDIA_API_KEY is set we call it over
httpx (already a dep). g4f public API drifts, so it's imported lazily and every
error is swallowed. If both fail, `summarise` returns a clean template blurb
built from the structured fields — the pipeline never depends on the LLM.
"""

from __future__ import annotations

import logging
import os

import httpx

from ..models import Ipo

log = logging.getLogger("ipo_watch")

# --- NVIDIA NIM (server-side, requires NVIDIA_API_KEY) -----------------------
_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
# Best confirmed model first, then fallbacks. Override with IPO_NVIDIA_MODELS.
_NVIDIA_MODELS = [
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "meta/llama-3.3-70b-instruct",
    "deepseek-ai/deepseek-r1",
]

# --- g4f (keyless, last resort) ----------------------------------------------
# Best models first, then fall back down the list. g4f routes each to whichever
# provider currently serves it; if one model/provider fails we try the next.
# Override with IPO_LLM_MODELS="a,b,c". (g4f docs: gpt-4o / gpt-4.1 / deepseek-v3
# are the strong keyless models; gpt-4o-mini is the reliable fallback.)
_DEFAULT_MODELS = ["gpt-4o", "gpt-4.1", "deepseek-v3", "gpt-4o-mini"]


def _models() -> list[str]:
    env = os.environ.get("IPO_LLM_MODELS", "").strip()
    return [m.strip() for m in env.split(",") if m.strip()] or _DEFAULT_MODELS


def _nvidia_models() -> list[str]:
    env = os.environ.get("IPO_NVIDIA_MODELS", "").strip()
    return [m.strip() for m in env.split(",") if m.strip()] or _NVIDIA_MODELS


def _nvidia_complete(prompt: str) -> str | None:
    """Server-side NVIDIA NIM (OpenAI-compatible), best models first. None if no
    key or all fail."""
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        return None
    for model in _nvidia_models():
        try:
            resp = httpx.post(
                f"{_NVIDIA_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 400,
                },
                timeout=45,
            )
            resp.raise_for_status()
            text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
            if text:
                log.info("nvidia: %s answered", model)
                return text
        except Exception as e:  # noqa: BLE001 - try next model
            log.info("nvidia model %s failed: %s", model, e)
            continue
    return None


def _complete(prompt: str) -> str | None:
    """NVIDIA NIM first (if keyed), g4f as last resort. None if all fail."""
    if os.environ.get("IPO_DISABLE_LLM") == "1":
        return None
    return _nvidia_complete(prompt) or _g4f_complete(prompt)


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
    return _complete(prompt) or _template_blurb(ipo)


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
    return _complete(prompt) or _template_comment_analysis(ipo)
