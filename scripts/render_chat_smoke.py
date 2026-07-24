#!/usr/bin/env python3
"""Smoke-test Isaac chat on Render via WebSocket /ws.

Usage:
  python3 scripts/render_chat_smoke.py
  RENDER_URL=https://isaac-free.onrender.com python3 scripts/render_chat_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

try:
    import websockets
except ImportError:
    print("websockets package required", file=sys.stderr)
    sys.exit(2)


DEFAULT_URL = os.getenv("RENDER_URL", "https://isaac-free.onrender.com").rstrip("/")
CASES = [
    ("A", "Hallo Isaac"),
    ("C", "Was ist 2+2?"),
]


def ws_url(http_url: str) -> str:
    if http_url.startswith("https://"):
        return "wss://" + http_url[len("https://") :] + "/ws"
    if http_url.startswith("http://"):
        return "ws://" + http_url[len("http://") :] + "/ws"
    return "wss://" + http_url + "/ws"


async def one_chat(uri: str, text: str, timeout: float = 120.0) -> dict[str, Any]:
    t0 = time.perf_counter()
    got_init = False
    response_text = ""
    error = ""
    async with websockets.connect(uri, max_size=10 * 1024 * 1024, open_timeout=60) as ws:
        # drain init messages briefly, then send chat
        deadline_init = time.perf_counter() + 15
        while time.perf_counter() < deadline_init:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=3)
            except asyncio.TimeoutError:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("typ") == "init":
                got_init = True
                break

        await ws.send(json.dumps({"typ": "chat", "text": text}))

        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(30, deadline - time.perf_counter()))
            except asyncio.TimeoutError:
                error = "timeout waiting for chat_response"
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            typ = msg.get("typ")
            if typ == "chat_response":
                response_text = str(msg.get("text") or "")
                break
            if typ == "fehler":
                error = str(msg.get("msg") or msg)
                break

    ms = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "text": text,
        "got_init": got_init,
        "response": response_text,
        "error": error,
        "ms": ms,
        "ok": bool(response_text) and not error and "[Fehler]" not in response_text[:20],
    }


def classify_expectation(case_id: str, response: str) -> tuple[bool, str]:
    r = (response or "").strip()
    if not r:
        return False, "empty response"
    if case_id == "A":
        # local greeting — usually short, German, no RELAY error
        if "[RELAY" in r or "[Fehler]" in r:
            return False, "greeting should not hit relay error"
        return True, "greeting path"
    if case_id == "C":
        # may use LLM — accept if not hard failure
        if "[RELAY] Alle Provider" in r:
            return False, "all providers failed"
        if "[Fehler]" in r[:30]:
            return False, "error response"
        # ideally mentions 4
        if "4" in r or "vier" in r.lower():
            return True, "contains answer 4"
        return True, "non-empty chat reply (model may paraphrase)"
    return True, "ok"


async def main() -> int:
    base = DEFAULT_URL
    uri = ws_url(base)
    print(f"WS {uri}")
    results = []
    # sequential — free tier single instance
    for case_id, text in CASES:
        print(f"\n--- {case_id}: {text!r} ---")
        try:
            res = await one_chat(uri, text, timeout=150)
        except Exception as exc:
            res = {
                "text": text,
                "got_init": False,
                "response": "",
                "error": str(exc),
                "ms": 0,
                "ok": False,
            }
        exp_ok, exp_note = classify_expectation(case_id, res.get("response") or "")
        res["case"] = case_id
        res["expect_ok"] = exp_ok
        res["expect_note"] = exp_note
        res["pass"] = bool(res.get("ok")) and exp_ok
        results.append(res)
        preview = (res.get("response") or res.get("error") or "")[:300].replace("\n", " ")
        print(f"  init={res.get('got_init')} ms={res.get('ms')} pass={res['pass']}")
        print(f"  note={exp_note}")
        print(f"  reply: {preview}")

    passed = sum(1 for r in results if r["pass"])
    print(f"\n=== Render chat: {passed}/{len(results)} passed ===")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
