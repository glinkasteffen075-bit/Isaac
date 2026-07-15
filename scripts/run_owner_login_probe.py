#!/usr/bin/env python3
"""Owner-Login-Probe ausführen (nur lokal, Admin-Modus)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from owner_login_probe import format_probe_report, run_login_probe


async def main() -> int:
    result = await run_login_probe()
    print(format_probe_report(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))