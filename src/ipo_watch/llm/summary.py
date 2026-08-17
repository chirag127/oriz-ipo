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
# Override with IPO_LLM_MODELS="a,b,c". "auto" lets g4f route to the best working
# provider/model (verified keyless, 2026-08); gpt-4o / gpt-4o-mini are the tested
# fallbacks. (gpt-4.1 / deepseek-v3 now require auth on g4f — dropped.)
_DEFAULT_MODELS = ["auto", "gpt-4o", "gpt-4o-mini"]


def _models() -> list[str]:
    env = os.environ.get("IPO_LLM_MODELS", "").strip()
    return [m.strip() for m in env.split(",") if m.strip()] or _DEFAULT_MODELS


def _nvidia_models() -> list[str]:
    env = os.environ.get("IPO_NVIDIA_MODELS", "").strip()
    return [m.strip() for m in env.split(",") if m.strip()] or _NVIDIA_MODELS


def _nvidia_complete(prompt: str, max_tokens: int = 1100) -> str | None:
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
                    "max_tokens": max_tokens,
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


def _complete(prompt: str, max_tokens: int = 1100) -> str | None:
    """NVIDIA NIM first (if keyed), g4f as last resort. None if all fail."""
    if os.environ.get("IPO_DISABLE_LLM") == "1":
        return None
    return _nvidia_complete(prompt, max_tokens) or _g4f_complete(prompt, max_tokens)


def _fmt_num(x: float | None) -> str:
    """12.4 -> '12.4x', 12.0 -> '12x'; None -> ''."""
    if x is None:
        return ""
    return f"{x:g}x"


def _facts_block(ipo: Ipo) -> list[str]:
    """Only-present-fields fact lines. Never fabricates; each line is a raw datum
    from the record so the model can reason without inventing missing values."""
    f: list[str] = [f"Name: {ipo.name}"]
    if ipo.ipo_type:
        f.append(f"Type: {ipo.ipo_type}")
    if ipo.status:
        f.append(f"Stage: {ipo.status}")
    if ipo.issue_size:
        f.append(f"Issue size: {ipo.issue_size}")
    if ipo.price_band:
        f.append(f"Price band: {ipo.price_band}")
    if ipo.lot_size:
        f.append(f"Lot size: {ipo.lot_size}")
    if ipo.gmp_pct is not None:
        gmp_rs = f" (₹{ipo.gmp:g})" if ipo.gmp is not None else ""
        f.append(f"Grey-market premium: ~{ipo.gmp_pct:.1f}% of upper band{gmp_rs}")
    elif ipo.gmp is not None:
        f.append(f"Grey-market premium: ₹{ipo.gmp:g}")
    if ipo.kostak:
        f.append(f"Kostak: {ipo.kostak}")
    if ipo.subject_to:
        f.append(f"Subject-to-sauda: {ipo.subject_to}")
    subs = []
    if ipo.sub_total is not None:
        subs.append(f"overall {_fmt_num(ipo.sub_total)}")
    if ipo.sub_qib is not None:
        subs.append(f"QIB {_fmt_num(ipo.sub_qib)}")
    if ipo.sub_nii is not None:
        subs.append(f"NII/HNI {_fmt_num(ipo.sub_nii)}")
    if ipo.sub_retail is not None:
        subs.append(f"retail {_fmt_num(ipo.sub_retail)}")
    if subs:
        f.append("Subscription (times): " + ", ".join(subs))
    dates = []
    if ipo.open_date:
        dates.append(f"opens {ipo.open_date}")
    if ipo.close_date:
        dates.append(f"closes {ipo.close_date}")
    if ipo.listing_date:
        dates.append(f"lists {ipo.listing_date}")
    elif ipo.est_listing:
        dates.append(f"est. listing {ipo.est_listing}")
    if dates:
        f.append("Timeline: " + ", ".join(dates))
    if ipo.videos:
        f.append(f"YouTube reviews: {len(ipo.videos)} found, "
                 f"aggregate review score {ipo.review_score:.2f}/1")
        for v in ipo.videos[:6]:
            sent = f" [{v.sentiment}]" if v.sentiment else ""
            views = f", {v.views:,} views" if v.views else ""
            f.append(f"  - \"{v.title}\" ({v.channel or 'unknown'}{views}){sent}")
    else:
        f.append("YouTube reviews: none found yet")
    return f


def _template_blurb(ipo: Ipo) -> str:
    """Deterministic multi-paragraph analysis when no LLM is reachable. Mirrors
    the prompt's sections; every clause is gated on a present field."""
    is_sme = ipo.is_sme
    p: list[str] = []

    lead = f"{ipo.name}"
    if ipo.ipo_type:
        lead += f" is a {ipo.ipo_type} IPO"
    if ipo.status:
        lead += f" currently marked {ipo.status}"
    lead += "."
    if ipo.gmp_pct is not None:
        rs = f" (about ₹{ipo.gmp:g} over the band)" if ipo.gmp is not None else ""
        lead += (f" The grey-market premium is running near {ipo.gmp_pct:.1f}% of the "
                 f"upper price band{rs}, which is the market's informal read on possible "
                 f"listing-day gains. Note that GMP is an unofficial, unregulated and "
                 f"thinly-traded signal that can move sharply or vanish before listing, "
                 f"so it should be treated as sentiment, not a forecast.")
    else:
        lead += " No grey-market premium is recorded for this issue yet."
    p.append(lead)

    subs = []
    if ipo.sub_total is not None:
        subs.append(f"overall {ipo.sub_total:g}x")
    if ipo.sub_qib is not None:
        subs.append(f"QIB {ipo.sub_qib:g}x")
    if ipo.sub_nii is not None:
        subs.append(f"NII/HNI {ipo.sub_nii:g}x")
    if ipo.sub_retail is not None:
        subs.append(f"retail {ipo.sub_retail:g}x")
    if subs:
        p.append("The book is subscribed " + ", ".join(subs) + ". "
                 "A stronger QIB figure points to institutional conviction, heavy "
                 "NII/HNI bidding often reflects leveraged listing-gain interest, and "
                 "the retail number shows how crowded the trade is with small investors.")
    else:
        p.append("Live subscription figures are not yet available for this issue, so "
                 "demand across QIB, NII and retail cannot be gauged from this snapshot.")

    seg = []
    if ipo.issue_size:
        seg.append(f"The issue size is {ipo.issue_size}.")
    if is_sme:
        seg.append("As an SME issue it is smaller and typically thinly traded, with a "
                   "higher per-lot value and lower post-listing liquidity — structurally "
                   "higher risk than a mainboard name.")
    elif ipo.ipo_type:
        seg.append("As a mainboard issue it is generally larger and more liquid than an "
                   "SME listing.")
    if seg:
        p.append(" ".join(seg))

    dates = []
    if ipo.open_date:
        dates.append(f"opens {ipo.open_date}")
    if ipo.close_date:
        dates.append(f"closes {ipo.close_date}")
    if ipo.listing_date:
        dates.append(f"lists {ipo.listing_date}")
    elif ipo.est_listing:
        dates.append(f"estimated listing {ipo.est_listing}")
    if dates:
        stage_hint = {
            "upcoming": "so the bidding window has not opened yet",
            "open": "so the issue is currently biddable",
            "closed": "so bidding has closed and the stock now awaits listing",
            "listed": "and the stock has already listed",
        }.get((ipo.status or "").lower(), "")
        line = "Timeline: " + ", ".join(dates) + "."
        if stage_hint:
            line += f" Given the current stage, {stage_hint}."
        p.append(line)

    if ipo.videos:
        n = len(ipo.videos)
        tone = ("lean positive / apply-side" if ipo.review_score >= 0.6
                else "mixed" if ipo.review_score >= 0.4
                else "cautious / avoid-side")
        p.append(f"Across {n} YouTube review{'s' if n != 1 else ''} the aggregate score is "
                 f"{ipo.review_score:.2f}/1, with commentary reading {tone}. This reflects "
                 f"reviewer opinion rather than fact, and coverage tends to emphasise "
                 f"listing-gain potential more than long-term fundamentals.")
    else:
        p.append("No YouTube reviews have surfaced yet, so there is no independent "
                 "reviewer consensus to weigh.")

    p.append("On balance, this may interest applicants comfortable with GMP-driven, "
             "listing-oriented positioning who accept that the premium can swing before "
             "listing. Investors who need liquidity, are risk-averse"
             + (", or are wary of SME thin trading" if is_sme else "")
             + ", or who would treat GMP as a guaranteed gain, have clear reasons to be "
             "cautious. None of the above is a recommendation.")

    return " ".join(p)


def _g4f_complete(prompt: str, max_tokens: int = 1100) -> str | None:
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
                max_tokens=max_tokens,
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
    """Long, neutral, equity-desk per-IPO analysis. LLM if available; a rich
    deterministic template otherwise. Never invents fields absent from `ipo`."""
    facts = "\n".join(_facts_block(ipo))

    # Only instruct a GMP read when GMP is actually present.
    if ipo.gmp_pct is not None:
        gmp_line = (f"1. GMP read — what the grey-market premium of ~{ipo.gmp_pct:.1f}% "
                    "signals about the market's listing-gain expectation, with the explicit "
                    "caveat that GMP is an unofficial, unregulated, thinly-traded and highly "
                    "volatile indicator that can evaporate before listing.")
    elif ipo.gmp is not None:
        gmp_line = ("1. GMP read — what the recorded grey-market premium signals about "
                    "listing-gain expectation, with the explicit caveat that GMP is an "
                    "unofficial, unregulated, thinly-traded and highly volatile indicator "
                    "that can evaporate before listing.")
    else:
        gmp_line = ("1. GMP read — no grey-market premium is recorded; state plainly that "
                    "no GMP signal is available and do not estimate one.")

    # Only ask for a reviewer-lean read when videos exist; never derive a lean
    # from the 0.00 default that also means "no data".
    if ipo.videos:
        review_line = (f"5. Reviewer consensus — from the YouTube review score "
                       f"({ipo.review_score:.2f}/1) and the video titles, describe the "
                       "apparent reviewer lean (apply vs avoid) and whether the framing is "
                       "listing-gain vs long-term. Attribute this clearly to reviewer "
                       "opinion, not fact.")
    else:
        review_line = ("5. Reviewer consensus — no YouTube reviews were found; state plainly "
                       "that there is no independent reviewer consensus yet and do not infer "
                       "one. Do not treat the absence of reviews as a negative signal.")

    prompt = f"""You are a neutral equity-desk analyst writing a factual read on an Indian IPO for a retail investor. Write 400-700 words of flowing prose (2-5 short paragraphs, no headings, no bullet lists, no markdown). Plain, sober, sell-side-desk tone: no hype, no exclamation marks, no emojis, no "financial advice" disclaimer, no buy/sell verdict phrased as a recommendation.

STRICT RULE: use ONLY the facts listed below. Do NOT invent, estimate, or assume any number, financial metric, subscription figure, valuation, or fundamental that is not explicitly given. If a data point (e.g. subscription, issue size, dates, GMP, reviews) is absent from the facts, either omit it or state plainly that it is not yet available — never guess it, and never treat an absent data point as a negative signal.

Cover, in order, only where the data supports it:
{gmp_line}
2. Subscription demand — ONLY if subscription figures appear in the facts: read the overall times-subscribed and what the QIB vs NII/HNI vs retail split implies about who is driving demand (institutional conviction vs leveraged HNI vs retail froth). If no subscription data is given, say the book is not yet visible / issue not yet open and skip it.
3. Issue size and type — contextualise the issue size and note the structural difference between a {ipo.ipo_type or 'Mainboard/SME'} listing: SME issues are smaller, thinly traded, higher lot value, lower liquidity and higher risk; mainboard issues are larger and more liquid.
4. Timeline — given the stage ({ipo.status or 'unknown'}) and the open/close/listing dates, state plainly what decision window the investor is in (yet to open / currently biddable / bidding closed and awaiting listing / already listed).
{review_line}
6. Balanced close — one short paragraph on who might reasonably consider this (e.g. listing-gain-oriented applicants comfortable with GMP volatility) and who should be cautious (e.g. those needing liquidity, risk-averse investors, or anyone treating GMP as a guarantee). End neutral.

Facts:
{facts}
"""
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
    return _complete(prompt, max_tokens=300) or _template_comment_analysis(ipo)
