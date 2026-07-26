from __future__ import annotations

"""NOW snapshot for Dashboard v6 — what Isaac is doing right now.

Fail-open, no secrets. Additive telemetry only (no routing changes).
"""

import logging
import time
from typing import Any, Optional

log = logging.getLogger("Isaac.MonitorNow")

PIPELINE_ORDER = (
    "input",
    "classification",
    "retrieval",
    "strategy",
    "task",
    "execution",
    "evaluation",
    "memory",
)

_PHASE_FROM_TRACE = {
    "classification": "classification",
    "retrieval": "retrieval",
    "strategy": "strategy",
    "motivation": "strategy",
    "eligibility": "strategy",
    "selection": "task",
    "execution": "execution",
    "context_integration": "execution",
    "evaluation": "evaluation",
    "learning": "memory",
    "followup": "evaluation",
    "governance": "classification",
}

# In-memory override from optional kernel hooks
_override: dict[str, Any] = {}
_override_ts: float = 0.0


def set_now_phase(
    phase: str,
    *,
    headline: str = "",
    subline: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Optional kernel hook — fail-open callers wrap in try/except."""
    global _override, _override_ts
    ph = (phase or "idle").strip().lower()
    if ph not in PIPELINE_ORDER and ph != "idle":
        ph = "execution"
    _override = {
        "pipeline_phase": ph,
        "headline": (headline or "")[:200],
        "subline": (subline or "")[:200],
        "extra": dict(extra or {}),
        "ts": time.time(),
    }
    _override_ts = _override["ts"]


def clear_now_override() -> None:
    global _override, _override_ts
    _override = {}
    _override_ts = 0.0


def _phase_status_map(active: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if active == "idle" or not active:
        for p in PIPELINE_ORDER:
            out[p] = {"status": "idle", "ms": None}
        return out
    seen = False
    for p in PIPELINE_ORDER:
        if p == active:
            out[p] = {"status": "active", "ms": None}
            seen = True
        elif not seen:
            out[p] = {"status": "done", "ms": None}
        else:
            out[p] = {"status": "idle", "ms": None}
    return out


def _trace_phase(task: dict[str, Any]) -> str:
    trace = task.get("decision_trace") or []
    if not isinstance(trace, list) or not trace:
        st = str(task.get("status") or "").lower()
        if st in {"running", "evaluating", "followup"}:
            return "execution" if st == "running" else "evaluation"
        return "idle"
    last = trace[-1] if isinstance(trace[-1], dict) else {}
    raw = str(last.get("phase") or "").lower()
    return _PHASE_FROM_TRACE.get(raw, "execution")


def _safe_goals() -> dict[str, Any]:
    try:
        from goal_store import get_goal_store

        gs = get_goal_store()
        active = gs.list_goals(status="active")[:8]
        rows = [
            {
                "id": g.id,
                "title": (g.title or "")[:80],
                "priority": g.priority,
                "status": g.status,
            }
            for g in active
        ]
        next_mot = None
        try:
            from motivation import pick_motivation_decision

            dec = pick_motivation_decision()
            if dec:
                next_mot = {
                    "goal_id": dec.goal_id,
                    "goal_title": (dec.goal_title or "")[:60],
                    "subgoal_title": (dec.subgoal_title or "")[:60],
                    "score": dec.score,
                }
        except Exception:
            pass
        return {"active": rows, "next_motivation": next_mot, "count": len(rows)}
    except Exception as exc:
        log.debug("goals snapshot: %s", exc)
        return {"active": [], "next_motivation": None, "count": 0}


def _safe_missions() -> dict[str, Any]:
    try:
        from execution_contract import get_mission_store

        store = get_mission_store()
        active = store.list_active()[:10]
        rows = [
            {
                "id": m.id,
                "title": (m.title or "")[:80],
                "kind": m.kind,
                "status": m.status,
                "steps_done": m.steps_done,
                "target_url": (m.target_url or "")[:120],
                "goal_id": m.goal_id,
            }
            for m in active
        ]
        return {"active": rows, "count": len(rows)}
    except Exception as exc:
        log.debug("missions snapshot: %s", exc)
        return {"active": [], "count": 0}


def _safe_smoke() -> dict[str, Any]:
    try:
        from remote_smoke import status as smoke_status

        st = smoke_status()
        return {
            "enabled": st.get("enabled"),
            "wake_interval_s": st.get("wake_interval_s"),
            "last_ok": st.get("last_ok"),
            "last_commit": st.get("last_commit"),
            "wake_count": st.get("wake_count"),
            "full_count": st.get("full_count"),
            "wake_under_sleep": st.get("wake_under_sleep"),
        }
    except Exception:
        return {}


def _running_task(executor) -> Optional[dict[str, Any]]:
    try:
        running = executor.running_tasks() if hasattr(executor, "running_tasks") else []
        if isinstance(running, list) and running:
            t = running[0]
            return t if isinstance(t, dict) else None
        # fallback: scan all_tasks
        for t in executor.all_tasks(30) or []:
            if str(t.get("status") or "").lower() in {
                "running",
                "evaluating",
                "followup",
            }:
                return t
    except Exception:
        pass
    return None


def build_now_snapshot(
    *,
    executor=None,
    gate=None,
    provider: str = "",
    background: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble NOW payload for monitor state."""
    try:
        if executor is None:
            from executor import get_executor

            executor = get_executor()
    except Exception:
        executor = None

    task = _running_task(executor) if executor else None
    phase = "idle"
    headline = "Isaac wartet auf Steffen"
    subline = "Bereit"
    intent = ""
    interaction = ""
    strategy: dict[str, Any] = {}
    task_id = None
    task_type = None
    task_status = None
    last_tool = None

    # Fresh override wins for ~90s
    if _override and (time.time() - _override_ts) < 90:
        phase = _override.get("pipeline_phase") or "idle"
        if _override.get("headline"):
            headline = _override["headline"]
        if _override.get("subline"):
            subline = _override["subline"]

    if task:
        task_id = task.get("id")
        task_type = task.get("typ") or task.get("type")
        task_status = task.get("status")
        intent = str(
            (task.get("classification") or {}).get("intent")
            if isinstance(task.get("classification"), dict)
            else task.get("intent") or ""
        )
        if isinstance(task.get("classification"), dict):
            interaction = str(
                task["classification"].get("interaction_class")
                or task["classification"].get("class")
                or ""
            )
        strat = task.get("strategy") if isinstance(task.get("strategy"), dict) else {}
        strategy = {
            "allow_tools": bool(strat.get("allow_tools")),
            "allow_followup": bool(strat.get("allow_followup", True)),
            "allow_provider_switch": bool(strat.get("allow_provider_switch", True)),
            "style_note": str(strat.get("style_note") or "")[:80],
        }
        if phase == "idle" or not _override:
            phase = _trace_phase(task)
        desc = str(task.get("beschreibung") or task.get("prompt") or "")[:100]
        st = str(task_status or "").lower()
        headline = f"Task {task_id}: {desc}" if desc else f"Task {task_id} ({st})"
        subline = (
            f"{task_type or '—'} · {st} · tools="
            f"{'on' if strategy.get('allow_tools') else 'off'}"
        )
        # last tool from tool_strategy if present
        ts = task.get("tool_strategy") if isinstance(task.get("tool_strategy"), dict) else {}
        if ts.get("last_tool") or ts.get("tool_name"):
            last_tool = {
                "name": str(ts.get("last_tool") or ts.get("tool_name") or "")[:60],
                "ok": ts.get("last_ok"),
                "ms": ts.get("last_ms"),
            }

    paused = False
    try:
        if gate is None:
            from privilege import get_gate

            gate = get_gate()
        paused = bool(getattr(gate, "is_paused", False))
    except Exception:
        pass
    if paused:
        headline = "Pausiert — warte auf Owner"
        subline = "Pause aktiv"
        phase = "idle"

    goals = _safe_goals()
    missions = _safe_missions()
    goal_id = None
    mission_id = None
    if goals.get("next_motivation"):
        goal_id = goals["next_motivation"].get("goal_id")
    if missions.get("active"):
        mission_id = missions["active"][0].get("id")
        if phase == "idle" and not task:
            headline = f"Mission bereit: {missions['active'][0].get('title', '')}"
            subline = f"kind={missions['active'][0].get('kind')}"

    bg = dict(background or {})
    try:
        smoke = _safe_smoke()
        if smoke:
            bg["remote_smoke"] = smoke
    except Exception:
        pass

    if not provider:
        try:
            from config import get_config

            provider = str(
                getattr(getattr(get_config(), "relay", None), "primary_provider", "")
                or ""
            )
        except Exception:
            provider = ""

    return {
        "headline": headline[:200],
        "subline": subline[:200],
        "pipeline_phase": phase if phase in PIPELINE_ORDER or phase == "idle" else "idle",
        "phases": _phase_status_map(phase if phase != "idle" else ""),
        "intent": intent[:40],
        "interaction_class": interaction[:40],
        "strategy": strategy,
        "active_task_id": task_id,
        "active_task_type": task_type,
        "active_task_status": task_status,
        "provider": provider[:40],
        "model_hint": None,
        "goal_id": goal_id,
        "mission_id": mission_id,
        "constitution": {"blocked": False, "reason": ""},
        "last_tool": last_tool,
        "background": bg,
        "goals_count": goals.get("count", 0),
        "missions_count": missions.get("count", 0),
        "updated_ts": time.time(),
        "paused": paused,
    }


def build_goals_missions_extras() -> dict[str, Any]:
    return {
        "goals": _safe_goals(),
        "missions": _safe_missions(),
        "remote_smoke": _safe_smoke(),
    }
