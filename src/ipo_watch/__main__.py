"""CLI: python -m ipo_watch [--data DIR] [--content DIR] [--no-reviews]
[--no-llm] [--no-notify] [--once] [--iterations N] [--interval S]

Self-loop (--iterations>1) approximates sub-hourly polling inside one GitHub
Actions run, since GitHub throttles high-frequency cron.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .pipeline import run
from .util import configure_logging, log


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ipo_watch", description="India IPO GMP watch")
    p.add_argument("--data", default="data", help="data dir for JSON snapshots")
    p.add_argument("--content", default=None, help="Astro content-collection dir for blog posts")
    p.add_argument("--no-reviews", action="store_true", help="skip YouTube review gathering")
    p.add_argument("--no-llm", action="store_true", help="skip g4f summaries")
    p.add_argument("--no-notify", action="store_true", help="skip Telegram/ntfy")
    p.add_argument("--iterations", type=int, default=1, help="self-loop count")
    p.add_argument("--interval", type=int, default=60, help="seconds between iterations")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    configure_logging(args.verbose)
    data_dir = Path(args.data)
    content_dir = Path(args.content) if args.content else None

    rc = 0
    for i in range(1, args.iterations + 1):
        log.info("=== iteration %d/%d ===", i, args.iterations)
        try:
            snap, changed = run(
                data_dir=data_dir,
                content_dir=content_dir,
                with_reviews=not args.no_reviews,
                with_llm=not args.no_llm,
                with_notify=not args.no_notify,
            )
            log.info("done: %d picks, changed=%s", len(snap.picks), changed)
        except Exception as e:  # noqa: BLE001
            log.error("iteration %d failed: %s", i, e)
            rc = 1
            break
        if i < args.iterations:
            time.sleep(args.interval)
    return rc


if __name__ == "__main__":
    sys.exit(main())
