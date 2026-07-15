from __future__ import annotations

"""Owner-only: Login-Kombinationen lokal testen.

Credentials gehören NUR in data/owner_login_probe_config.json (gitignored).
Keine Klartext-Passwörter oder privaten E-Mails im Quellcode.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

from audit import AuditLog
from config import DATA_DIR, is_owner_equivalent_mode

log = logging.getLogger("Isaac.OwnerLoginProbe")

CONFIG_PATH = DATA_DIR / "owner_login_probe_config.json"
RESULTS_PATH = DATA_DIR / "owner_login_probe_results.json"

# Leere Defaults — echte Werte nur aus lokaler Config / Funktionsargumenten.
DEFAULT_EMAILS: tuple[str, ...] = ()
DEFAULT_PASSWORDS: tuple[str, ...] = ()

PROBE_DELAY_SEC = 4.0


@dataclass(frozen=True)
class ProbeTarget:
    target_id: str
    login_url: str
    domain: str
    email_selector: str = "input[type='email'], input[name='identifier']"
    password_selector: str = "input[type='password'], input[name='Passwd']"
    next_labels: tuple[str, ...] = ("Weiter", "Next", "Fortfahren")
    success_url_markers: tuple[str, ...] = ()
    failure_url_markers: tuple[str, ...] = ("signin", "login", "challenge", "rejected")


def require_owner_probe() -> Optional[str]:
    if is_owner_equivalent_mode():
        return None
    return "Login-Probe nur im Admin-Modus."


def load_probe_config() -> dict[str, Any]:
    """Lädt Owner-Probe-Config. Schreibt keine Credentials in den Code-Tree."""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Probe-Config unlesbar: %s", exc)
            return {
                "emails": [],
                "passwords": [],
                "delay_sec": PROBE_DELAY_SEC,
                "targets": ["google", "webde"],
            }
        if not isinstance(data, dict):
            return {
                "emails": [],
                "passwords": [],
                "delay_sec": PROBE_DELAY_SEC,
                "targets": ["google", "webde"],
            }
        return data
    # Scaffold ohne Secrets — Owner füllt manuell.
    payload = {
        "emails": list(DEFAULT_EMAILS),
        "passwords": list(DEFAULT_PASSWORDS),
        "delay_sec": PROBE_DELAY_SEC,
        "targets": ["google", "webde"],
        "_note": "E-Mails und Passwörter hier eintragen. Datei bleibt unter data/ (gitignored).",
    }
    CONFIG_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass
    return payload


def probe_targets(selected: list[str]) -> list[ProbeTarget]:
    catalog = {
        "google": ProbeTarget(
            target_id="google",
            login_url="https://accounts.google.com/signin/v2/identifier",
            domain="accounts.google.com",
            success_url_markers=("myaccount.google.com", "mail.google.com", "google.com/webhp"),
            failure_url_markers=("signin", "challenge", "disabled", "rejected", "wrongpassword"),
        ),
        "webde": ProbeTarget(
            target_id="webde",
            login_url="https://web.de/",
            domain="web.de",
            email_selector="input[name='username'], input[type='email'], input[name='login']",
            password_selector="input[type='password'], input[name='password']",
            next_labels=("Login", "Anmelden", "Weiter"),
            success_url_markers=("web.de/logout", "navigator.web.de"),
            failure_url_markers=("login", "fehler", "error"),
        ),
    }
    return [catalog[key] for key in selected if key in catalog]


def _mask_email(email: str) -> str:
    if "@" not in email:
        return email[:2] + "..."
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"**@{domain}"
    return f"{local[:2]}...{local[-1:]}@{domain}"


def _mask_password(password: str) -> str:
    if len(password) <= 2:
        return "****"
    return password[:2] + "..." + password[-1:]


async def _click_first_label(page, labels: tuple[str, ...]) -> bool:
    for label in labels:
        try:
            await page.get_by_role("button", name=label, exact=False).first.click(timeout=2500)
            return True
        except Exception:
            try:
                await page.get_by_text(label, exact=False).first.click(timeout=1500)
                return True
            except Exception:
                continue
    return False


def _url_looks_success(url: str, target: ProbeTarget) -> bool:
    lower = (url or "").lower()
    if any(marker in lower for marker in target.failure_url_markers):
        return False
    if target.success_url_markers:
        return any(marker in lower for marker in target.success_url_markers)
    return "signin" not in lower and "login" not in lower


async def _fill_google_login(page, email: str, password: str) -> Optional[str]:
    await page.goto("https://accounts.google.com/signin/v2/identifier", wait_until="domcontentloaded", timeout=25000)
    await asyncio.sleep(1.0)
    email_locators = ("#identifierId", "input[name='identifier']", "input[type='email']")
    for sel in email_locators:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=4000)
            await loc.fill(email, timeout=4000)
            break
        except Exception:
            continue
    else:
        return "email-feld nicht gefunden"
    for sel in ("#identifierNext", "button:has-text('Weiter')", "button:has-text('Next')"):
        try:
            await page.locator(sel).first.click(timeout=3000)
            break
        except Exception:
            continue
    await asyncio.sleep(1.5)
    pwd_locators = ("input[name='Passwd']", "input[type='password']:not([aria-hidden='true'])", "input[type='password']")
    for sel in pwd_locators:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=8000)
            if await loc.get_attribute("aria-hidden") == "true":
                continue
            await loc.fill(password, timeout=5000)
            break
        except Exception:
            continue
    else:
        return "passwort-feld nicht sichtbar (evtl. captcha/2fa)"
    for sel in ("#passwordNext", "button:has-text('Weiter')", "button:has-text('Next')"):
        try:
            await page.locator(sel).first.click(timeout=3000)
            break
        except Exception:
            continue
    await page.wait_for_load_state("domcontentloaded", timeout=15000)
    return None


async def _probe_single(
    page,
    target: ProbeTarget,
    email: str,
    password: str,
) -> dict[str, Any]:
    try:
        if target.target_id == "google":
            err = await _fill_google_login(page, email, password)
            if err:
                return {"ok": False, "reason": err, "url": page.url}
        else:
            await page.goto(target.login_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1.5)
            try:
                await page.locator(target.email_selector).first.fill(email, timeout=5000)
                await asyncio.sleep(0.4)
                await _click_first_label(page, target.next_labels)
                await asyncio.sleep(1.2)
            except Exception:
                pass
            try:
                await page.locator(target.password_selector).first.fill(password, timeout=6000)
                await asyncio.sleep(0.4)
                await _click_first_label(page, target.next_labels + ("Anmelden", "Sign in"))
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception as exc:
                return {"ok": False, "reason": f"passwort-schritt: {exc}", "url": page.url}
        await asyncio.sleep(2.0)
        url = page.url
        body = ""
        try:
            body = (await page.locator("body").inner_text(timeout=3000))[:1200].lower()
        except Exception:
            body = ""
        if any(token in body for token in ("falsches passwort", "wrong password", "couldn't sign you in", "konto gesperrt")):
            return {"ok": False, "reason": "anmeldung abgelehnt", "url": url}
        if _url_looks_success(url, target):
            return {"ok": True, "url": url}
        if "challenge" in url.lower() or "2-step" in body or "bestätigung" in body:
            return {"ok": False, "reason": "2fa/captcha erforderlich", "url": url}
        return {"ok": False, "reason": "kein erfolg erkannt", "url": url}
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "url": getattr(page, "url", "")}


async def run_login_probe(
    *,
    emails: Optional[list[str]] = None,
    passwords: Optional[list[str]] = None,
    targets: Optional[list[str]] = None,
    delay_sec: float = PROBE_DELAY_SEC,
    save_success_to_browser: bool = True,
) -> dict[str, Any]:
    blocked = require_owner_probe()
    if blocked:
        return {"ok": False, "error": blocked}

    cfg = load_probe_config()
    email_list = [e.strip() for e in (emails or cfg.get("emails") or []) if e and "@" in e]
    password_list = [p for p in (passwords or cfg.get("passwords") or []) if p]
    target_keys = targets or cfg.get("targets") or ["google"]
    delay = float(cfg.get("delay_sec") or delay_sec)

    if not email_list or not password_list:
        return {"ok": False, "error": "E-Mails oder Passwörter fehlen in owner_login_probe_config.json"}

    from browser import get_browser

    browser = get_browser()
    if not browser.cfg.browser_automation:
        return {"ok": False, "error": "browser_automation ist deaktiviert"}

    results: list[dict[str, Any]] = []
    successes: list[dict[str, Any]] = []

    for target in probe_targets(target_keys):
        inst = await browser.ensure_instance(
            f"probe-{target.target_id}",
            target.login_url,
            name=f"Login Probe {target.target_id}",
        )
        page = inst.page
        if not page:
            return {"ok": False, "error": f"Browser-Instanz für {target.target_id} nicht verfügbar"}

        for email in email_list:
            for password in password_list:
                # Frischer Kontext pro Versuch (Cookies leeren)
                try:
                    await inst.context.clear_cookies()
                except Exception:
                    pass
                attempt = await _probe_single(page, target, email, password)
                row = {
                    "target": target.target_id,
                    "email": email,
                    "email_masked": _mask_email(email),
                    "password_masked": _mask_password(password),
                    "ok": bool(attempt.get("ok")),
                    "reason": attempt.get("reason", ""),
                    "url": attempt.get("url", ""),
                    "ts": time.time(),
                }
                results.append(row)
                AuditLog.action(
                    "OwnerLoginProbe",
                    target.target_id,
                    f"{row['email_masked']} ok={row['ok']} reason={row.get('reason', '')[:80]}",
                    level=40,
                )
                if row["ok"]:
                    successes.append(row)
                    if save_success_to_browser:
                        browser.add_credential(
                            target.domain,
                            target.login_url,
                            email,
                            password,
                        )
                log.info(
                    "Probe %s %s -> %s",
                    target.target_id,
                    row["email_masked"],
                    "OK" if row["ok"] else row.get("reason", "fail"),
                )
                await asyncio.sleep(delay)

    payload = {
        "ok": True,
        "tested": len(results),
        "success_count": len(successes),
        "successes": [
            {
                "target": s["target"],
                "email_masked": s["email_masked"],
                "password_masked": s["password_masked"],
                "url": s.get("url", ""),
            }
            for s in successes
        ],
        "results": [
            {
                "target": r["target"],
                "email_masked": r["email_masked"],
                "password_masked": r["password_masked"],
                "ok": r["ok"],
                "reason": r.get("reason", ""),
            }
            for r in results
        ],
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        RESULTS_PATH.chmod(0o600)
    except OSError:
        pass
    return payload


def format_probe_report(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"[Login-Probe] Fehler: {result.get('error', 'unbekannt')}"
    lines = [
        f"[Login-Probe] Getestet: {result.get('tested', 0)} | Erfolge: {result.get('success_count', 0)}",
    ]
    for row in result.get("successes") or []:
        lines.append(
            f"  ✓ {row.get('target')}: {row.get('email_masked')} ({row.get('password_masked')})"
        )
    fails = [r for r in result.get("results") or [] if not r.get("ok")]
    if fails and not result.get("successes"):
        lines.append("Keine erfolgreiche Kombination.")
        for row in fails[:6]:
            lines.append(
                f"  ✗ {row.get('target')} {row.get('email_masked')}: {row.get('reason') or 'fail'}"
            )
    lines.append(f"Details: {RESULTS_PATH}")
    return "\n".join(lines)