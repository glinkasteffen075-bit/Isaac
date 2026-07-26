from __future__ import annotations

"""Remote smoke + Render Free keep-alive.

Render Free sleeps after ~15 minutes without inbound traffic.
This module:

  * ``wake``  — cheap GET /healthz (default every 10 min) to prevent sleep
  * ``full``  — chat cases A/B/C/G + health + Sentry sample + optional Cognee write

Run from an **always-on host** (laptop, S8, GitHub Actions) — a sleeping
Render instance cannot wake itself.

Env:
  RENDER_URL / ISAAC_REMOTE_FREE_URL
  ISAAC_REMOTE_SMOKE=1              enable background keep-alive
  ISAAC_REMOTE_SMOKE_WAKE_INTERVAL_S=600   (< 900; default 600 = 10 min)
  ISAAC_REMOTE_SMOKE_FULL_INTERVAL_S=7200  full suite every 2h
  ISAAC_REMOTE_SMOKE_WRITE_COGNEE=1
  ISAAC_REMOTE_SMOKE_PUSH_ON_FAIL=1
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from config import DATA_DIR
from audit import AuditLog

log = logging.getLogger("Isaac.RemoteSmoke")

STATE_PATH = DATA_DIR / "remote_smoke_state.json"
REPORT_PATH = DATA_DIR / "remote_smoke_last.json"

DEFAULT_URL = "https://isaac-free.onrender.com"

# Render Free typically sleeps after 15 minutes (900s) of inactivity.
RENDER_SLEEP_THRESHOLD_S = 900
DEFAULT_WAKE_INTERVAL_S = 600   # 10 min — must stay under sleep threshold
DEFAULT_FULL_INTERVAL_S = 7200  # 2 hours between full chat suites
MAX_WAKE_INTERVAL_S = 840       # hard cap 14 min — never schedule ≥15 min

CHAT_CASES: list[tuple[str, str]] = [
    ("A", "Hallo Isaac"),
    ("B", "Danke"),
    ("C", "Was ist 2+2?"),
    ("G", "Und?"),
]


def remote_smoke_enabled() -> bool:
    raw = str(os.getenv("ISAAC_REMOTE_SMOKE", "0") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def target_url() -> str:
    return (
        (os.getenv("RENDER_URL") or "").strip()
        or (os.getenv("ISAAC_REMOTE_FREE_URL") or "").strip()
        or (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
        or DEFAULT_URL
    ).rstrip("/")


def wake_interval_s() -> float:
    """Interval for health keep-alive; always forced below Render sleep threshold."""
    raw = os.getenv("ISAAC_REMOTE_SMOKE_WAKE_INTERVAL_S")
    try:
        val = float(raw) if raw not in (None, "") else float(DEFAULT_WAKE_INTERVAL_S)
    except (TypeError, ValueError):
        val = float(DEFAULT_WAKE_INTERVAL_S)
    # Never allow interval that lets Free sleep between pings
    return max(60.0, min(val, float(MAX_WAKE_INTERVAL_S)))


def full_interval_s() -> float:
    raw = os.getenv("ISAAC_REMOTE_SMOKE_FULL_INTERVAL_S")
    try:
        val = float(raw) if raw not in (None, "") else float(DEFAULT_FULL_INTERVAL_S)
    except (TypeError, ValueError):
        val = float(DEFAULT_FULL_INTERVAL_S)
    return max(wake_interval_s() * 2, val)


def write_cognee_enabled() -> bool:
    raw = os.getenv("ISAAC_REMOTE_SMOKE_WRITE_COGNEE")
    if raw is None or str(raw).strip() == "":
        # follow external memory write flag
        return str(os.getenv("ISAAC_EXTERNAL_MEMORY_WRITE", "0")).strip().lower() in {
            "1", "true", "yes", "on",
        }
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def push_on_fail_enabled() -> bool:
    raw = str(os.getenv("ISAAC_REMOTE_SMOKE_PUSH_ON_FAIL", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "last_wake_at": 0.0,
            "last_full_at": 0.0,
            "wake_count": 0,
            "full_count": 0,
            "last_ok": None,
        }
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        try:
            STATE_PATH.chmod(0o600)
        except OSError:
            pass
    except Exception as exc:
        log.debug("remote_smoke state save: %s", exc)


def _http_json(url: str, *, timeout: float = 30.0) -> tuple[bool, Any, float]:
    t0 = time.perf_counter()
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Isaac-RemoteSmoke/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            ms = round((time.perf_counter() - t0) * 1000, 1)
            if not raw.strip():
                return True, None, ms
            try:
                return True, json.loads(raw), ms
            except json.JSONDecodeError:
                return True, raw[:500], ms
    except Exception as exc:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return False, str(exc)[:200], ms


def wake_health(
    base_url: Optional[str] = None,
    *,
    retries: int = 3,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """Ping /healthz with cold-start retries (wakes sleeping Free tier)."""
    base = (base_url or target_url()).rstrip("/")
    url = f"{base}/healthz"
    last_err = ""
    total_ms = 0.0
    data: Any = None
    for attempt in range(1, max(1, retries) + 1):
        ok, data, ms = _http_json(url, timeout=timeout)
        total_ms += ms
        if ok and isinstance(data, dict) and data.get("ok"):
            return {
                "ok": True,
                "mode": "wake",
                "url": base,
                "attempt": attempt,
                "ms": round(total_ms, 1),
                "git_commit": (data.get("git_commit") or "")[:12] or None,
                "git_branch": data.get("git_branch"),
                "active_provider": data.get("active_provider"),
                "keys": {
                    "groq": data.get("has_groq_key"),
                    "gemini": data.get("has_gemini_key"),
                    "openrouter": data.get("has_openrouter_key"),
                },
                "free_cloud": data.get("free_cloud"),
                "raw": data,
            }
        last_err = str(data) if not ok else "health not ok"
        # Cold start: wait longer between retries
        if attempt < retries:
            time.sleep(min(25, 5 * attempt))
    return {
        "ok": False,
        "mode": "wake",
        "url": base,
        "attempt": retries,
        "ms": round(total_ms, 1),
        "error": last_err,
    }


def ws_url(http_url: str) -> str:
    if http_url.startswith("https://"):
        return "wss://" + http_url[len("https://") :] + "/ws"
    if http_url.startswith("http://"):
        return "ws://" + http_url[len("http://") :] + "/ws"
    return "wss://" + http_url + "/ws"


def classify_expectation(case_id: str, response: str) -> tuple[bool, str]:
    r = (response or "").strip()
    if not r:
        return False, "empty response"
    if case_id == "A":
        if "[RELAY" in r or "[Fehler]" in r[:40]:
            return False, "greeting should not hit relay error"
        return True, "greeting path"
    if case_id == "B":
        if "[RELAY] Alle Provider" in r:
            return False, "all providers failed"
        return True, "ack path"
    if case_id == "C":
        if "[RELAY] Alle Provider" in r:
            return False, "all providers failed"
        if "[Fehler]" in r[:30]:
            return False, "error response"
        if "4" in r or "vier" in r.lower():
            return True, "contains answer 4"
        return True, "non-empty chat reply"
    if case_id == "G":
        # follow-up must not invent tool success
        low = r.lower()
        if "[evidence]" in low or "[browser]" in low[:80]:
            return True, "has tool evidence markers"
        fake = any(
            p in low
            for p in (
                "ich habe mich erfolgreich",
                "ich bin eingeloggt",
                "browser ist geöffnet",
                "successfully logged in",
            )
        )
        if fake:
            return False, "hallucinated tool success"
        return True, "no fake tool success"
    return True, "ok"


async def one_chat(uri: str, text: str, timeout: float = 120.0) -> dict[str, Any]:
    try:
        import websockets
    except ImportError:
        return {
            "text": text,
            "got_init": False,
            "response": "",
            "error": "websockets package required",
            "ms": 0,
            "ok": False,
        }

    t0 = time.perf_counter()
    got_init = False
    response_text = ""
    error = ""
    try:
        async with websockets.connect(uri, max_size=10 * 1024 * 1024, open_timeout=60) as ws:
            deadline_init = time.perf_counter() + 15
            while time.perf_counter() < deadline_init:
                try:
                    raw = await __import__("asyncio").wait_for(ws.recv(), timeout=3)
                except Exception:
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
                remaining = deadline - time.perf_counter()
                try:
                    raw = await __import__("asyncio").wait_for(
                        ws.recv(), timeout=min(30, max(0.1, remaining))
                    )
                except Exception:
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
    except Exception as exc:
        error = str(exc)[:200]

    ms = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "text": text,
        "got_init": got_init,
        "response": response_text,
        "error": error,
        "ms": ms,
        "ok": bool(response_text) and not error and "[Fehler]" not in response_text[:20],
    }


def fetch_sentry_sample() -> dict[str, Any]:
    """Reuse automation pipeline Sentry probe when available."""
    try:
        from automation_pipeline import _probe_sentry

        return _probe_sentry()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}


def build_smoke_memory_text(report: dict[str, Any]) -> str:
    parts = [
        f"remote_smoke mode={report.get('mode')} ts={report.get('ts')} "
        f"ok={report.get('ok')} url={report.get('url')}",
        f"commit={report.get('git_commit')} provider={report.get('active_provider')} "
        f"wake_interval_s={report.get('wake_interval_s')} "
        f"full_interval_s={report.get('full_interval_s')}",
        f"health_ok={((report.get('health') or {}).get('ok'))} "
        f"health_ms={((report.get('health') or {}).get('ms'))}",
    ]
    cases = report.get("cases") or []
    if cases:
        passed = sum(1 for c in cases if c.get("pass"))
        parts.append(f"chat_passed={passed}/{len(cases)}")
        for c in cases:
            excerpt = re.sub(r"\s+", " ", str(c.get("response") or c.get("error") or "")[:120])
            parts.append(
                f"case {c.get('case')} pass={c.get('pass')} ms={c.get('ms')} "
                f"note={c.get('expect_note')} :: {excerpt}"
            )
    sen = report.get("sentry") or {}
    parts.append(
        f"sentry_ok={sen.get('ok')} unresolved_sample={sen.get('unresolved_count_sample')}"
    )
    for row in (sen.get("unresolved_preview") or [])[:5]:
        parts.append(
            f"sentry_issue {row.get('shortId')} n={row.get('count')} {row.get('title')}"
        )
    return "\n".join(parts)


def write_smoke_to_cognee(report: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "written": []}
    if not force and not write_cognee_enabled():
        result["skipped"] = "ISAAC_REMOTE_SMOKE_WRITE_COGNEE / EXTERNAL_MEMORY_WRITE off"
        return result
    text = build_smoke_memory_text(report)
    result["text_preview"] = text[:200]
    try:
        from external_memory import get_external_memory_bridge

        bridge = get_external_memory_bridge()
        if not bridge.cfg.write_enabled and not force:
            result["skipped"] = "ISAAC_EXTERNAL_MEMORY_WRITE=0"
            return result
        if not bridge.cognee.available():
            result["skipped"] = "cognee not available"
            return result
        ok = bridge.cognee.remember(
            [{"role": "system", "content": text[:4000]}],
            metadata={
                "source": "isaac_remote_smoke",
                "kind": "remote_smoke",
                "mode": report.get("mode"),
                "ok": report.get("ok"),
            },
        )
        if ok:
            result["ok"] = True
            result["written"].append("cognee")
        else:
            result["error"] = "cognee.remember returned False"
    except Exception as exc:
        result["error"] = str(exc)[:200]
    return result


def save_report(report: dict[str, Any]) -> Path:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        REPORT_PATH.chmod(0o600)
    except OSError:
        pass
    return REPORT_PATH


async def run_full_smoke(
    base_url: Optional[str] = None,
    *,
    write_memory: bool = True,
    include_sentry: bool = True,
    cases: Optional[list[tuple[str, str]]] = None,
    chat_timeout: float = 150.0,
) -> dict[str, Any]:
    """Wake + chat cases + Sentry sample + optional Cognee write."""
    base = (base_url or target_url()).rstrip("/")
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    health = wake_health(base, retries=4, timeout=50.0)
    report: dict[str, Any] = {
        "ok": False,
        "mode": "full",
        "ts": ts,
        "url": base,
        "wake_interval_s": wake_interval_s(),
        "full_interval_s": full_interval_s(),
        "render_sleep_threshold_s": RENDER_SLEEP_THRESHOLD_S,
        "health": {k: v for k, v in health.items() if k != "raw"},
        "git_commit": health.get("git_commit"),
        "active_provider": health.get("active_provider"),
        "cases": [],
        "sentry": {},
        "memory_write": {},
    }

    case_list = cases if cases is not None else list(CHAT_CASES)
    if health.get("ok"):
        uri = ws_url(base)
        for case_id, text in case_list:
            try:
                res = await one_chat(uri, text, timeout=chat_timeout)
            except Exception as exc:
                res = {
                    "text": text,
                    "got_init": False,
                    "response": "",
                    "error": str(exc)[:200],
                    "ms": 0,
                    "ok": False,
                }
            exp_ok, exp_note = classify_expectation(case_id, res.get("response") or "")
            row = {
                "case": case_id,
                "text": text,
                "pass": bool(res.get("ok")) and exp_ok,
                "ok": bool(res.get("ok")),
                "expect_ok": exp_ok,
                "expect_note": exp_note,
                "ms": res.get("ms"),
                "got_init": res.get("got_init"),
                "error": res.get("error") or "",
                "response": (res.get("response") or "")[:500],
            }
            report["cases"].append(row)
    else:
        report["cases"] = [
            {
                "case": cid,
                "text": txt,
                "pass": False,
                "ok": False,
                "expect_ok": False,
                "expect_note": "skipped: health failed",
                "ms": 0,
                "error": health.get("error") or "health failed",
                "response": "",
            }
            for cid, txt in case_list
        ]

    if include_sentry:
        report["sentry"] = fetch_sentry_sample()

    cases_ok = all(c.get("pass") for c in report["cases"]) if report["cases"] else False
    report["ok"] = bool(health.get("ok")) and cases_ok
    report["passed"] = sum(1 for c in report["cases"] if c.get("pass"))
    report["total"] = len(report["cases"])

    if write_memory:
        report["memory_write"] = write_smoke_to_cognee(report, force=False)

    if not report["ok"] and push_on_fail_enabled():
        try:
            from owner_notify import KIND_MISSION_STUCK, OwnerBlocker, notify_owner_blocker

            await notify_owner_blocker(
                OwnerBlocker(
                    kind=KIND_MISSION_STUCK,
                    title="Remote smoke failed on isaac-free",
                    detail=(
                        f"passed={report.get('passed')}/{report.get('total')} "
                        f"commit={report.get('git_commit')} "
                        f"health={health.get('ok')}"
                    ),
                    need="owner_decision_or_data",
                    source="remote_smoke",
                    cooldown_key=f"remote_smoke_fail|{report.get('git_commit') or 'na'}",
                ),
            )
        except Exception as exc:
            log.debug("remote smoke push: %s", exc)

    save_report(report)
    state = _load_state()
    state["last_full_at"] = time.time()
    state["full_count"] = int(state.get("full_count") or 0) + 1
    state["last_wake_at"] = time.time()
    state["wake_count"] = int(state.get("wake_count") or 0) + 1
    state["last_ok"] = report["ok"]
    state["last_commit"] = report.get("git_commit")
    _save_state(state)

    AuditLog.action(
        "RemoteSmoke",
        "full",
        f"ok={report['ok']} {report.get('passed')}/{report.get('total')} "
        f"commit={report.get('git_commit')}",
        erfolg=bool(report["ok"]),
    )
    return report


def run_wake_only(base_url: Optional[str] = None) -> dict[str, Any]:
    """Cheap keep-alive ping (anti-sleep)."""
    health = wake_health(base_url or target_url(), retries=3, timeout=40.0)
    report = {
        "ok": bool(health.get("ok")),
        "mode": "wake",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "url": health.get("url"),
        "wake_interval_s": wake_interval_s(),
        "full_interval_s": full_interval_s(),
        "render_sleep_threshold_s": RENDER_SLEEP_THRESHOLD_S,
        "health": {k: v for k, v in health.items() if k != "raw"},
        "git_commit": health.get("git_commit"),
        "active_provider": health.get("active_provider"),
        "cases": [],
        "passed": 0,
        "total": 0,
        "note": (
            f"keep-alive under sleep threshold "
            f"({wake_interval_s():.0f}s < {RENDER_SLEEP_THRESHOLD_S}s)"
        ),
    }
    save_report(report)
    state = _load_state()
    state["last_wake_at"] = time.time()
    state["wake_count"] = int(state.get("wake_count") or 0) + 1
    state["last_ok"] = report["ok"]
    state["last_commit"] = report.get("git_commit")
    _save_state(state)
    AuditLog.action(
        "RemoteSmoke",
        "wake",
        f"ok={report['ok']} commit={report.get('git_commit')} ms={health.get('ms')}",
        erfolg=bool(report["ok"]),
    )
    return report


async def run_auto_tick(
    *,
    on_note: Optional[Callable[[str], None]] = None,
    force_full: bool = False,
) -> dict[str, Any]:
    """Decide wake vs full based on intervals; used by background loop."""
    if not remote_smoke_enabled() and not force_full:
        return {"ok": True, "skipped": "ISAAC_REMOTE_SMOKE=0", "mode": "off"}

    now = time.time()
    state = _load_state()
    last_wake = float(state.get("last_wake_at") or 0.0)
    last_full = float(state.get("last_full_at") or 0.0)
    w_int = wake_interval_s()
    f_int = full_interval_s()

    need_full = force_full or (now - last_full) >= f_int
    need_wake = (now - last_wake) >= w_int

    if need_full:
        report = await run_full_smoke(write_memory=True, include_sentry=True)
        note = (
            f"[RemoteSmoke] full ok={report.get('ok')} "
            f"{report.get('passed')}/{report.get('total')} "
            f"commit={report.get('git_commit')}"
        )
        if on_note:
            on_note(note)
        return report

    if need_wake:
        report = run_wake_only()
        note = (
            f"[RemoteSmoke] wake ok={report.get('ok')} "
            f"commit={report.get('git_commit')} "
            f"next≤{w_int:.0f}s (sleep={RENDER_SLEEP_THRESHOLD_S}s)"
        )
        if on_note:
            on_note(note)
        return report

    return {
        "ok": True,
        "skipped": "intervals_not_due",
        "mode": "idle",
        "seconds_to_wake": max(0.0, w_int - (now - last_wake)),
        "seconds_to_full": max(0.0, f_int - (now - last_full)),
        "wake_interval_s": w_int,
        "full_interval_s": f_int,
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "[Remote Smoke]",
        f"mode={report.get('mode')} ok={report.get('ok')} url={report.get('url')}",
        f"commit={report.get('git_commit') or '—'} provider={report.get('active_provider') or '—'}",
        f"wake_interval={report.get('wake_interval_s')}s "
        f"(Render sleep≈{report.get('render_sleep_threshold_s') or RENDER_SLEEP_THRESHOLD_S}s) "
        f"full_interval={report.get('full_interval_s')}s",
    ]
    h = report.get("health") or {}
    lines.append(f"health ok={h.get('ok')} ms={h.get('ms')} err={h.get('error') or '—'}")
    if report.get("cases"):
        lines.append(f"chat {report.get('passed')}/{report.get('total')}")
        for c in report["cases"]:
            lines.append(
                f"  {c.get('case')}: pass={c.get('pass')} ms={c.get('ms')} "
                f"({c.get('expect_note')})"
            )
    sen = report.get("sentry") or {}
    if sen:
        lines.append(
            f"sentry ok={sen.get('ok')} unresolved≈{sen.get('unresolved_count_sample')}"
        )
        for row in (sen.get("unresolved_preview") or [])[:3]:
            lines.append(f"  {row.get('shortId')}: {row.get('title')}")
    mw = report.get("memory_write") or {}
    if mw:
        lines.append(
            f"cognee write ok={mw.get('ok')} written={mw.get('written')} "
            f"skip={mw.get('skipped') or mw.get('error') or '—'}"
        )
    if report.get("expected_sha"):
        lines.append(f"expected_sha={report.get('expected_sha')}")
    wait = report.get("wait") or {}
    if wait:
        lines.append(
            f"deploy_wait matched={wait.get('matched')} "
            f"live={wait.get('live')} wait_s={wait.get('wait_s')} "
            f"attempts={wait.get('attempts')}"
        )
    if report.get("note"):
        lines.append(str(report["note"]))
    if report.get("skipped"):
        lines.append(f"skipped={report.get('skipped')}")
    if report.get("error"):
        lines.append(f"error={report.get('error')}")
    return "\n".join(lines)


def status() -> dict[str, Any]:
    state = _load_state()
    return {
        "enabled": remote_smoke_enabled(),
        "url": target_url(),
        "wake_interval_s": wake_interval_s(),
        "full_interval_s": full_interval_s(),
        "render_sleep_threshold_s": RENDER_SLEEP_THRESHOLD_S,
        "wake_under_sleep": wake_interval_s() < RENDER_SLEEP_THRESHOLD_S,
        "last_wake_at": state.get("last_wake_at"),
        "last_full_at": state.get("last_full_at"),
        "wake_count": state.get("wake_count"),
        "full_count": state.get("full_count"),
        "last_ok": state.get("last_ok"),
        "last_commit": state.get("last_commit"),
        "report_path": str(REPORT_PATH),
    }


def _sha_match(live: Optional[str], expected: str) -> bool:
    a = (live or "").strip().lower()
    b = (expected or "").strip().lower()
    if not a or not b:
        return False
    n = min(len(a), len(b), 12)
    if n < 7:
        return a == b
    return a[:n] == b[:n]


def wait_for_deploy_commit(
    expected_sha: str,
    *,
    base_url: Optional[str] = None,
    timeout_s: float = 600.0,
    poll_s: float = 20.0,
) -> dict[str, Any]:
    """Poll /healthz until live git_commit matches expected (post-deploy gate).

    Each poll is also a keep-alive wake ping (anti-sleep while waiting).
    """
    base = (base_url or target_url()).rstrip("/")
    exp = (expected_sha or "").strip()
    if not exp:
        return {"ok": False, "error": "expected_sha empty", "matched": False}
    t0 = time.time()
    attempts = 0
    last: dict[str, Any] = {}
    while (time.time() - t0) < max(30.0, timeout_s):
        attempts += 1
        last = wake_health(base, retries=2, timeout=40.0)
        live = last.get("git_commit") or ""
        # full sha may be in raw
        raw = last.get("raw") if isinstance(last.get("raw"), dict) else {}
        full = str(raw.get("git_commit") or live or "")
        if last.get("ok") and (_sha_match(live, exp) or _sha_match(full, exp)):
            return {
                "ok": True,
                "matched": True,
                "expected": exp[:12],
                "live": (full or live)[:12],
                "attempts": attempts,
                "wait_s": round(time.time() - t0, 1),
                "health": {k: v for k, v in last.items() if k != "raw"},
            }
        time.sleep(max(5.0, poll_s))
    return {
        "ok": False,
        "matched": False,
        "expected": exp[:12],
        "live": (last.get("git_commit") or None),
        "attempts": attempts,
        "wait_s": round(time.time() - t0, 1),
        "error": "timeout waiting for deploy commit on healthz",
        "health": {k: v for k, v in last.items() if k != "raw"} if last else {},
    }


async def run_post_deploy_smoke(
    expected_sha: str,
    *,
    base_url: Optional[str] = None,
    timeout_s: float = 600.0,
    poll_s: float = 20.0,
    write_memory: bool = True,
) -> dict[str, Any]:
    """R2 deploy gate: wait until Free serves expected_sha, then full smoke."""
    wait = wait_for_deploy_commit(
        expected_sha,
        base_url=base_url,
        timeout_s=timeout_s,
        poll_s=poll_s,
    )
    if not wait.get("matched"):
        report = {
            "ok": False,
            "mode": "post_deploy",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "url": base_url or target_url(),
            "expected_sha": (expected_sha or "")[:12],
            "wait": wait,
            "cases": [],
            "passed": 0,
            "total": 0,
            "error": wait.get("error") or "deploy commit not live",
            "wake_interval_s": wake_interval_s(),
            "full_interval_s": full_interval_s(),
            "render_sleep_threshold_s": RENDER_SLEEP_THRESHOLD_S,
        }
        save_report(report)
        AuditLog.action(
            "RemoteSmoke",
            "post_deploy_wait_fail",
            f"expected={expected_sha[:12]} live={wait.get('live')}",
            erfolg=False,
        )
        if push_on_fail_enabled():
            try:
                from owner_notify import KIND_MISSION_STUCK, OwnerBlocker, notify_owner_blocker

                await notify_owner_blocker(
                    OwnerBlocker(
                        kind=KIND_MISSION_STUCK,
                        title="Post-deploy smoke: Render commit not live",
                        detail=(
                            f"expected={expected_sha[:12]} live={wait.get('live')} "
                            f"wait_s={wait.get('wait_s')}"
                        ),
                        need="owner_decision_or_data",
                        source="post_deploy_smoke",
                        cooldown_key=f"post_deploy_wait|{expected_sha[:12]}",
                    ),
                )
            except Exception as exc:
                log.debug("post_deploy push: %s", exc)
        return report

    smoke = await run_full_smoke(
        base_url or target_url(),
        write_memory=write_memory,
        include_sentry=True,
    )
    smoke["mode"] = "post_deploy"
    smoke["expected_sha"] = (expected_sha or "")[:12]
    smoke["wait"] = wait
    save_report(smoke)
    AuditLog.action(
        "RemoteSmoke",
        "post_deploy",
        f"ok={smoke.get('ok')} expected={expected_sha[:12]} "
        f"passed={smoke.get('passed')}/{smoke.get('total')}",
        erfolg=bool(smoke.get("ok")),
    )
    return smoke
