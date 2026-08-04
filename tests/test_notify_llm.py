"""Notifier formatting + LLM fallback tests (no network, no real send)."""

import os

from ipo_watch.models import Ipo, ReviewVideo
from ipo_watch.notify.channels import _fmt_picks, send_telegram, send_ntfy
from ipo_watch.llm.summary import summarise, _template_blurb


def _ipo(name, pct, review=0.0):
    i = Ipo(name=name, gmp_pct=pct)
    i.review_score = review
    return i


def test_fmt_picks_empty():
    assert "No IPOs above" in _fmt_picks([], "ipowatch")


def test_fmt_picks_lists_and_stars():
    a = _ipo("Alpha", 30.0, 0.7)  # >=0.6 -> star
    a.videos = [ReviewVideo(title="t", url="https://youtu.be/z")]
    b = _ipo("Beta", 8.0, 0.1)
    text = _fmt_picks([a, b], "investorgain")
    assert "Alpha" in text and "Beta" in text
    assert "30.0% GMP" in text
    assert "★" in text  # Alpha earns a star
    assert "ipo.oriz.in" in text
    assert "investorgain" in text


def test_notifiers_noop_without_env(monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NTFY_TOPIC"):
        monkeypatch.delenv(k, raising=False)
    assert send_telegram("hi") is False
    assert send_ntfy("hi") is False


def test_template_blurb():
    i = _ipo("Gamma", 12.5)
    i.price_band = "100-108"
    blurb = _template_blurb(i)
    assert "Gamma" in blurb
    assert "12.5%" in blurb
    assert "threshold" in blurb.lower()


def test_summarise_falls_back_without_llm(monkeypatch):
    monkeypatch.setenv("IPO_DISABLE_LLM", "1")
    i = _ipo("Delta", 20.0)
    out = summarise(i)
    assert "Delta" in out
    assert isinstance(out, str) and len(out) > 10
