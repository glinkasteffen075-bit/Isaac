from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TracePhase(Enum):
    ELIGIBILITY = "eligibility"
    SELECTION = "selection"
    EXECUTION = "execution"
    CONTEXT_INTEGRATION = "context_integration"
    FOLLOWUP = "followup"


@dataclass(frozen=True)
class TraceEntry:
    sequence: int
    ts: float
    phase: TracePhase
    event: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "ts": self.ts,
            "phase": self.phase.value,
            "event": self.event,
            "data": self.data,
        }


@dataclass
class DecisionTrace:
    entries: list[TraceEntry] = field(default_factory=list)

    def add(self, phase: TracePhase, event: str, data: dict[str, Any] | None = None) -> TraceEntry:
        payload = dict(data or {})
        entry = TraceEntry(
            sequence=len(self.entries) + 1,
            ts=time.time(),
            phase=phase,
            event=event,
            data=payload,
        )
        self.entries.append(entry)
        return entry

    def to_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]
