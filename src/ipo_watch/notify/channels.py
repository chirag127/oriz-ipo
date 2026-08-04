"""Notifiers: Telegram (bot token from env) + ntfy. Both best-effort, both
read config from env, both no-op cleanly when unconfigured.
"""

from __future__ import annotations

import logging
import os

import httpx

from ..models import Ipo

log = logging.getLogger("ipo_watch")


def _fmt_picks(picks: list[Ipo], source: str) -> str:
    if not picks:
        return "No IPOs above the 5% GMP threshold right now."
    lines = [f"IPO GMP watch — {len(picks)} above 5% (via {source})", ""]
    for i, ipo in enumerate(picks, 1):
        star = " ★" if ipo.review_score >= 0.6 else ""
        lines.append(
            f"{i}. {ipo.name} — {ipo.gmp_pct:.1f}% GMP"
            f"{f' (₹{ipo.gmp:g})' if ipo.gmp else ''}{star}"
        )
        if ipo.ipo_type or ipo.status:
            lines.append(f"   {ipo.ipo_type} · {ipo.status}".strip(" ·"))
        if ipo.videos:
            top = ipo.videos[0]
            lines.append(f"   review: {top.url}")
    lines.append("")
    lines.append("https://ipo.oriz.in")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.info("telegram: TELEGRAM_BOT_TOKEN/CHAT_ID unset — skipping")
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=20,
        )
        r.raise_for_status()
        log.info("telegram: sent")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("telegram send failed: %s", e)
        return False


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


def notify_all(picks: list[Ipo], source: str) -> dict[str, bool]:
    text = _fmt_picks(picks, source)
    return {"telegram": send_telegram(text), "ntfy": send_ntfy(text)}
