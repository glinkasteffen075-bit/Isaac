"""Isaac – Owner-Action Routing (nur ISAAC_PRIVILEGE_MODE=admin)

Erkennt imperative Owner-Befehle in natürlicher Sprache und führt sie
über vorhandene Ausführungspfade aus (Shell, Browser, Dateien, Suche).
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

from audit import AuditLog
from config import WORKSPACE, get_config, is_owner_equivalent_mode

log = logging.getLogger("Isaac.OwnerAction")

_EXPLANATORY_PREFIXES = (
    "erkläre ",
    "erklaere ",
    "erklär ",
    "erklaer ",
    "was ist ",
    "was bedeutet ",
    "wie funktioniert ",
    "warum ",
    "beschreibe ",
    "vergleiche ",
    "diskutiere ",
)

_ACTION_VERBS = (
    "suche",
    "such",
    "finde",
    "find",
    "hol",
    "hole",
    "zeig",
    "zeige",
    "öffne",
    "oeffne",
    "navigiere",
    "verbinde",
    "verbind",
    "räum",
    "raeum",
    "aufräum",
    "aufraeum",
    "bereinige",
    "lösch",
    "loesch",
    "verschiebe",
    "kopiere",
    "installiere",
    "starte",
    "führe aus",
    "fuehre aus",
    "stell ein",
    "setz",
    "mach",
)

_PHOTOS_MARKERS = ("google fotos", "google photos", "photos.google", "fotos app")
_WLAN_MARKERS = ("wlan", "wifi", "router", "netzwerk", "hotspot")
_CLEANUP_MARKERS = (
    "dateisystem",
    "dateien aufräumen",
    "dateien aufraeumen",
    "dateien aufräumen",
    "festplatte aufräumen",
    "speicher aufräumen",
    "ordner aufräumen",
    "aufräumen",
    "aufraeumen",
    "aufräum",
    "aufraeum",
    "bereinige",
    "cleanup",
)
_WEB_SEARCH_MARKERS = ("google", "im web", "internet", "online")


@dataclass(frozen=True)
class OwnerAction:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


def _normalize(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"^isaac[,:]?\s+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _is_explanatory(normalized: str) -> bool:
    return any(normalized.startswith(p) for p in _EXPLANATORY_PREFIXES)


def _has_action_verb(normalized: str) -> bool:
    first = normalized.split()[0] if normalized.split() else normalized
    return any(
        normalized == v
        or normalized.startswith(v + " ")
        or first.startswith(v)
        or f" {v} " in f" {normalized} "
        for v in _ACTION_VERBS
    )


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def _extract_query_after_tokens(text: str, tokens: tuple[str, ...]) -> str:
    lower = text.lower()
    for token in tokens:
        idx = lower.find(token)
        if idx >= 0:
            return text[idx + len(token):].strip(" :.,!?")
    return ""


def _extract_photos_query(text: str) -> str:
    patterns = (
        r"(?:über|ueber|nach|mit|von|für|fuer|about)\s+(.+)$",
        r"(?:raus|heraus)?\s*(?:über|ueber|nach|mit|von|für|fuer)\s+(.+)$",
        r"google\s+fotos\s+(.+)$",
        r"google\s+photos\s+(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            q = m.group(1).strip(" .,!?:")
            q = re.sub(r"^(raus|heraus)\s+", "", q, flags=re.I)
            if q:
                return q
    tail = _extract_query_after_tokens(text, ("google fotos", "google photos", "fotos"))
    return tail.strip(" .,!?:") if tail else ""


def _extract_web_query(text: str) -> str:
    patterns = (
        r"(?:suche|such|finde)\s+(?:mir\s+)?(?:bei\s+)?google\s+(?:nach\s+)?(.+)$",
        r"(?:suche|such|finde)\s+(?:mir\s+)?(?:im\s+)?(?:web|internet|online)\s+(?:nach\s+)?(.+)$",
        r"(?:suche|such|finde)\s+(?:mir\s+)?(.+)$",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            q = m.group(1).strip(" .,!?:")
            if q and not _contains_any(q, _PHOTOS_MARKERS + _WLAN_MARKERS + _CLEANUP_MARKERS):
                return q
    return ""


def detect_owner_action(text: str) -> Optional[OwnerAction]:
    """Imperative Owner-Befehle erkennen (Aufrufer prüft admin-Modus separat)."""
    raw = (text or "").strip()
    if not raw:
        return None

    normalized = _normalize(raw)
    if not normalized or _is_explanatory(normalized):
        return None
    if not _has_action_verb(normalized):
        return None

    if _contains_any(normalized, _PHOTOS_MARKERS):
        query = _extract_photos_query(raw)
        if query:
            return OwnerAction("photos_search", {"query": query}, raw=raw)

    if _contains_any(normalized, _WLAN_MARKERS):
        if any(t in normalized for t in ("verbind", "connect", "einlogg", "anmelden", "join")):
            return OwnerAction("wlan_connect", {}, raw=raw)
        if any(t in normalized for t in ("einstellung", "settings", "öffne", "oeffne")):
            return OwnerAction("wlan_open_settings", {}, raw=raw)
        return OwnerAction("wlan_status", {}, raw=raw)

    if (
        any(t in normalized for t in ("räum", "raeum", "aufräum", "aufraeum", "bereinige", "cleanup"))
        and any(t in normalized for t in ("datei", "dateisystem", "ordner", "speicher", "festplatte", "system"))
    ) or normalized.endswith(("aufräumen", "aufraeumen", "aufräum", "aufraeum")):
        scope = "home"
        if any(t in normalized for t in ("alles", "gesamt", "komplett", "ganzes system")):
            scope = "home"
        return OwnerAction("filesystem_cleanup", {"scope": scope}, raw=raw)

    if _contains_any(normalized, _WEB_SEARCH_MARKERS) or normalized.startswith(("suche ", "such ", "finde ")):
        query = _extract_web_query(raw)
        if query:
            return OwnerAction("web_search", {"query": query}, raw=raw)

    if normalized.startswith(("öffne ", "oeffne ", "navigiere ")):
        target = re.sub(r"^(öffne|oeffne|navigiere)\s+(zu\s+)?", "", raw, flags=re.I).strip()
        if target:
            return OwnerAction("open_target", {"target": target}, raw=raw)

    return None


async def execute_owner_action(action: OwnerAction) -> tuple[str, bool]:
    handlers = {
        "photos_search": _photos_search,
        "web_search": _web_search,
        "wlan_status": _wlan_status,
        "wlan_open_settings": _wlan_open_settings,
        "wlan_connect": _wlan_connect,
        "filesystem_cleanup": _filesystem_cleanup,
        "open_target": _open_target,
    }
    handler = handlers.get(action.kind)
    if not handler:
        return f"[Owner] Unbekannte Aktion: {action.kind}", False
    try:
        return await handler(action)
    except Exception as exc:
        log.warning("Owner action %s failed: %s", action.kind, exc)
        return f"[Owner] Fehler bei {action.kind}: {exc}", False


async def _photos_search(action: OwnerAction) -> tuple[str, bool]:
    query = str(action.params.get("query") or "").strip()
    if not query:
        return "[Owner] Kein Suchbegriff für Google Fotos erkannt.", False
    url = f"https://photos.google.com/search/{quote_plus(query)}"
    AuditLog.action("OwnerAction", "photos_search", f"query={query[:120]}")
    opened = await _open_url(url)
    return (
        f"[Owner] Google Fotos-Suche gestartet.\n"
        f"Suchbegriff: {query}\n"
        f"URL: {url}\n"
        f"{opened}"
    ), True


async def _web_search(action: OwnerAction) -> tuple[str, bool]:
    query = str(action.params.get("query") or "").strip()
    if not query:
        return "[Owner] Kein Suchbegriff erkannt.", False
    AuditLog.action("OwnerAction", "web_search", f"query={query[:120]}")
    try:
        from search import get_search

        result = await get_search().search(query, max_hits=5)
        if result and result.hits:
            lines = [f"[Owner] Websuche: {query}", ""]
            for hit in result.hits[:5]:
                lines.append(f"- {hit.titel}\n  {hit.url}")
            return "\n".join(lines), True
    except Exception as exc:
        log.debug("Search fallback: %s", exc)
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    opened = await _open_url(url)
    return f"[Owner] Google-Suche geöffnet.\nQuery: {query}\nURL: {url}\n{opened}", True


async def _wlan_status(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "wlan_status", action.raw[:120])
    from computer_use import ComputerUseRuntime, AgentAction

    runtime = ComputerUseRuntime()
    cmds = []
    if runtime.runtime == "termux":
        cmds = ["termux-wifi-connectioninfo", "termux-wifi-signal"]
    else:
        cmds = ["nmcli -t -f ACTIVE,SSID,SIGNAL,SECURITY dev wifi 2>/dev/null || iwconfig 2>/dev/null | head -20"]
    lines = ["[Owner] WLAN-Status", ""]
    for cmd in cmds:
        result = await runtime.execute(AgentAction("shell", {"command": cmd}))
        if result.get("stdout"):
            lines.append(result["stdout"][:2000])
        elif result.get("error"):
            lines.append(f"({cmd}): {result['error']}")
    return "\n".join(lines), True


async def _wlan_open_settings(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "wlan_open_settings", action.raw[:120])
    from computer_use import ComputerUseRuntime, AgentAction

    runtime = ComputerUseRuntime()
    if runtime.runtime == "termux":
        cmd = "am start -a android.settings.WIFI_SETTINGS"
    else:
        cmd = "nm-connection-editor >/dev/null 2>&1 & disown || nmtui"
    result = await runtime.execute(AgentAction("shell", {"command": cmd}))
    if result.get("ok"):
        return "[Owner] WLAN-Einstellungen geöffnet.", True
    return f"[Owner] WLAN-Einstellungen konnten nicht geöffnet werden: {result.get('error', 'unbekannt')}", False


async def _wlan_connect(action: OwnerAction) -> tuple[str, bool]:
    AuditLog.action("OwnerAction", "wlan_connect", action.raw[:120])
    opened = await _wlan_open_settings(action)
    msg = (
        "[Owner] Automatisches WLAN-Join ist auf Android/Linux oft eingeschränkt.\n"
        "Isaac hat die WLAN-Einstellungen geöffnet — bitte Netzwerk dort auswählen.\n"
        "Alternativ: shell termux-wifi-scanlist (Termux:API nötig)."
    )
    return msg if opened[1] else opened[0] + "\n" + msg, opened[1]


async def _filesystem_cleanup(action: OwnerAction) -> tuple[str, bool]:
    scope = str(action.params.get("scope") or "home")
    roots = [Path.home()]
    if scope != "home":
        roots.append(WORKSPACE.resolve())

    patterns = ("**/__pycache__", "**/*.pyc", "**/*.pyo", "**/*.tmp", "**/*~", "**/.DS_Store")
    removed_dirs: list[str] = []
    removed_files: list[str] = []
    freed = 0

    for root in roots:
        if not root.exists():
            continue
        for pattern in patterns:
            for path in root.glob(pattern):
                try:
                    if path.is_dir():
                        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                        shutil.rmtree(path)
                        removed_dirs.append(str(path))
                        freed += size
                    elif path.is_file():
                        size = path.stat().st_size
                        path.unlink()
                        removed_files.append(str(path))
                        freed += size
                except Exception as exc:
                    log.debug("Cleanup skip %s: %s", path, exc)

    AuditLog.action(
        "OwnerAction",
        "filesystem_cleanup",
        f"dirs={len(removed_dirs)} files={len(removed_files)} freed={freed}",
    )
    lines = [
        "[Owner] Dateisystem-Aufräumen abgeschlossen.",
        f"Bereich: {', '.join(str(r) for r in roots)}",
        f"Ordner entfernt: {len(removed_dirs)}",
        f"Dateien entfernt: {len(removed_files)}",
        f"Freigegeben: {freed // 1024} KB",
    ]
    if removed_dirs[:8]:
        lines.append("")
        lines.append("Beispiele (Ordner):")
        lines.extend(f"- {p}" for p in removed_dirs[:8])
    if removed_files[:8]:
        lines.append("")
        lines.append("Beispiele (Dateien):")
        lines.extend(f"- {p}" for p in removed_files[:8])
    return "\n".join(lines), True


async def _open_target(action: OwnerAction) -> tuple[str, bool]:
    target = str(action.params.get("target") or "").strip()
    if not target:
        return "[Owner] Kein Ziel angegeben.", False
    if not re.match(r"^https?://", target, re.I):
        if "." in target and " " not in target:
            target = f"https://{target}"
        else:
            target = f"https://www.google.com/search?q={quote_plus(target)}"
    AuditLog.action("OwnerAction", "open_target", target[:160])
    opened = await _open_url(target)
    return f"[Owner] Geöffnet: {target}\n{opened}", True


async def _open_url(url: str) -> str:
    from computer_use import ComputerUseRuntime, AgentAction, computer_use_enabled

    if computer_use_enabled():
        runtime = ComputerUseRuntime()
        result = await runtime.execute(AgentAction("open", {"target": url}))
        if result.get("ok"):
            return "Geöffnet über Computer-Use."
        return f"Hinweis Computer-Use: {result.get('error', 'unbekannt')}"

    if get_config().browser_automation:
        try:
            from browser import get_browser

            result = await get_browser().run_flow(
                "owner-action",
                url,
                [{"action": "goto", "url": url}],
                name="Owner Action",
            )
            if result.get("ok"):
                return "Geöffnet über Browser-Automation."
            return f"Hinweis Browser: {result.get('error', 'unbekannt')}"
        except Exception as exc:
            return f"Browser nicht verfügbar: {exc}"
    return "Weder Computer-Use noch Browser aktiv — URL oben manuell öffnen."


def owner_action_enabled() -> bool:
    return is_owner_equivalent_mode()