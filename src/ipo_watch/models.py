"""Data models for IPO GMP records."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ReviewVideo:
    title: str
    url: str
    channel: str = ""
    views: int = 0
    upload_date: str = ""          # YYYYMMDD from yt-dlp
    sentiment: str = ""            # positive|neutral|negative|"" (g4f)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Ipo:
    name: str
    gmp: float | None = None       # rupees
    gmp_pct: float | None = None   # percent of upper band — the ranking key
    price_band: str = ""
    lot_size: str = ""
    open_date: str = ""
    close_date: str = ""
    listing_date: str = ""
    est_listing: str = ""
    ipo_type: str = ""             # Mainboard | SME
    status: str = ""               # Upcoming | Open | Closed | Listed
    source: str = ""               # which site produced this row
    kostak: str = ""
    subject_to: str = ""
    review_score: float = 0.0      # tiebreaker, 0..1
    videos: list[ReviewVideo] = field(default_factory=list)
    summary: str = ""              # g4f / template blurb
    slug: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["videos"] = [v.to_dict() for v in self.videos]
        return d


@dataclass(slots=True)
class Snapshot:
    generated_at: str = field(default_factory=_now_iso)
    source: str = ""
    threshold_pct: float = 5.0
    all_ipos: list[Ipo] = field(default_factory=list)
    picks: list[Ipo] = field(default_factory=list)  # gmp_pct > threshold, sorted

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "source": self.source,
            "threshold_pct": self.threshold_pct,
            "count_all": len(self.all_ipos),
            "count_picks": len(self.picks),
            "all_ipos": [i.to_dict() for i in self.all_ipos],
            "picks": [i.to_dict() for i in self.picks],
        }
