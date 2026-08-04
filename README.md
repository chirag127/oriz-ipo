# oriz-ipo — India IPO GMP Terminal

Live at **[ipo.oriz.in](https://ipo.oriz.in)** · hourly India IPO grey-market-premium (GMP) analyzer + dark terminal site.

![license](https://img.shields.io/github/license/chirag127/oriz-ipo)
![last commit](https://img.shields.io/github/last-commit/chirag127/oriz-ipo)

Scrapes every open India IPO's grey-market premium across multiple public trackers (with failover), keeps only IPOs with **GMP > 5%**, ranks them by GMP, gathers YouTube reviews per IPO, writes a per-IPO post, and notifies Telegram + ntfy on change — every hour, via GitHub Actions. The committed JSON drives a static Astro site.

## How it works

```
scrape (failover) → filter GMP>5% → rank by GMP → YouTube reviews (yt-dlp)
  → g4f summary (keyless, optional) → write data/latest.json + posts
  → notify Telegram/ntfy on change → commit → CF Pages rebuilds ipo.oriz.in
```

- **Language:** Python (scraper) + Astro (site). No external DB — the repo IS the database (`data/latest.json` + `data/history/`), free + versioned.
- **Sources (verified, failover order):** IPOWatch → IPOPremium (both plain-HTTP, server-rendered) → InvestorGain → Chittorgarh (JS, Playwright). First source with GMP% rows wins.
- **Reviews:** `yt-dlp ytsearch` (no API key). Score = view-weighted recency + positive-title signal. GMP is the primary sort; review score is the tiebreaker.
- **LLM:** `g4f` (GPT4Free), keyless, best-effort — deterministic template blurb if every provider fails. Never blocks the run.
- **Notify:** Telegram (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` from env/secrets) + ntfy (`NTFY_TOPIC`). Fires only when the pick set changes.

## Run locally

```bash
pip install -e ".[browser,dev]"
python -m playwright install chromium        # for JS-rendered sources
python -m ipo_watch --data data --no-notify  # scrape + rank + reviews
pytest -q                                    # tests
cd web && npm install && npm run build       # build the site
```

Flags: `--no-reviews`, `--no-llm`, `--no-notify`, `--content DIR`, `--iterations N --interval S` (self-loop).

## Deploy

CF Pages project builds `web/` on push (`web/dist`). The hourly Action commits fresh data; the push triggers the rebuild. Set repo secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `NTFY_TOPIC` (+ optional `NTFY_*`).

## Disclaimer

Not investment advice. GMP is an unofficial grey-market signal, not a listing guarantee.
