#!/usr/bin/env python3
"""One-shot live Playwright smoke via BrowserManager (example.com).

Usage:
  ISAAC_DISABLE_VECTOR_MEMORY=1 python3 scripts/browser_live_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def main() -> int:
    from browser import BrowserManager

    mgr = BrowserManager()
    try:
        mgr.cfg.browser.headless = True
    except Exception:
        pass
    try:
        result = await mgr.run_flow(
            instance_id="smoke_example",
            start_url="https://example.com",
            actions=[
                {"action": "goto", "url": "https://example.com"},
                {"action": "extract_text", "selector": "h1", "save_as": "heading"},
            ],
            name="BrowserLiveSmoke",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
        ok = bool(result.get("ok")) and "Example" in str(
            (result.get("memory") or {}).get("heading") or ""
        )
        return 0 if ok else 1
    finally:
        try:
            await mgr.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
