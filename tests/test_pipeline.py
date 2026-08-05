"""Ranking, filtering, change-detection, and blog-write tests."""

from pathlib import Path

from ipo_watch.models import Ipo, Snapshot, ReviewVideo
from ipo_watch.pipeline import rank, _change_key, write_blog_posts, THRESHOLD_PCT


def _ipo(name, pct, review=0.0, status="Open", ipo_type="Mainboard"):
    """Open mainboard IPO by default (the only kind that ranks)."""
    i = Ipo(name=name, gmp_pct=pct, status=status, ipo_type=ipo_type)
    i.review_score = review
    return i


def test_rank_filters_below_threshold():
    ipos = [_ipo("A", 12.0), _ipo("B", 5.0), _ipo("C", 4.9), _ipo("D", None)]
    names = [p.name for p in rank(ipos)]
    assert "A" in names
    assert "B" not in names  # 5.0 is NOT > 5
    assert "C" not in names
    assert "D" not in names


def test_rank_open_only():
    ipos = [
        _ipo("OpenOne", 20.0, status="Open"),
        _ipo("Upcoming", 40.0, status="Upcoming"),
        _ipo("Closed", 35.0, status="Closed"),
        _ipo("Listed", 50.0, status="Listed"),
    ]
    names = [p.name for p in rank(ipos)]
    assert names == ["OpenOne"]  # only the OPEN one, despite lower GMP


def test_rank_no_sme():
    ipos = [
        _ipo("Main", 15.0, ipo_type="Mainboard"),
        _ipo("SmeHigh", 90.0, ipo_type="NSE SME"),
        _ipo("SmeHigh2", 80.0, ipo_type="BSE SME"),
    ]
    names = [p.name for p in rank(ipos)]
    assert names == ["Main"]  # SME excluded even at 90% GMP


def test_rank_sorts_by_gmp_then_review():
    ipos = [_ipo("low", 10.0, 0.9), _ipo("high", 30.0, 0.1), _ipo("mid", 20.0, 0.5)]
    assert [p.name for p in rank(ipos)] == ["high", "mid", "low"]


def test_rank_review_score_is_tiebreaker():
    ipos = [_ipo("x", 15.0, 0.2), _ipo("y", 15.0, 0.8)]
    assert [p.name for p in rank(ipos)] == ["y", "x"]


def test_change_key_detects_change():
    a = [_ipo("A", 12.0), _ipo("B", 8.0)]
    b = [_ipo("A", 12.0), _ipo("B", 8.0)]
    c = [_ipo("A", 12.0), _ipo("B", 9.0)]
    assert _change_key(a) == _change_key(b)
    assert _change_key(a) != _change_key(c)


def test_write_blog_posts(tmp_path: Path):
    ipo = _ipo("Dhoot Transmission", 28.1, 0.7)
    ipo.gmp = 245
    ipo.price_band = "829-871"
    ipo.summary = "Test summary."
    ipo.videos = [ReviewVideo(title="Dhoot IPO review", url="https://youtu.be/x", channel="ch", views=1000)]
    n = write_blog_posts([ipo], tmp_path)
    assert n == 1
    md = (tmp_path / "dhoot-transmission.md").read_text(encoding="utf-8")
    assert "Dhoot Transmission" in md
    assert "gmp_pct: 28.1" in md
    assert "Test summary." in md
    assert "youtu.be/x" in md


def test_threshold_is_five():
    assert THRESHOLD_PCT == 5.0
