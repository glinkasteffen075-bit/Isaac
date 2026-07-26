#!/usr/bin/env python3
"""Remote smoke + Render Free anti-sleep keep-alive.

Wake interval defaults to 10 minutes (< Render Free ~15 min sleep).

Usage:
  # one full suite (health + chat A/B/C/G + sentry + optional cognee)
  python3 scripts/remote_smoke_suite.py
  python3 scripts/remote_smoke_suite.py --mode full

  # single keep-alive health ping
  python3 scripts/remote_smoke_suite.py --mode wake

  # continuous: wake every 10m, full every 2h (run on always-on host / CI)
  ISAAC_REMOTE_SMOKE=1 python3 scripts/remote_smoke_suite.py --loop

  RENDER_URL=https://isaac-free.onrender.com python3 scripts/remote_smoke_suite.py --mode wake
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# repo root on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Isaac remote smoke / keep-alive")
    parser.add_argument(
        "--mode",
        choices=("full", "wake", "auto"),
        default="full",
        help="full=chat suite, wake=health only, auto=interval decision",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Repeat forever using wake/full intervals (anti-sleep)",
    )
    parser.add_argument(
        "--url",
        default="",
        help="Override RENDER_URL / ISAAC_REMOTE_FREE_URL",
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Do not write Cognee on full runs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print report JSON only",
    )
    args = parser.parse_args()

    if args.url:
        os.environ["RENDER_URL"] = args.url.rstrip("/")

    from remote_smoke import (
        format_report,
        full_interval_s,
        run_auto_tick,
        run_full_smoke,
        run_wake_only,
        status,
        target_url,
        wake_interval_s,
        RENDER_SLEEP_THRESHOLD_S,
    )

    if not args.json:
        print(
            f"target={target_url()} wake={wake_interval_s():.0f}s "
            f"full={full_interval_s():.0f}s sleep_threshold={RENDER_SLEEP_THRESHOLD_S}s"
        )
        print(f"status={json.dumps(status(), ensure_ascii=False)}")

    async def once(mode: str) -> dict:
        if mode == "wake":
            return run_wake_only()
        if mode == "auto":
            return await run_auto_tick(force_full=False)
        return await run_full_smoke(write_memory=not args.no_memory)

    if not args.loop:
        report = asyncio.run(once(args.mode))
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_report(report))
        if report.get("skipped"):
            return 0
        return 0 if report.get("ok") else 1

    # Continuous anti-sleep loop (must run outside Render Free)
    os.environ.setdefault("ISAAC_REMOTE_SMOKE", "1")
    print(
        f"LOOP anti-sleep: wake every {wake_interval_s():.0f}s "
        f"(must be < {RENDER_SLEEP_THRESHOLD_S}s)"
    )
    exit_worst = 0
    while True:
        try:
            report = asyncio.run(run_auto_tick(force_full=(args.mode == "full")))
            if args.json:
                print(json.dumps(report, ensure_ascii=False))
            else:
                print(format_report(report))
                print("---")
            if report.get("ok") is False and not report.get("skipped"):
                exit_worst = 1
            # sleep until next wake is due (with small jitter)
            sleep_s = max(30.0, min(wake_interval_s(), float(report.get("seconds_to_wake") or wake_interval_s())))
            if report.get("mode") in {"wake", "full"} or report.get("skipped") == "intervals_not_due":
                # after a run, wait full wake interval
                if report.get("mode") in {"wake", "full"}:
                    sleep_s = wake_interval_s()
            time.sleep(sleep_s)
        except KeyboardInterrupt:
            print("stopped")
            return exit_worst


if __name__ == "__main__":
    raise SystemExit(main())
