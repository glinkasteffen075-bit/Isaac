from __future__ import annotations

"""Isaac – Task Checkpoint States
Zustandsmaschine für Task-Checkpointing und Resume.
"""

from typing import Any


CHECKPOINT_MAX_PER_TASK = 25
CHECKPOINT_MAX_AGE_DAYS = 30
CHECKPOINT_GLOBAL_MAX = 5000
TERMINAL_CHECKPOINT_STATES = frozenset({
    "done",
    "failed",
    "learning_commit",
})


class CheckpointState:
    PLANNING = "planning"
    TOOL_PENDING = "tool_pending"
    EVALUATING = "evaluating"
    LEARNING_COMMIT = "learning_commit"
    DONE = "done"
    FAILED = "failed"

    # Legacy alias
    TOOL_RUNNING = "tool_running"

    ALL = frozenset({
        PLANNING,
        TOOL_PENDING,
        TOOL_RUNNING,
        EVALUATING,
        LEARNING_COMMIT,
        DONE,
        FAILED,
    })

    RESUMABLE = frozenset({
        PLANNING,
        TOOL_PENDING,
        TOOL_RUNNING,
        EVALUATING,
        LEARNING_COMMIT,
    })


def is_resumable_state(state_name: str) -> bool:
    return (state_name or "") in CheckpointState.RESUMABLE


def normalize_state(state_name: str) -> str:
    name = (state_name or "").strip()
    if name == CheckpointState.TOOL_RUNNING:
        return CheckpointState.TOOL_PENDING
    return name


def build_input_snapshot(task: Any, *, current_prompt: str = "") -> dict[str, Any]:
    return {
        "task_id": task.id,
        "typ": task.typ.value,
        "prompt": task.prompt,
        "current_prompt": current_prompt or task.prompt,
        "beschreibung": task.beschreibung,
        "provider": task.provider,
        "provider_used": task.provider_used,
        "iteration": task.iteration,
        "status": task.status.value,
        "sudo": task.sudo_aktiv,
        "used_tools": list(getattr(task, "used_tools", [])[-8:]),
        "interaction_class": getattr(task, "interaction_class", ""),
    }


def build_result_snapshot(
    *,
    antwort: str = "",
    provider: str = "",
    score_total: float | None = None,
    partial: bool | None = None,
    via: str = "",
    resume_reason: str = "",
) -> dict[str, Any]:
    preview = (antwort or "")[:400]
    return {
        "answer_preview": preview,
        "answer_full": antwort or "",
        "provider": provider,
        "score_total": score_total,
        "partial": partial,
        "via": via,
        "resume_reason": resume_reason,
    }