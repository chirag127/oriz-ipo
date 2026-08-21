"""Notifier formatting + LLM fallback tests (no network, no real send)."""

from ipo_watch.models import Ipo, ReviewVideo
from ipo_watch.notify.channels import (
    format_messages,
    _fmt_ntfy,
    _ipo_block,
    send_telegram,
    send_ntfy,
)
from ipo_watch.llm.summary import summarise, analyse_comments, _template_blurb


def _ipo(name, pct, review=0.0, slug=""):
    i = Ipo(name=name, gmp_pct=pct)
    i.review_score = review
    i.slug = slug or name.lower().replace(" ", "-")
    return i


def test_format_messages_empty():
    msgs = format_messages([], "ipowatch")
    assert len(msgs) == 1
    assert "No open mainboard IPO" in msgs[0]


def test_format_messages_html_link_and_star():
    a = _ipo("Alpha", 30.0, 0.7, slug="alpha")
    a.gmp = 100
    a.issue_size = "₹1,200 Cr"
    a.sub_total = 12.4
    a.videos = [ReviewVideo(title="t", url="https://youtu.be/z")]
    msgs = format_messages([a], "investorgain")
    text = "\n".join(msgs)
    assert "Alpha" in text
    assert "GMP" in text
    assert "30.0%" in text  # GMP percentage shown as (30.0%)
    assert 'href="https://ipo.oriz.in/ipo/alpha"' in text  # clickable page link
    assert "<b>" in text  # HTML bold
    assert "₹1,200 Cr" in text  # issue size
    assert "12.4x" in text  # subscription
    assert "investorgain" in text


def test_format_messages_chunks_under_limit():
    many = [_ipo(f"IPO Number {i}", 10.0 + i, 0.5) for i in range(60)]
    for m in many:
        m.summary = "A reasonably long AI analysis sentence. " * 5
    msgs = format_messages(many, "ipowatch")
    assert all(len(m) <= 4096 for m in msgs)
    assert len(msgs) >= 2  # 60 blocks must chunk


def test_ipo_block_has_analysis_and_page_link():
    i = _ipo("Zeta", 15.0, 0.3, slug="zeta")
    i.summary = "Neutral take on Zeta."
    block = _ipo_block(i, 1)
    assert "Analysis" in block
    assert 'href="https://ipo.oriz.in/ipo/zeta"' in block  # clickable Analysis link


def test_fmt_ntfy_plain_text():
    i = _ipo("Eta", 22.0, slug="eta")
    i.issue_size = "₹500 Cr"
    i.sub_total = 8.0
    text = _fmt_ntfy([i], "ipowatch")
    assert "Eta" in text
    assert "<b>" not in text  # ntfy is plain text
    assert "₹500 Cr" in text
    assert "ipo.oriz.in/ipo/eta" in text


def test_notifiers_noop_without_env(monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NTFY_TOPIC"):
        monkeypatch.delenv(k, raising=False)
    assert send_telegram(["hi"]) is False
    assert send_ntfy("hi") is False


def test_template_blurb():
    i = _ipo("Gamma", 12.5)
    i.price_band = "100-108"
    blurb = _template_blurb(i)
    assert "Gamma" in blurb
    assert "12.5%" in blurb
    # long-form analysis: carries the GMP caveat + is multi-sentence
    assert "grey-market premium" in blurb.lower()
    assert "unofficial" in blurb.lower()
    assert len(blurb.split()) > 60  # no longer a 2-liner


def test_summarise_falls_back_without_llm(monkeypatch):
    monkeypatch.setenv("IPO_DISABLE_LLM", "1")
    i = _ipo("Delta", 20.0)
    out = summarise(i)
    assert "Delta" in out
    assert isinstance(out, str) and len(out) > 10


def test_comment_analysis_fallback(monkeypatch):
    monkeypatch.setenv("IPO_DISABLE_LLM", "1")
    i = _ipo("Theta", 18.0, 0.7)
    i.videos = [ReviewVideo(title="Theta review", url="u", views=5000)]
    out = analyse_comments(i)
    assert isinstance(out, str) and len(out) > 10
    # no videos -> graceful message
    empty = analyse_comments(_ipo("Iota", 9.0))
    assert "No YouTube reviews" in empty
