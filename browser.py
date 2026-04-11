"""
Isaac – Browser-Automation (Playwright)
=========================================
Kernstück des Multi-Instanz-Modus.

Jede KI-Instanz = eine URL = ein isolierter Browser-Context.
Isaac navigiert zu den URLs, loggt sich ein, schickt Nachrichten
und liest Antworten aus — wie ein Mensch, aber automatisiert.

Architektur:
  BrowserManager        → verwaltet alle Instanzen
  KIInstance            → eine KI-Chat-Session (ein Browser-Context)
  LoginProfile          → gespeicherte Login-Daten pro Domain
  SiteAdapter           → URL-spezifische Selektoren (erweiterbar)

Instanzen sind vollständig isoliert:
  - Eigene Cookies / Sessions
  - Eigene LocalStorage
  - Kein Cross-Contamination zwischen Instanzen

Auto-Login:
  - Credentials in encrypted local store
  - Pro Domain: Username, Passwort, Login-URL, Selektoren
  - Wird beim Start automatisch durchgeführt
"""

import asyncio
import json
import time
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, Callable

from config  import get_config, DATA_DIR
from audit   import AuditLog
from privilege import get_gate, isaac_ctx
from secrets_store import get_secrets_store

log = logging.getLogger("Isaac.Browser")

# Credentials-Datei (verschlüsselt gespeichert)
CREDS_PATH = DATA_DIR / "browser_creds.json"


# ── Login-Profil ───────────────────────────────────────────────────────────────
@dataclass
class LoginProfile:
    domain:        str
    login_url:     str
    username:      str
    password:      str   # Wird verschlüsselt gespeichert
    user_selector: str   = "input[type='email'], input[name='email'], input[name='username']"
    pass_selector: str   = "input[type='password']"
    submit_selector: str = "button[type='submit'], input[type='submit']"
    logged_in_check: str = ""  # CSS-Selector der nach Login sichtbar ist
    extra_steps:   list  = field(default_factory=list)  # Für 2FA etc.


# ── Site-Adapter ──────────────────────────────────────────────────────────────
# Bekannte KI-Chat-Seiten: URL-Pattern → Chat-Selektoren
SITE_ADAPTERS: dict[str, dict] = {
    "chat.openai.com": {
        "input":    "#prompt-textarea",
        "send":     "button[data-testid='send-button']",
        "response": "[data-message-author-role='assistant']:last-child",
        "wait_ms":  3000,
    },
    "claude.ai": {
        "input":    "div[contenteditable='true']",
        "send":     "button[aria-label='Send message']",
        "response": "[data-is-streaming='false']:last-child",
        "wait_ms":  5000,
    },
    "gemini.google.com": {
        "input":    "rich-textarea",
        "send":     "button.send-button",
        "response": "model-response:last-child .response-content",
        "wait_ms":  4000,
    },
    "copilot.microsoft.com": {
        "input":    "#userInput",
        "send":     "button#sendButton",
        "response": ".ac-textBlock:last-child",
        "wait_ms":  5000,
    },
    "huggingface.co": {
        "input":    "textarea",
        "send":     "button[type='submit']",
        "response": ".message.bot:last-child",
        "wait_ms":  4000,
    },
    "poe.com": {
        "input":    "textarea[class*='GrowingTextArea']",
        "send":     "button[class*='SendButton']",
        "response": "[class*='Message_humanMessageBubble']:last-child",
        "wait_ms":  4000,
    },
    "you.com": {
        "input":    "textarea[placeholder*='Ask']",
        "send":     "button[aria-label='Submit']",
        "response": "[data-testid='youchat-text']:last-child",
        "wait_ms":  5000,
    },
    "perplexity.ai": {
        "input":    "textarea",
        "send":     "button[aria-label='Submit']",
        "response": ".prose:last-child",
        "wait_ms":  6000,
    },
    "mistral.ai": {
        "input":    "textarea",
        "send":     "button[type='submit']",
        "response": ".assistant-message:last-child",
        "wait_ms":  4000,
    },
    "groq.com": {
        "input":    "textarea",
        "send":     "button[aria-label='Send']",
        "response": ".message-content:last-child",
        "wait_ms":  3000,
    },
    # Fallback für unbekannte Sites
    "_default": {
        "input":    "textarea, input[type='text']",
        "send":     "button[type='submit'], button:last-child",
        "response": "main p:last-child, .response:last-child, .message:last-child",
        "wait_ms":  5000,
    },
}

SITE_CATALOG_META: dict[str, dict[str, str]] = {
    "chat.openai.com": {
        "site_id": "chatgpt",
        "label": "ChatGPT",
        "url": "https://chat.openai.com",
    },
    "claude.ai": {
        "site_id": "claude",
        "label": "Claude",
        "url": "https://claude.ai",
    },
    "gemini.google.com": {
        "site_id": "gemini",
        "label": "Gemini",
        "url": "https://gemini.google.com",
    },
    "copilot.microsoft.com": {
        "site_id": "copilot",
        "label": "Copilot",
        "url": "https://copilot.microsoft.com",
    },
    "huggingface.co": {
        "site_id": "huggingface",
        "label": "Hugging Face Chat",
        "url": "https://huggingface.co/chat",
    },
    "poe.com": {
        "site_id": "poe",
        "label": "Poe",
        "url": "https://poe.com",
    },
    "you.com": {
        "site_id": "you",
        "label": "You.com",
        "url": "https://you.com",
    },
    "perplexity.ai": {
        "site_id": "perplexity",
        "label": "Perplexity",
        "url": "https://perplexity.ai",
    },
    "mistral.ai": {
        "site_id": "mistral",
        "label": "Mistral",
        "url": "https://mistral.ai",
    },
    "groq.com": {
        "site_id": "groq",
        "label": "Groq",
        "url": "https://groq.com",
    },
}


def get_adapter(url: str) -> dict:
    for domain, adapter in SITE_ADAPTERS.items():
        if domain != "_default" and domain in url:
            return adapter
    return SITE_ADAPTERS["_default"]


# ── KI-Instanz ────────────────────────────────────────────────────────────────
@dataclass
class KIInstance:
    id:         str
    url:        str
    name:       str
    aktiv:      bool  = False
    eingeloggt: bool  = False
    fehler:     int   = 0
    letzter_einsatz: float = 0.0
    antworten:  int   = 0
    avg_latenz: float = 0.0
    context     = None   # playwright BrowserContext
    page        = None   # playwright Page

    def to_dict(self) -> dict:
        return {
            "id":        self.id,
            "url":       self.url,
            "name":      self.name,
            "aktiv":     self.aktiv,
            "eingeloggt": self.eingeloggt,
            "fehler":    self.fehler,
            "antworten": self.antworten,
            "avg_latenz": round(self.avg_latenz, 2),
        }

    def update_latenz(self, sek: float):
        n = self.antworten + 1
        self.avg_latenz = (self.avg_latenz * self.antworten + sek) / n
        self.antworten  = n


# ── Browser-Manager ───────────────────────────────────────────────────────────
class BrowserManager:
    """
    Verwaltet alle KI-Browser-Instanzen.

    Beim Start:
      1. Playwright initialisieren
      2. Für jede konfigurierte URL: Browser-Context erstellen
      3. Auto-Login wenn Credentials vorhanden
      4. Instanzen als "bereit" markieren

    Dispatcher nutzt dann ask_instance() oder broadcast().
    """

    def __init__(self):
        self.cfg        = get_config()
        self._instances: dict[str, KIInstance] = {}
        self._pw        = None    # playwright instance
        self._browser   = None   # chromium browser
        self._creds:    dict[str, LoginProfile] = {}
        self._bereit    = False
        self._lock      = asyncio.Lock()
        self._load_creds()
        log.info("BrowserManager initialisiert")

    def _browser_allowed(self, url: str = "") -> bool:
        if not self.cfg.browser_automation:
            return False
        if url and not self.cfg.browser_external_sites:
            return False
        return True

    # ── Startup ───────────────────────────────────────────────────────────────
    async def _ensure_runtime(self):
        if self._browser is not None and self._pw is not None:
            return True
        if not self._browser_allowed():
            log.warning("Browser-Automation durch Runtime-Policy deaktiviert")
            return False
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.error(
                "Playwright nicht installiert!\n"
                "Installiere mit: pip install playwright && playwright install chromium"
            )
            return False
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.cfg.browser.headless,
            slow_mo=self.cfg.browser.slowmo,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        return True

    async def start(self, urls: list[dict]):
        """
        urls = [{"id": "claude1", "url": "https://claude.ai", "name": "Claude #1"}, ...]
        """
        if not await self._ensure_runtime():
            return

        log.info(f"Browser startet mit {len(urls)} Instanzen...")

        # Instanzen sequentiell erstellen (nicht alle gleichzeitig)
        for ui in urls:
            try:
                inst = await self._create_instance(ui)
                self._instances[inst.id] = inst
                await asyncio.sleep(1.5)   # Sanfter Start
            except Exception as e:
                log.error(f"Instanz {ui.get('id')} fehlgeschlagen: {e}")

        self._bereit = True
        log.info(
            f"BrowserManager bereit │ "
            f"{len([i for i in self._instances.values() if i.aktiv])} Instanzen aktiv"
        )

    async def _create_instance(self, ui: dict) -> KIInstance:
        inst = KIInstance(
            id   = ui["id"],
            url  = ui["url"],
            name = ui.get("name", ui["id"]),
        )

        # Isolierter Context (eigene Cookies, Session, Storage)
        inst.context = await self._browser.new_context(
            viewport         = {"width": 1280, "height": 900},
            user_agent       = (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            java_script_enabled = True,
            ignore_https_errors = True,
        )
        inst.page = await inst.context.new_page()

        # Automation-Detection deaktivieren
        await inst.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

        # Zur URL navigieren
        log.info(f"Instanz {inst.id}: Lade {inst.url}")
        try:
            await inst.page.goto(inst.url, wait_until="networkidle", timeout=30000)
            inst.aktiv = True
        except Exception as e:
            log.warning(f"Instanz {inst.id}: Navigation fehlgeschlagen: {e}")
            inst.fehler += 1

        # Auto-Login versuchen
        if inst.aktiv:
            await self._auto_login(inst)

        AuditLog.instance(inst.id, "created", detail=inst.url)
        return inst

    def _normalize_url(self, url: str) -> str:
        raw = (url or "").strip()
        if raw and "://" not in raw:
            raw = f"https://{raw}"
        return raw

    async def ensure_instance(self, instance_id: str, url: str, name: str = "") -> KIInstance:
        target_url = self._normalize_url(url)
        if not self._browser_allowed(target_url):
            raise PermissionError("Browser-Nutzung ist durch Runtime-Policy deaktiviert")
        if not await self._ensure_runtime():
            raise RuntimeError("Browser-Runtime nicht verfügbar")

        inst = self._instances.get(instance_id)
        if inst and inst.aktiv:
            if target_url and inst.url != target_url:
                inst.url = target_url
                await inst.page.goto(target_url, wait_until="networkidle", timeout=30000)
            return inst

        inst = await self._create_instance({
            "id": instance_id,
            "url": target_url,
            "name": name or instance_id,
        })
        self._instances[inst.id] = inst
        return inst

    # ── Auto-Login ─────────────────────────────────────────────────────────────
    async def _auto_login(self, inst: KIInstance):
        """Loggt sich automatisch ein wenn Credentials vorhanden."""
        from urllib.parse import urlparse
        domain = urlparse(inst.url).netloc

        cred = self._creds.get(domain) or self._creds.get(
            domain.replace("www.", "")
        )
        if not cred:
            log.debug(f"Keine Credentials für {domain}")
            return

        log.info(f"Auto-Login: {inst.id} @ {domain}")
        try:
            # Login-Seite aufrufen
            await inst.page.goto(cred.login_url, wait_until="networkidle",
                                 timeout=20000)
            await asyncio.sleep(1.5)

            # Username eingeben
            try:
                await inst.page.fill(cred.user_selector, cred.username)
                await asyncio.sleep(0.5)
            except Exception:
                log.warning(f"Username-Feld nicht gefunden: {cred.user_selector}")

            # Passwort eingeben
            try:
                await inst.page.fill(cred.pass_selector, cred.password)
                await asyncio.sleep(0.5)
            except Exception:
                log.warning(f"Passwort-Feld nicht gefunden")

            # Absenden
            try:
                await inst.page.click(cred.submit_selector)
                await inst.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                log.warning(f"Submit fehlgeschlagen")

            # Erfolg prüfen
            await asyncio.sleep(2)
            if cred.logged_in_check:
                try:
                    await inst.page.wait_for_selector(
                        cred.logged_in_check, timeout=8000
                    )
                    inst.eingeloggt = True
                    log.info(f"✓ Login {inst.id} @ {domain}")
                except Exception:
                    log.warning(f"Login-Check fehlgeschlagen: {inst.id}")
            else:
                # Kein Check-Selector → Annahme: OK wenn kein Error
                inst.eingeloggt = True
                log.info(f"✓ Login {inst.id} @ {domain} (kein Check)")

            # Zurück zur Chat-URL
            if inst.url != cred.login_url:
                await inst.page.goto(inst.url, wait_until="networkidle",
                                     timeout=20000)

            AuditLog.instance(inst.id, "logged_in", detail=domain)

        except Exception as e:
            log.error(f"Auto-Login fehlgeschlagen {inst.id}: {e}")
            AuditLog.error("Browser", f"Login {inst.id}", str(e)[:100])

    # ── Nachricht senden ───────────────────────────────────────────────────────
    async def ask_instance(self, instance_id: str,
                           prompt: str,
                           timeout: float = 60.0) -> str:
        """
        Schickt einen Prompt an eine KI-Instanz per Browser.
        Gibt die Antwort als Text zurück.
        """
        inst = self._instances.get(instance_id)
        if not inst or not inst.aktiv:
            return f"[Browser] Instanz {instance_id} nicht verfügbar"

        async with self._lock:
            t0 = time.monotonic()
            try:
                adapter = get_adapter(inst.url)
                page    = inst.page

                # Input-Feld finden und füllen
                await page.wait_for_selector(
                    adapter["input"], timeout=10000
                )

                # Eingabe simulieren (menschlich)
                await page.click(adapter["input"])
                await asyncio.sleep(0.3)

                # Text schrittweise eingeben (weniger detektierbar)
                await page.fill(adapter["input"], "")
                await page.type(adapter["input"], prompt, delay=15)
                await asyncio.sleep(0.5)

                # Senden (Enter oder Button)
                try:
                    await page.click(adapter["send"], timeout=3000)
                except Exception:
                    await page.keyboard.press("Enter")

                # Auf Antwort warten
                await asyncio.sleep(adapter["wait_ms"] / 1000)

                # Antwort lesen
                antwort = await self._extract_response(page, adapter, timeout)

                latenz = time.monotonic() - t0
                inst.update_latenz(latenz)
                inst.letzter_einsatz = time.monotonic()

                AuditLog.instance(instance_id, "answered",
                                  detail=f"{len(antwort.split())} Wörter")
                return antwort

            except Exception as e:
                inst.fehler += 1
                log.error(f"Instanz {instance_id}: {e}")
                AuditLog.error("Browser", f"ask:{instance_id}", str(e)[:100])

                # Neustart versuchen wenn zu viele Fehler
                if inst.fehler >= self.cfg.browser.max_errors_per_instance:
                    await self._restart_instance(inst)
                return f"[Browser-Fehler:{instance_id}] {e}"

    async def _extract_response(self, page, adapter: dict,
                                 timeout: float) -> str:
        """Wartet und extrahiert die KI-Antwort."""
        deadline = time.monotonic() + timeout
        selector = adapter["response"]

        while time.monotonic() < deadline:
            try:
                # Auf Response-Element warten
                el = await page.wait_for_selector(selector, timeout=5000)
                if el:
                    text = await el.inner_text()
                    if text and len(text.strip()) > 10:
                        # Prüfen ob noch gestreamt wird
                        await asyncio.sleep(1.5)
                        text2 = await el.inner_text()
                        if text == text2:   # Stabil → fertig
                            return text.strip()
            except Exception:
                pass
            await asyncio.sleep(1.0)

        # Fallback: letzten sichtbaren Text nehmen
        try:
            text = await page.inner_text("body")
            # Nur letzten Teil (Antwort ist meist am Ende)
            return text[-2000:].strip()
        except Exception:
            return "[Keine Antwort extrahiert]"

    def _extract_candidate_secret(self, text: str) -> str:
        if not text:
            return ""
        candidates = re.findall(r"[A-Za-z0-9_\-]{20,}", text)
        if not candidates:
            return ""
        candidates.sort(key=len, reverse=True)
        return candidates[0]

    def _resolve_target(self, page, action: dict):
        selector = (action.get("selector") or "").strip()
        text = (action.get("text") or "").strip()
        if selector:
            return page.locator(selector).first
        if text:
            return page.get_by_text(text, exact=bool(action.get("exact", False))).first
        raise ValueError("Browser-Aktion benötigt selector oder text")

    async def run_flow(self, instance_id: str, start_url: str, actions: list[dict], name: str = "") -> dict[str, Any]:
        inst = await self.ensure_instance(instance_id, start_url, name=name or instance_id)
        page = inst.page
        memory: dict[str, str] = {}
        steps: list[dict[str, Any]] = []

        for idx, action in enumerate(actions or [], start=1):
            kind = (action.get("action") or "").strip().lower()
            try:
                if kind == "goto":
                    url = self._normalize_url(action.get("url") or start_url)
                    if not self._browser_allowed(url):
                        raise PermissionError("Externe Browser-Ziele sind deaktiviert")
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    steps.append({"step": idx, "action": kind, "url": page.url, "ok": True})
                    continue

                if kind == "wait":
                    seconds = max(0.1, float(action.get("seconds", 1.0)))
                    await asyncio.sleep(seconds)
                    steps.append({"step": idx, "action": kind, "seconds": seconds, "ok": True})
                    continue

                if kind == "press":
                    key = (action.get("key") or "Enter").strip() or "Enter"
                    await page.keyboard.press(key)
                    steps.append({"step": idx, "action": kind, "key": key, "ok": True})
                    continue

                target = self._resolve_target(page, action)
                if kind == "click":
                    await target.click(timeout=10000)
                    steps.append({"step": idx, "action": kind, "target": action.get("selector") or action.get("text"), "ok": True})
                    continue

                if kind == "fill":
                    value = str(action.get("value") or "")
                    await target.fill(value, timeout=10000)
                    steps.append({"step": idx, "action": kind, "target": action.get("selector") or action.get("text"), "ok": True})
                    continue

                if kind in {"extract_text", "extract_value"}:
                    value = await (target.input_value(timeout=10000) if kind == "extract_value" else target.inner_text(timeout=10000))
                    slot = (action.get("save_as") or f"value_{idx}").strip()
                    memory[slot] = value.strip()
                    steps.append({"step": idx, "action": kind, "save_as": slot, "length": len(memory[slot]), "ok": True})
                    continue

                if kind == "store_secret":
                    slot = (action.get("from_var") or "").strip()
                    secret_ref = (action.get("ref") or "").strip()
                    if not self.cfg.browser_external_sites:
                        raise PermissionError("Secret-Import via Browser ist deaktiviert")
                    if not slot or slot not in memory:
                        raise ValueError("store_secret benötigt from_var eines extrahierten Werts")
                    if not secret_ref:
                        raise ValueError("store_secret benötigt ref")
                    secret = self._extract_candidate_secret(memory[slot]) or memory[slot]
                    get_secrets_store().set_secret(secret_ref, secret, kind="browser_import")
                    steps.append({"step": idx, "action": kind, "ref": secret_ref, "ok": True})
                    continue

                raise ValueError(f"Nicht unterstützte Browser-Aktion: {kind}")
            except Exception as e:
                steps.append({"step": idx, "action": kind, "ok": False, "error": str(e)})
                return {
                    "ok": False,
                    "instance_id": inst.id,
                    "current_url": page.url,
                    "steps": steps,
                    "memory": memory,
                    "error": str(e),
                }

        return {
            "ok": True,
            "instance_id": inst.id,
            "current_url": page.url,
            "steps": steps,
            "memory": memory,
        }

    async def provision_openrouter_token(self, secret_ref: str = "OPENROUTER_API_KEY", key_name: str = "Isaac") -> dict[str, Any]:
        plan = [
            {"action": "goto", "url": "https://openrouter.ai/settings/keys"},
            {"action": "wait", "seconds": 1.2},
        ]
        result = await self.run_flow("openrouter", "https://openrouter.ai/settings/keys", plan, name="OpenRouter")
        if not result.get("ok"):
            return result

        inst = self._instances.get("openrouter")
        if not inst or not inst.page:
            return {"ok": False, "error": "OpenRouter-Instanz nicht verfügbar"}

        page = inst.page
        create_labels = ["Create Key", "New Key", "Create API Key", "Generate Key", "New Token"]
        clicked = False
        for label in create_labels:
            try:
                await page.get_by_text(label, exact=False).first.click(timeout=2500)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            return {"ok": False, "error": "OpenRouter-Key-Button nicht gefunden", "current_url": page.url}

        try:
            await asyncio.sleep(1.0)
            for selector in ["input[name*=name]", "input[placeholder*=name]", "input[type='text']"]:
                try:
                    await page.locator(selector).first.fill(key_name, timeout=1500)
                    break
                except Exception:
                    continue
            for label in ["Create", "Generate", "Save", "Submit"]:
                try:
                    await page.get_by_text(label, exact=False).last.click(timeout=1500)
                    break
                except Exception:
                    continue
            await asyncio.sleep(1.5)
        except Exception as e:
            return {"ok": False, "error": f"OpenRouter-Key-Dialog fehlgeschlagen: {e}", "current_url": page.url}

        candidates: list[str] = []
        selectors = ["code", "input[readonly]", "input[type='text']", "textarea", "[data-token]"]
        for selector in selectors:
            try:
                loc = page.locator(selector)
                count = await loc.count()
                for idx in range(min(count, 5)):
                    node = loc.nth(idx)
                    text = ""
                    try:
                        text = await node.input_value(timeout=500)
                    except Exception:
                        try:
                            text = await node.inner_text(timeout=500)
                        except Exception:
                            text = ""
                    token = self._extract_candidate_secret(text)
                    if token:
                        candidates.append(token)
            except Exception:
                continue

        if not candidates:
            return {"ok": False, "error": "OpenRouter-Token konnte nicht extrahiert werden", "current_url": page.url}

        token = max(candidates, key=len)
        get_secrets_store().set_secret(secret_ref, token, kind="browser_import")
        if secret_ref == "OPENROUTER_API_KEY":
            self.cfg.providers["openrouter"].api_key = token
        return {
            "ok": True,
            "secret_ref": secret_ref,
            "current_url": page.url,
            "token_preview": token[:6] + "..." + token[-4:],
        }

    # ── Broadcast ─────────────────────────────────────────────────────────────
    async def broadcast(self, prompt: str,
                        instance_ids: Optional[list] = None,
                        stagger_ms: int = 1500) -> dict[str, str]:
        """
        Sendet einen Prompt an mehrere Instanzen.
        Mit konfigurierbarer Latenz zwischen Anfragen (kein Ban-Risiko).
        """
        ids = instance_ids or [
            i.id for i in self._instances.values() if i.aktiv
        ]

        ergebnisse = {}
        tasks      = []

        for i, iid in enumerate(ids):
            # Stagger: jede Anfrage mit Verzögerung starten
            delay = (i * stagger_ms) / 1000.0
            tasks.append(self._delayed_ask(iid, prompt, delay))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for iid, result in zip(ids, results):
            if isinstance(result, Exception):
                ergebnisse[iid] = f"[Fehler: {result}]"
            else:
                ergebnisse[iid] = result

        return ergebnisse

    async def _delayed_ask(self, iid: str, prompt: str,
                           delay: float) -> str:
        await asyncio.sleep(delay)
        return await self.ask_instance(iid, prompt)

    # ── Instanz neustarten ────────────────────────────────────────────────────
    async def _restart_instance(self, inst: KIInstance):
        log.warning(f"Neustart: {inst.id}")
        try:
            if inst.context:
                await inst.context.close()
            inst.fehler  = 0
            inst.aktiv   = False
            inst.context = await self._browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            inst.page = await inst.context.new_page()
            await inst.page.goto(inst.url, wait_until="networkidle",
                                 timeout=30000)
            inst.aktiv = True
            await self._auto_login(inst)
            AuditLog.instance(inst.id, "restarted")
        except Exception as e:
            log.error(f"Neustart {inst.id} fehlgeschlagen: {e}")

    # ── Credentials verwalten ─────────────────────────────────────────────────
    def add_credential(self, domain: str, login_url: str,
                       username: str, password: str,
                       logged_in_check: str = "") -> bool:
        """Fügt Login-Daten für eine Domain hinzu."""
        self._creds[domain] = LoginProfile(
            domain          = domain,
            login_url       = login_url,
            username        = username,
            password        = password,
            logged_in_check = logged_in_check,
        )
        self._save_creds()
        log.info(f"Credentials gespeichert: {domain}")
        return True

    def remove_credential(self, domain: str):
        self._creds.pop(domain, None)
        self._save_creds()

    def _load_creds(self):
        if not CREDS_PATH.exists():
            return
        try:
            data = json.loads(CREDS_PATH.read_text())
            for domain, d in data.items():
                self._creds[domain] = LoginProfile(**d)
            log.info(f"Credentials geladen: {len(self._creds)} Domains")
        except Exception as e:
            log.warning(f"Credentials laden: {e}")

    def _save_creds(self):
        try:
            CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {k: asdict(v) for k, v in self._creds.items()}
            CREDS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            # Nur Owner-Zugriff
            import stat
            CREDS_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception as e:
            log.warning(f"Credentials speichern: {e}")

    # ── Status ────────────────────────────────────────────────────────────────
    def add_url(self, url_config: dict):
        """Fügt eine neue URL-Konfiguration hinzu (dynamisch)."""
        # Wird beim nächsten start() oder manuell initiiert
        self._pending_urls = getattr(self, "_pending_urls", [])
        self._pending_urls.append(url_config)

    def site_catalog(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for domain, meta in SITE_CATALOG_META.items():
            existing = next((inst for inst in self._instances.values() if domain in inst.url), None)
            rows.append({
                "site_id": meta["site_id"],
                "label": meta["label"],
                "domain": domain,
                "url": meta["url"],
                "active": bool(existing and existing.aktiv),
                "logged_in": bool(existing and existing.eingeloggt),
                "instance_id": existing.id if existing else "",
            })
        return rows

    async def activate_catalog_site(self, site_id: str) -> dict[str, Any]:
        target = next((meta | {"domain": domain} for domain, meta in SITE_CATALOG_META.items() if meta["site_id"] == site_id), None)
        if not target:
            raise KeyError(f"Unbekannte Browser-Site: {site_id}")
        inst = await self.ensure_instance(target["site_id"], target["url"], name=target["label"])
        return {
            "ok": True,
            "site_id": target["site_id"],
            "instance": inst.to_dict(),
        }

    def list_instances(self) -> list[dict]:
        return [i.to_dict() for i in self._instances.values()]

    def get_active_ids(self) -> list[str]:
        return [i.id for i in self._instances.values() if i.aktiv]

    def stats(self) -> dict:
        inst = list(self._instances.values())
        return {
            "total":     len(inst),
            "aktiv":     sum(1 for i in inst if i.aktiv),
            "eingeloggt": sum(1 for i in inst if i.eingeloggt),
            "bereit":    self._bereit,
            "creds":     len(self._creds),
        }

    async def close(self):
        for inst in self._instances.values():
            try:
                if inst.context:
                    await inst.context.close()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        log.info("BrowserManager geschlossen")


# ── Singleton ─────────────────────────────────────────────────────────────────
_browser_mgr: Optional[BrowserManager] = None

def get_browser() -> BrowserManager:
    global _browser_mgr
    if _browser_mgr is None:
        _browser_mgr = BrowserManager()
    return _browser_mgr
