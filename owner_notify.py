from __future__ import annotations

"""Isaac – Owner Push only when truly blocked.

Notify Steffen when Isaac cannot proceed without owner input
(credentials, API keys, URL/target, 2FA/captcha, hard mission stuck).

Channels (best-effort, non-fatal):
  1. ntfy (ISAAC_NTFY_TOPIC / NTFY_TOPIC) — cross-device push
  2. Termux notification — local Android
  3. Webhook (ISAAC_OWNER_WEBHOOK_URL)
  4. Local blocker log + optional background note

Spam protection: per-blocker cooldown + global min interval.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR
from audit import AuditLog

log = logging.getLogger("Isaac.OwnerNotify")

STATE_PATH = DATA_DIR / "owner_notify_state.json"
BLOCKERS_LOG = DATA_DIR / "owner_blockers.jsonl"

# Hard blockers only — soft failures do not push
KIND_MISSING_CREDENTIALS = "missing_credentials"
KIND_MISSING_API_KEY = "missing_api_key"
KIND_MISSING_TARGET = "missing_target"
KIND_BROWSER_DISABLED = "browser_disabled"
KIND_CAPTCHA_2FA = "captcha_or_2fa"
KIND_CONSTITUTION = "constitution_block"
KIND_MISSION_STUCK = "mission_hard_stuck"
KIND_OWNER_INPUT = "owner_input_required"

HARD_KINDS = frozenset({
    KIND_MISSING_CREDENTIALS,
    KIND_MISSING_API_KEY,
    KIND_MISSING_TARGET,
    KIND_BROWSER_DISABLED,
    KIND_CAPTCHA_2FA,
    KIND_CONSTITUTION,
    KIND_MISSION_STUCK,
    KIND_OWNER_INPUT,
})

NEED_LABELS = {
    KIND_MISSING_CREDENTIALS: "credentials",
    KIND_MISSING_API_KEY: "api_key",
    KIND_MISSING_TARGET: "url_or_target",
    KIND_BROWSER_DISABLED: "enable_browser_or_local_runtime",
    KIND_CAPTCHA_2FA: "2fa_or_captcha_help",
    KIND_CONSTITUTION: "owner_override_or_rephrase",
    KIND_MISSION_STUCK: "owner_decision_or_data",
    KIND_OWNER_INPUT: "owner_input",
}


@dataclass
class OwnerBlocker:
    kind: str
    title: str
    detail: str = ""
    need: str = ""
    mission_id: str = ""
    goal_id: str = ""
    source: str = ""
    cooldown_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        if self.cooldown_key:
            return self.cooldown_key[:200]
        parts = [self.kind, self.mission_id or "", self.goal_id or "", self.title[:80]]
        return "|".join(parts)


def push_enabled() -> bool:
    raw = str(os.getenv("ISAAC_OWNER_PUSH", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def cooldown_s() -> float:
    raw = os.getenv("ISAAC_OWNER_PUSH_COOLDOWN_S")
    if raw is None or str(raw).strip() == "":
        return 6 * 3600.0  # 6 hours per same blocker
    try:
        return max(60.0, float(raw))
    except (TypeError, ValueError):
        return 6 * 3600.0


def global_min_interval_s() -> float:
    raw = os.getenv("ISAAC_OWNER_PUSH_MIN_INTERVAL_S")
    if raw is None or str(raw).strip() == "":
        return 300.0  # 5 min between any pushes
    try:
        return max(30.0, float(raw))
    except (TypeError, ValueError):
        return 300.0


def ntfy_topic() -> str:
    return (
        (os.getenv("ISAAC_NTFY_TOPIC") or "").strip()
        or (os.getenv("NTFY_TOPIC") or "").strip()
    )


def ntfy_base_url() -> str:
    return (
        (os.getenv("ISAAC_NTFY_URL") or "").strip()
        or (os.getenv("NTFY_URL") or "").strip()
        or "https://ntfy.sh"
    ).rstrip("/")


def webhook_url() -> str:
    return (os.getenv("ISAAC_OWNER_WEBHOOK_URL") or "").strip()


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"last_push_at": 0.0, "by_key": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"last_push_at": 0.0, "by_key": {}}
        data.setdefault("last_push_at", 0.0)
        data.setdefault("by_key", {})
        return data
    except Exception:
        return {"last_push_at": 0.0, "by_key": {}}


def _save_state(state: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            STATE_PATH.chmod(0o600)
        except OSError:
            pass
    except Exception as exc:
        log.debug("owner_notify state save: %s", exc)


def _log_blocker(blocker: OwnerBlocker, result: dict[str, Any]) -> None:
    try:
        BLOCKERS_LOG.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": blocker.kind,
            "title": blocker.title[:200],
            "need": blocker.need or NEED_LABELS.get(blocker.kind, ""),
            "mission_id": blocker.mission_id,
            "goal_id": blocker.goal_id,
            "source": blocker.source,
            "pushed": bool(result.get("pushed")),
            "channels": result.get("channels") or [],
            "skipped": result.get("skipped"),
        }
        with BLOCKERS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.debug("blocker log: %s", exc)


def _on_cooldown(state: dict[str, Any], key: str, *, now: float) -> bool:
    by_key = state.get("by_key") or {}
    last = float(by_key.get(key) or 0.0)
    if last and (now - last) < cooldown_s():
        return True
    last_global = float(state.get("last_push_at") or 0.0)
    if last_global and (now - last_global) < global_min_interval_s():
        return True
    return False


def _format_body(blocker: OwnerBlocker) -> str:
    need = blocker.need or NEED_LABELS.get(blocker.kind, "owner_input")
    lines = [
        f"Isaac braucht dich: {blocker.title[:120]}",
        f"Art: {blocker.kind}",
        f"Braucht: {need}",
    ]
    if blocker.detail:
        lines.append(f"Detail: {blocker.detail[:280]}")
    if blocker.mission_id:
        lines.append(f"Mission: {blocker.mission_id}")
    if blocker.goal_id:
        lines.append(f"Goal: {blocker.goal_id}")
    lines.append("Nur melden wenn wirklich blockiert — bitte im Chat antworten.")
    return "\n".join(lines)


def _send_ntfy(title: str, body: str, *, priority: str = "default") -> dict[str, Any]:
    topic = ntfy_topic()
    if not topic:
        return {"ok": False, "channel": "ntfy", "error": "no_topic"}
    url = f"{ntfy_base_url()}/{topic}"
    data = body.encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Title": title[:120],
            "Priority": priority,
            "Tags": "warning,robot",
            "Content-Type": "text/plain; charset=utf-8",
        },
    )
    token = (os.getenv("ISAAC_NTFY_TOKEN") or os.getenv("NTFY_TOKEN") or "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return {"ok": 200 <= getattr(resp, "status", 200) < 300, "channel": "ntfy"}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "channel": "ntfy", "error": f"http_{exc.code}"}
    except Exception as exc:
        return {"ok": False, "channel": "ntfy", "error": str(exc)[:120]}


def _send_webhook(title: str, body: str, blocker: OwnerBlocker) -> dict[str, Any]:
    url = webhook_url()
    if not url:
        return {"ok": False, "channel": "webhook", "error": "no_url"}
    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "kind": blocker.kind,
            "need": blocker.need or NEED_LABELS.get(blocker.kind, ""),
            "mission_id": blocker.mission_id,
            "goal_id": blocker.goal_id,
            "source": "isaac_owner_notify",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return {"ok": 200 <= getattr(resp, "status", 200) < 300, "channel": "webhook"}
    except Exception as exc:
        return {"ok": False, "channel": "webhook", "error": str(exc)[:120]}


async def _send_termux(title: str, body: str) -> dict[str, Any]:
    try:
        import asyncio
        import shlex

        content = f"{title}: {body}"[:400]
        cmd = (
            f"termux-notification --title {shlex.quote('Isaac Blocker')} "
            f"--content {shlex.quote(content)}"
        )
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=8)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return {"ok": False, "channel": "termux", "error": "timeout"}
        if proc.returncode == 0:
            return {"ok": True, "channel": "termux"}
        return {"ok": False, "channel": "termux", "error": f"rc={proc.returncode}"}
    except FileNotFoundError:
        return {"ok": False, "channel": "termux", "error": "no_termux"}
    except Exception as exc:
        return {"ok": False, "channel": "termux", "error": str(exc)[:120]}


def infer_blocker_from_text(
    text: str,
    *,
    source: str = "",
    mission_id: str = "",
    goal_id: str = "",
) -> Optional[OwnerBlocker]:
    """Heuristic: only hard, owner-actionable blockers."""
    t = (text or "").lower()
    if not t:
        return None

    if "browser_automation" in t and ("deaktiviert" in t or "disabled" in t):
        return OwnerBlocker(
            kind=KIND_BROWSER_DISABLED,
            title="Browser-Automation aus",
            detail="Isaac kann Seiten/Logins nicht bedienen (Free-Cloud oder Setting).",
            need="enable_browser_or_local_runtime",
            source=source,
            mission_id=mission_id,
            goal_id=goal_id,
            cooldown_key=f"browser_disabled|{source}",
        )

    if any(x in t for x in ("2fa", "two-factor", "captcha", "challenge", "otp", "mfa")):
        if any(x in t for x in ("fehl", "fail", "block", "required", "nötig", "noetig", "braucht")):
            return OwnerBlocker(
                kind=KIND_CAPTCHA_2FA,
                title="2FA/Captcha blockiert",
                detail=text[:200],
                need="2fa_or_captcha_help",
                source=source,
                mission_id=mission_id,
                goal_id=goal_id,
            )

    if any(
        x in t
        for x in (
            "keine credentials",
            "credentials fehlen",
            "login fehlt",
            "passwort fehlt",
            "password missing",
            "no credentials",
            "needs credentials",
            "login erforderlich",
        )
    ):
        return OwnerBlocker(
            kind=KIND_MISSING_CREDENTIALS,
            title="Login-Daten fehlen",
            detail=text[:200],
            need="credentials",
            source=source,
            mission_id=mission_id,
            goal_id=goal_id,
        )

    if any(
        x in t
        for x in (
            "api-key fehlt",
            "api key fehlt",
            "api_key missing",
            "missing api key",
            "token fehlt",
            "kein nutzbarer primary",
        )
    ):
        return OwnerBlocker(
            kind=KIND_MISSING_API_KEY,
            title="API-Key fehlt",
            detail=text[:200],
            need="api_key",
            source=source,
            mission_id=mission_id,
            goal_id=goal_id,
        )

    if any(
        x in t
        for x in (
            "no_target_url",
            "ziel unklar",
            "needs_target",
            "url fehlt",
            "kein ziel",
        )
    ):
        return OwnerBlocker(
            kind=KIND_MISSING_TARGET,
            title="Ziel-URL fehlt",
            detail=text[:200],
            need="url_or_target",
            source=source,
            mission_id=mission_id,
            goal_id=goal_id,
        )

    if "constitution" in t and any(x in t for x in ("block", "verboten", "denied")):
        return OwnerBlocker(
            kind=KIND_CONSTITUTION,
            title="Verfassung blockiert Aktion",
            detail=text[:200],
            need="owner_override_or_rephrase",
            source=source,
            mission_id=mission_id,
            goal_id=goal_id,
        )

    return None


async def notify_owner_blocker(
    blocker: OwnerBlocker,
    *,
    force: bool = False,
    on_note: Optional[Any] = None,
) -> dict[str, Any]:
    """Push only for hard blockers and only when not on cooldown."""
    if not push_enabled() and not force:
        return {"ok": True, "pushed": False, "skipped": "push_disabled"}

    if blocker.kind not in HARD_KINDS:
        return {"ok": True, "pushed": False, "skipped": "not_hard_blocker"}

    now = time.time()
    state = _load_state()
    key = blocker.key()
    if not force and _on_cooldown(state, key, now=now):
        result = {"ok": True, "pushed": False, "skipped": "cooldown", "key": key}
        _log_blocker(blocker, result)
        return result

    title = f"Isaac: {blocker.title}"[:100]
    body = _format_body(blocker)
    channels: list[dict[str, Any]] = []

    # Sync channels first
    ntfy_r = _send_ntfy(title, body, priority="high")
    channels.append(ntfy_r)
    wh_r = _send_webhook(title, body, blocker)
    channels.append(wh_r)
    # Termux async
    try:
        termux_r = await _send_termux(title, body)
        channels.append(termux_r)
    except Exception as exc:
        channels.append({"ok": False, "channel": "termux", "error": str(exc)[:80]})

    any_ok = any(c.get("ok") for c in channels)
    # Always surface in background notes if provided
    note = f"[Owner-Push] {blocker.kind}: {blocker.title} (need={blocker.need or NEED_LABELS.get(blocker.kind, '')})"
    if on_note:
        try:
            on_note(note)
        except Exception:
            pass

    if any_ok or force:
        state["last_push_at"] = now
        by_key = dict(state.get("by_key") or {})
        by_key[key] = now
        # prune old keys (> 50)
        if len(by_key) > 50:
            items = sorted(by_key.items(), key=lambda kv: kv[1], reverse=True)[:50]
            by_key = dict(items)
        state["by_key"] = by_key
        _save_state(state)

    result = {
        "ok": True,
        "pushed": any_ok,
        "channels": channels,
        "key": key,
        "kind": blocker.kind,
        "note": note,
    }
    # If no channel configured, still "pushed" to log as local-only notify
    if not any_ok and not ntfy_topic() and not webhook_url():
        result["pushed"] = True
        result["channels"].append({"ok": True, "channel": "local_log"})
        state["last_push_at"] = now
        by_key = dict(state.get("by_key") or {})
        by_key[key] = now
        state["by_key"] = by_key
        _save_state(state)

    _log_blocker(blocker, result)
    AuditLog.action(
        "OwnerNotify",
        "blocker",
        f"{blocker.kind} pushed={result.get('pushed')} key={key[:60]}",
        erfolg=bool(result.get("pushed")),
    )
    log.info(
        "Owner-Push kind=%s pushed=%s channels=%s",
        blocker.kind,
        result.get("pushed"),
        [c.get("channel") for c in channels],
    )
    return result


async def maybe_notify_from_text(
    text: str,
    *,
    source: str = "",
    mission_id: str = "",
    goal_id: str = "",
    force: bool = False,
    on_note: Optional[Any] = None,
) -> dict[str, Any]:
    blocker = infer_blocker_from_text(
        text, source=source, mission_id=mission_id, goal_id=goal_id
    )
    if not blocker:
        return {"ok": True, "pushed": False, "skipped": "no_hard_blocker"}
    return await notify_owner_blocker(
        blocker, force=force, on_note=on_note
    )


def status() -> dict[str, Any]:
    state = _load_state()
    return {
        "enabled": push_enabled(),
        "ntfy_topic_set": bool(ntfy_topic()),
        "ntfy_url": ntfy_base_url(),
        "webhook_set": bool(webhook_url()),
        "cooldown_s": cooldown_s(),
        "min_interval_s": global_min_interval_s(),
        "last_push_at": state.get("last_push_at"),
        "tracked_keys": len(state.get("by_key") or {}),
    }
