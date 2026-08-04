"""YouTube review gathering via yt-dlp (keyless, no API key).

For each IPO name we run `ytsearch{N}:{name} IPO review`, take metadata only
(title, views, channel, date) — fast + keyless. Optional transcript fetch
feeds the g4f sentiment step. review_score = view-weighted recency + positive
title signal, normalised 0..1 (a tiebreaker; GMP is the primary rank key).
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
import sys
from datetime import datetime, timezone

from ..models import Ipo, ReviewVideo

log = logging.getLogger("ipo_watch")

_POSITIVE = (
    "buy", "apply", "subscribe", "strong", "gain", "profit", "listing gain",
    "must apply", "gmp high", "bumper", "multibagger", "good", "positive",
)
_NEGATIVE = ("avoid", "skip", "risk", "overvalued", "loss", "weak", "don't apply", "negative")


def _yt_search(query: str, n: int) -> list[dict]:
    """Return yt-dlp flat metadata dicts. Empty list on any failure.

    Invoke yt-dlp as a module (`python -m yt_dlp`) so it works whether or not
    the console script is on PATH; fall back to the bare `yt-dlp` binary.
    """
    args = [
        f"ytsearch{n}:{query}",
        "--dump-json",
        "--flat-playlist",
        "--no-warnings",
        "--skip-download",
    ]
    candidates = [[sys.executable, "-m", "yt_dlp", *args], ["yt-dlp", *args]]
    proc = None
    for cmd in candidates:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            break
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            log.warning("yt-dlp attempt failed for %r: %s", query, e)
            continue
    if proc is None:
        return []
    out = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _recency_weight(upload_date: str) -> float:
    """YYYYMMDD -> 1.0 (today) decaying to ~0.3 at 90 days."""
    if not upload_date or len(upload_date) < 8:
        return 0.5
    try:
        d = datetime.strptime(upload_date[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.5
    days = max(0.0, (datetime.now(timezone.utc) - d).days)
    return max(0.3, math.exp(-days / 90.0))


def _title_signal(title: str) -> float:
    t = title.lower()
    pos = sum(1 for w in _POSITIVE if w in t)
    neg = sum(1 for w in _NEGATIVE if w in t)
    # -1..+1 -> 0..1
    return max(0.0, min(1.0, 0.5 + 0.15 * (pos - neg)))


def gather_reviews(ipo: Ipo, per_ipo: int = 5) -> None:
    """Populate ipo.videos + ipo.review_score (mutates in place)."""
    query = f"{ipo.name} IPO review GMP"
    raw = _yt_search(query, per_ipo)
    videos: list[ReviewVideo] = []
    score_acc = 0.0
    weight_acc = 0.0
    for item in raw:
        vid = item.get("id", "")
        title = item.get("title", "") or ""
        views = int(item.get("view_count") or 0)
        rv = ReviewVideo(
            title=title,
            url=f"https://www.youtube.com/watch?v={vid}" if vid else item.get("url", ""),
            channel=item.get("channel", "") or item.get("uploader", "") or "",
            views=views,
            upload_date=str(item.get("upload_date") or ""),
        )
        videos.append(rv)
        w = _recency_weight(rv.upload_date) * math.log10(max(10, views))
        score_acc += w * _title_signal(title)
        weight_acc += w
    ipo.videos = videos
    ipo.review_score = round(score_acc / weight_acc, 4) if weight_acc else 0.0
    log.info("reviews %s: %d videos, score=%.3f", ipo.name, len(videos), ipo.review_score)
