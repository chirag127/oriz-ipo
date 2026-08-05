"""Pipeline: scrape -> filter GMP>threshold -> reviews -> sort by GMP -> summarise
-> write JSON + per-IPO blog markdown -> detect change -> notify.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .llm.summary import analyse_comments, summarise
from .models import Ipo, Snapshot
from .reviews.youtube import gather_reviews
from .sources import scrape_first_available
from .sources.subscription import enrich_subscription
from .util import slugify

log = logging.getLogger("ipo_watch")

THRESHOLD_PCT = 5.0


def rank(ipos: list[Ipo], threshold: float = THRESHOLD_PCT) -> list[Ipo]:
    """Picks = OPEN mainboard IPOs with gmp_pct > threshold, sorted by GMP% desc.

    Per user directive 2026-08-05: only currently-OPEN IPOs, no SME (mainboard
    only). review_score is the tiebreaker; GMP% is the primary sort key.
    """
    picks = [
        i for i in ipos
        if (i.gmp_pct or 0) > threshold and i.is_open and not i.is_sme
    ]
    picks.sort(key=lambda i: (i.gmp_pct or 0, i.review_score), reverse=True)
    return picks


def _change_key(picks: list[Ipo]) -> list[list]:
    """Stable comparable signature for change detection (name + rounded GMP%)."""
    return sorted([[i.name, round(i.gmp_pct or 0, 1)] for i in picks])


def load_previous(data_dir: Path) -> Snapshot | None:
    latest = data_dir / "latest.json"
    if not latest.exists():
        return None
    try:
        raw = json.loads(latest.read_text(encoding="utf-8"))
        snap = Snapshot(
            generated_at=raw.get("generated_at", ""),
            source=raw.get("source", ""),
            threshold_pct=raw.get("threshold_pct", THRESHOLD_PCT),
        )
        snap.picks = [_ipo_from_dict(d) for d in raw.get("picks", [])]
        return snap
    except Exception as e:  # noqa: BLE001
        log.warning("could not read previous snapshot: %s", e)
        return None


def _ipo_from_dict(d: dict) -> Ipo:
    ipo = Ipo(name=d.get("name", ""))
    ipo.gmp_pct = d.get("gmp_pct")
    ipo.gmp = d.get("gmp")
    return ipo


def write_snapshot(snap: Snapshot, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snap.to_dict(), indent=2, ensure_ascii=False)
    (data_dir / "latest.json").write_text(payload, encoding="utf-8")
    day = snap.generated_at[:10] or "snapshot"
    (data_dir / "history").mkdir(exist_ok=True)
    (data_dir / "history" / f"{day}.json").write_text(payload, encoding="utf-8")
    log.info("wrote latest.json + history/%s.json", day)


def write_blog_posts(picks: list[Ipo], content_dir: Path) -> int:
    """One markdown post per pick, into the Astro content collection."""
    content_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for ipo in picks:
        slug = ipo.slug or slugify(ipo.name)
        fm = [
            "---",
            f'title: "{ipo.name} IPO — {ipo.gmp_pct:.1f}% grey-market premium"',
            f"gmp_pct: {ipo.gmp_pct:.2f}",
            f'gmp: "{ipo.gmp if ipo.gmp is not None else ""}"',
            f'price_band: "{ipo.price_band}"',
            f'ipo_type: "{ipo.ipo_type}"',
            f'status: "{ipo.status}"',
            f'source: "{ipo.source}"',
            f"review_score: {ipo.review_score:.4f}",
            "---",
            "",
            ipo.summary or "",
            "",
        ]
        if ipo.videos:
            fm.append("## Reviews\n")
            for v in ipo.videos:
                fm.append(f"- [{v.title}]({v.url}) — {v.channel} ({v.views:,} views)")
        (content_dir / f"{slug}.md").write_text("\n".join(fm), encoding="utf-8")
        n += 1
    log.info("wrote %d blog posts to %s", n, content_dir)
    return n


def run(
    data_dir: Path,
    content_dir: Path | None = None,
    with_reviews: bool = True,
    with_llm: bool = True,
    with_notify: bool = True,
) -> tuple[Snapshot, bool]:
    """Full run. Returns (snapshot, changed)."""
    source, ipos = scrape_first_available()
    picks = rank(ipos)
    for ipo in picks:
        ipo.slug = slugify(ipo.name)   # always — the site routes on slug
    log.info("%d IPOs, %d above %.0f%% GMP", len(ipos), len(picks), THRESHOLD_PCT)

    if with_reviews:
        for ipo in picks:
            gather_reviews(ipo)
        # review_score is the tiebreaker — re-sort after gathering
        picks.sort(key=lambda i: (i.gmp_pct or 0, i.review_score), reverse=True)

    # subscription + issue size (best-effort; never blocks the run)
    try:
        enrich_subscription(picks)
    except Exception as e:  # noqa: BLE001
        log.warning("subscription enrich failed: %s", e)
    if with_llm:
        for ipo in picks:
            ipo.summary = summarise(ipo)
            ipo.comment_analysis = analyse_comments(ipo)

    prev = load_previous(data_dir)
    changed = prev is None or _change_key(prev.picks) != _change_key(picks)

    snap = Snapshot(source=source, threshold_pct=THRESHOLD_PCT, all_ipos=ipos, picks=picks)
    write_snapshot(snap, data_dir)
    if content_dir is not None:
        write_blog_posts(picks, content_dir)

    if with_notify and changed:
        from .notify.channels import notify_all
        notify_all(picks, source)
    elif with_notify:
        log.info("no change since last run — skipping notification")

    return snap, changed
