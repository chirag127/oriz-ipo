"""Notifiers: Telegram (bot token from env) + ntfy. Both best-effort, both
read config from env, both no-op cleanly when unconfigured.

Telegram uses HTML parse_mode, i2i-style: each IPO is a block whose bold first
line is a clickable link to its analysis page on ipo.oriz.in, followed by
label-light info lines (GMP, issue size, subscription x, band, dates) + the AI
analysis + top review link. Messages are chunked to Telegram's 4096 limit.
"""

from __future__ import annotations

import logging
import os

import httpx

from ..models import Ipo

log = logging.getLogger("ipo_watch")

SITE = "https://ipo.oriz.in"
SAFE_CHUNK = 3800


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _sub_line(ipo: Ipo) -> str | None:
    if ipo.sub_total is None and ipo.sub_qib is None:
        return None
    parts = []
    if ipo.sub_total is not None:
        parts.append(f"{ipo.sub_total:g}x overall")
    cats = []
    if ipo.sub_qib is not None:
        cats.append(f"QIB {ipo.sub_qib:g}x")
    if ipo.sub_nii is not None:
        cats.append(f"NII {ipo.sub_nii:g}x")
    if ipo.sub_retail is not None:
        cats.append(f"Retail {ipo.sub_retail:g}x")
    if cats:
        parts.append("(" + ", ".join(cats) + ")")
    return "Subscribed " + " ".join(parts) if parts else None


def _ipo_block(ipo: Ipo, rank: int) -> str:
    url = f"{SITE}/ipo/{ipo.slug}" if ipo.slug else SITE
    star = " ★" if ipo.review_score >= 0.6 else ""
    head = (
        f'{rank}. <a href="{_esc(url)}"><b>{_esc(ipo.name)} — '
        f'{ipo.gmp_pct:.1f}% GMP{star}</b></a>'
    )
    lines = [head]
    meta = " · ".join(x for x in [ipo.status, ipo.ipo_type] if x)
    if meta:
        lines.append(_esc(meta))
    detail = []
    if ipo.gmp is not None:
        detail.append(f"GMP ₹{ipo.gmp:g}")
    if ipo.price_band:
        detail.append(f"band {ipo.price_band}")
    if ipo.issue_size:
        detail.append(f"size {ipo.issue_size}")
    if detail:
        lines.append(_esc(" · ".join(detail)))
    sub = _sub_line(ipo)
    if sub:
        lines.append(_esc(sub))
    dates = " · ".join(x for x in [ipo.open_date, ipo.close_date] if x)
    if dates:
        lines.append(_esc(dates))
    if ipo.summary:
        lines.append(_esc(ipo.summary))
    if ipo.videos:
        v = ipo.videos[0]
        lines.append(f'review: <a href="{_esc(v.url)}">{_esc(v.title[:70])}</a>')
    lines.append(f'→ full analysis: {_esc(url)}')
    return "\n".join(lines)


def format_messages(picks: list[Ipo], source: str) -> list[str]:
    """Build one or more HTML message chunks (<= Telegram 4096)."""
    header = (
        f"📈 <b>{len(picks)} open mainboard IPO"
        f"{'s' if len(picks) != 1 else ''} · GMP &gt; 5%</b> "
        f"(via {_esc(source)})\n\n"
    )
    footer = f'\n\n📊 <a href="{SITE}">IPO GMP Terminal</a>'
    if not picks:
        return [f"No open mainboard IPO is above the 5% GMP threshold right now.\n{footer}"]

    blocks = [_ipo_block(ipo, i) for i, ipo in enumerate(picks, 1)]
    messages: list[str] = []
    current = header
    for b in blocks:
        piece = b + "\n\n"
        if len(current) + len(piece) > SAFE_CHUNK and current != header:
            messages.append(current.rstrip())
            current = ""
        current += piece
    current = current.rstrip() + footer
    messages.append(current)
    return messages


def send_telegram(messages: list[str]) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.info("telegram: TELEGRAM_BOT_TOKEN/CHAT_ID unset — skipping")
        return False
    ok = True
    for msg in messages:
        try:
            r = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            log.warning("telegram send failed: %s", e)
            ok = False
    if ok:
        log.info("telegram: sent %d message(s)", len(messages))
    return ok


def send_ntfy(text: str) -> bool:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        log.info("ntfy: NTFY_TOPIC unset — skipping")
        return False
    base = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh").rstrip("/")
    headers = {"Title": "IPO GMP watch", "Tags": "chart_with_upwards_trend"}
    user = os.environ.get("NTFY_USER", "").strip()
    pw = os.environ.get("NTFY_PASSWORD", "").strip()
    auth = (user, pw) if user and pw else None
    try:
        r = httpx.post(
            f"{base}/{topic}",
            content=text.encode("utf-8"),
            headers=headers,
            auth=auth,
            timeout=20,
        )
        r.raise_for_status()
        log.info("ntfy: sent to %s/%s", base, topic)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("ntfy send failed: %s", e)
        return False


def _fmt_ntfy(picks: list[Ipo], source: str) -> str:
    """Plain-text version for ntfy (no HTML)."""
    if not picks:
        return "No open mainboard IPO above 5% GMP right now."
    lines = [f"{len(picks)} open mainboard IPO(s) · GMP>5% (via {source})", ""]
    for i, ipo in enumerate(picks, 1):
        lines.append(f"{i}. {ipo.name} — {ipo.gmp_pct:.1f}% GMP")
        bits = []
        if ipo.issue_size:
            bits.append(f"size {ipo.issue_size}")
        if ipo.sub_total is not None:
            bits.append(f"sub {ipo.sub_total:g}x")
        if ipo.price_band:
            bits.append(ipo.price_band)
        if bits:
            lines.append("   " + " · ".join(bits))
        if ipo.slug:
            lines.append(f"   https://ipo.oriz.in/ipo/{ipo.slug}")
    return "\n".join(lines)


def notify_all(picks: list[Ipo], source: str) -> dict[str, bool]:
    messages = format_messages(picks, source)
    return {
        "telegram": send_telegram(messages),
        "ntfy": send_ntfy(_fmt_ntfy(picks, source)),
    }
