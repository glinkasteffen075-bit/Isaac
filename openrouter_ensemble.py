from __future__ import annotations

"""Isaac – OpenRouter Multi-Model Ensemble

Ein API-Key, mehrere Modelle: Fan-out → Quality-Score → Winner oder Judge-Synthese.
Fokus Free-Modelle (`:free`), konfigurierbar per Env.
"""

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from audit import AuditLog
from logic import get_logic

log = logging.getLogger("Isaac.OpenRouterEnsemble")

# Start-Panel — Verfügbarkeit kann sich ändern; Free-Suffix ist Konvention.
DEFAULT_FREE_MODELS: tuple[str, ...] = (
    "meta-llama/llama-3.2-3b-instruct:free",
    "google/gemma-2-9b-it:free",
    "qwen/qwen-2.5-7b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
)

DEFAULT_JUDGE_MODEL = "meta-llama/llama-3.2-3b-instruct:free"


@dataclass
class ModelAnswer:
    model: str
    antwort: str
    score: float = 0.0
    latenz_s: float = 0.0
    fehler: bool = False
    error: str = ""


@dataclass
class EnsembleResult:
    final: str
    mode: str  # winner | judge | single | empty
    winner_model: str = ""
    ergebnisse: list[ModelAnswer] = field(default_factory=list)
    dauer_s: float = 0.0
    judge_model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary_line(self) -> str:
        ok = [e for e in self.ergebnisse if not e.fehler]
        return (
            f"Ensemble: mode={self.mode} winner={self.winner_model or '-'} "
            f"models={len(ok)}/{len(self.ergebnisse)} t={self.dauer_s:.1f}s"
        )


def _env_bool(name: str, default: str = "1") -> bool:
    raw = str(os.getenv(name, default) or default).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def ensemble_enabled() -> bool:
    return _env_bool("ISAAC_ENSEMBLE", "1")


def ensemble_free_only() -> bool:
    return _env_bool("ISAAC_ENSEMBLE_FREE_ONLY", "1")


def ensemble_auto_enabled() -> bool:
    """Always-on Ensemble nur für schwere CHAT-Fragen (nicht Tools/Greeting)."""
    return ensemble_enabled() and _env_bool("ISAAC_ENSEMBLE_AUTO", "1")


def ensemble_n() -> int:
    try:
        return max(1, min(6, int(os.getenv("ISAAC_ENSEMBLE_N", "3"))))
    except (TypeError, ValueError):
        return 3


def ensemble_stagger_ms() -> int:
    try:
        return max(0, min(5000, int(os.getenv("ISAAC_ENSEMBLE_STAGGER_MS", "800"))))
    except (TypeError, ValueError):
        return 800


def ensemble_judge_enabled() -> bool:
    return _env_bool("ISAAC_ENSEMBLE_JUDGE", "1")


def ensemble_score_delta() -> float:
    try:
        return max(0.0, float(os.getenv("ISAAC_ENSEMBLE_SCORE_DELTA", "1.0")))
    except (TypeError, ValueError):
        return 1.0


def ensemble_auto_min_words() -> int:
    """Wort-Schwelle für Auto-Ensemble (strenger als Decomposer-Default 15)."""
    try:
        return max(8, min(80, int(os.getenv("ISAAC_ENSEMBLE_AUTO_MIN_WORDS", "22"))))
    except (TypeError, ValueError):
        return 22


def ensemble_auto_min_themes() -> int:
    try:
        return max(2, min(6, int(os.getenv("ISAAC_ENSEMBLE_AUTO_MIN_THEMES", "2"))))
    except (TypeError, ValueError):
        return 2


def should_auto_ensemble(
    text: str,
    *,
    intent: str = "chat",
    interaction_class: str = "NORMAL_CHAT",
) -> tuple[bool, str]:
    """
    Entscheidet, ob ein normaler Chat ohne Prefix ins Ensemble geht.

    Nur CHAT + NORMAL_CHAT. Keine Tools, keine Short-Paths, keine Status-Queries.
    Schwer = lange Frage ODER multi-thematisch (und/sowie/…).
    """
    if not ensemble_auto_enabled():
        return False, "auto_disabled"
    intent_l = (intent or "").strip().lower()
    if intent_l not in {"chat", ""}:
        return False, f"intent={intent_l or 'empty'}"
    ic = (interaction_class or "").strip().upper()
    if ic and ic != "NORMAL_CHAT":
        return False, f"class={ic or 'empty'}"

    body = (text or "").strip()
    if not body:
        return False, "empty"
    # Explizite Prefix-Kommandos nie als Auto werten
    lower = body.lower()
    for prefix in (
        "ensemble:", "vergleiche:", "vergleiche modelle:",
        "multi-model:", "multimodel:", "broadcast:", "split:", "pipeline:",
        "suche:", "search:", "recherche:", "browser:", "agent:", "code:",
    ):
        if lower.startswith(prefix):
            return False, "explicit_prefix"

    words = body.split()
    word_count = len(words)
    theme_count = len(
        re.findall(r"\s+(?:und|sowie|außerdem|auch|bzw\.?|beziehungsweise)\s+", body, re.I)
    )
    min_words = ensemble_auto_min_words()
    min_themes = ensemble_auto_min_themes()

    if word_count >= min_words:
        return True, f"heavy_words={word_count}>={min_words}"
    if theme_count >= min_themes and word_count >= max(12, min_words // 2):
        return True, f"multi_theme={theme_count} words={word_count}"
    return False, f"light_words={word_count}<{min_words}"


def get_ensemble_models(*, free_only: Optional[bool] = None, limit: Optional[int] = None) -> list[str]:
    """Lädt Modell-Panel aus Env oder Defaults."""
    raw = (os.getenv("OPENROUTER_ENSEMBLE_MODELS") or "").strip()
    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
    else:
        models = list(DEFAULT_FREE_MODELS)
    fo = ensemble_free_only() if free_only is None else bool(free_only)
    if fo:
        models = [m for m in models if m.endswith(":free") or ":free" in m]
    if not models:
        models = list(DEFAULT_FREE_MODELS)
    n = ensemble_n() if limit is None else max(1, int(limit))
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for m in models:
        if m not in seen:
            seen.add(m)
            out.append(m)
        if len(out) >= n:
            break
    return out


def get_judge_model() -> str:
    return (os.getenv("OPENROUTER_ENSEMBLE_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL).strip()


async def _ask_model(
    relay: Any,
    *,
    prompt: str,
    system: str,
    model: str,
    task_id: str,
) -> ModelAnswer:
    t0 = time.monotonic()
    try:
        text = await relay.ask(
            prompt,
            system=system,
            provider="openrouter",
            task_id=task_id,
            model_override=model,
            use_cache=False,
        )
        lat = round(time.monotonic() - t0, 2)
        if (text or "").startswith("[RELAY"):
            return ModelAnswer(model=model, antwort=text or "", latenz_s=lat, fehler=True, error=text[:160])
        score = float(get_logic().evaluate(text or "", prompt).total)
        return ModelAnswer(model=model, antwort=text or "", score=score, latenz_s=lat, fehler=False)
    except Exception as exc:
        lat = round(time.monotonic() - t0, 2)
        return ModelAnswer(model=model, antwort="", latenz_s=lat, fehler=True, error=str(exc)[:160])


async def _judge_combine(
    relay: Any,
    *,
    prompt: str,
    candidates: list[ModelAnswer],
    judge_model: str,
    task_id: str,
) -> str:
    blocks = []
    for i, c in enumerate(candidates, 1):
        blocks.append(
            f"### Kandidat {i} [{c.model}] (Score {c.score:.1f})\n{c.antwort[:2500]}"
        )
    judge_prompt = (
        "Du bist ein neutraler Synthesizer.\n"
        "Unten stehen Antworten mehrerer Modelle auf DIESELBE Nutzerfrage.\n"
        "Kombiniere die Stärken, entferne Widersprüche und Halluzinationen wenn möglich.\n"
        "Gib EINE klare, vollständige deutsche Antwort. Keine Meta-Diskussion über Modelle.\n\n"
        f"## Nutzerfrage\n{prompt}\n\n"
        f"## Kandidaten\n" + "\n\n".join(blocks)
    )
    text = await relay.ask(
        judge_prompt,
        system="Du kombinierst Multi-Model-Antworten präzise und ehrlich.",
        provider="openrouter",
        task_id=f"{task_id}-judge",
        model_override=judge_model,
        use_cache=False,
    )
    if (text or "").startswith("[RELAY"):
        # Fallback: best scored candidate
        best = max(candidates, key=lambda c: c.score)
        return best.antwort
    return text


async def ensemble_openrouter(
    prompt: str,
    *,
    system: str = "",
    models: Optional[list[str]] = None,
    task_id: str = "ensemble",
    free_only: Optional[bool] = None,
    use_judge: Optional[bool] = None,
) -> EnsembleResult:
    """Fan-out über OpenRouter-Modelle → Score → Winner oder Judge."""
    t0 = time.monotonic()
    panel = models or get_ensemble_models(free_only=free_only)
    if not panel:
        return EnsembleResult(final="[Ensemble] Keine Modelle konfiguriert.", mode="empty")

    from relay import get_relay

    relay = get_relay()
    stagger = ensemble_stagger_ms() / 1000.0
    results: list[ModelAnswer] = []

    async def _one(i: int, model: str) -> ModelAnswer:
        if stagger and i:
            await asyncio.sleep(stagger * i)
        return await _ask_model(
            relay,
            prompt=prompt,
            system=system or "Du bist Isaac. Antworte präzise und vollständig.",
            model=model,
            task_id=f"{task_id}-{i}",
        )

    # begrenzte Parallelität
    sem = asyncio.Semaphore(int(os.getenv("ISAAC_ENSEMBLE_MAX_CONCURRENT", "3")))

    async def _guarded(i: int, model: str) -> ModelAnswer:
        async with sem:
            return await _one(i, model)

    results = list(await asyncio.gather(*[_guarded(i, m) for i, m in enumerate(panel)]))
    ok = [r for r in results if not r.fehler and (r.antwort or "").strip()]
    dauer = round(time.monotonic() - t0, 2)

    if not ok:
        # letzter Fallback: default openrouter ohne override
        fallback = await relay.ask(
            prompt,
            system=system,
            provider="openrouter",
            task_id=f"{task_id}-fallback",
            use_cache=False,
        )
        return EnsembleResult(
            final=fallback,
            mode="single",
            winner_model="openrouter-default",
            ergebnisse=results,
            dauer_s=dauer,
            metadata={"fallback": True},
        )

    ok_sorted = sorted(ok, key=lambda r: r.score, reverse=True)
    best = ok_sorted[0]
    second = ok_sorted[1] if len(ok_sorted) > 1 else None
    do_judge = ensemble_judge_enabled() if use_judge is None else bool(use_judge)
    close = second is not None and abs(best.score - second.score) <= ensemble_score_delta()

    if do_judge and close and len(ok_sorted) >= 2:
        judge_model = get_judge_model()
        final = await _judge_combine(
            relay,
            prompt=prompt,
            candidates=ok_sorted[:3],
            judge_model=judge_model,
            task_id=task_id,
        )
        mode = "judge"
        winner = judge_model
    else:
        final = best.antwort
        mode = "winner"
        winner = best.model
        judge_model = ""

    AuditLog.action(
        "Ensemble",
        mode,
        f"winner={winner} n={len(ok)}/{len(results)} t={dauer}s",
        erfolg=True,
    )
    log.info(
        "Ensemble done mode=%s winner=%s scores=%s",
        mode,
        winner,
        [(r.model.split("/")[-1], round(r.score, 1)) for r in ok_sorted[:4]],
    )
    return EnsembleResult(
        final=final,
        mode=mode,
        winner_model=winner,
        ergebnisse=results,
        dauer_s=dauer,
        judge_model=judge_model if mode == "judge" else "",
        metadata={
            "panel": panel,
            "scores": {r.model: r.score for r in ok_sorted},
            "free_only": ensemble_free_only() if free_only is None else free_only,
        },
    )


def format_ensemble_footer(result: EnsembleResult) -> str:
    parts = [result.summary_line()]
    for r in result.ergebnisse:
        if r.fehler:
            parts.append(f"  · {r.model}: FAIL {r.error[:60]}")
        else:
            parts.append(f"  · {r.model}: score={r.score:.1f} t={r.latenz_s:.1f}s")
    return "\n".join(parts)


def ensemble_trace_payload(result: EnsembleResult, *, trigger: str = "explicit") -> dict[str, Any]:
    """Kompakte Trace-Daten für DecisionTrace / Dashboard."""
    scores = {
        r.model: round(r.score, 2)
        for r in result.ergebnisse
        if not r.fehler
    }
    fails = [r.model for r in result.ergebnisse if r.fehler]
    return {
        "trigger": trigger,
        "mode": result.mode,
        "winner_model": result.winner_model,
        "judge_model": result.judge_model or "",
        "panel": list(result.metadata.get("panel") or [r.model for r in result.ergebnisse]),
        "scores": scores,
        "failed": fails,
        "dauer_s": result.dauer_s,
        "n_ok": len(scores),
        "n_total": len(result.ergebnisse),
        "free_only": bool(result.metadata.get("free_only", ensemble_free_only())),
    }
