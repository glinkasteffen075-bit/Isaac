"""
Isaac – Neural Core
====================
Hirninspiriertes Modulnetz für die Kern-Pipeline.

Modelliert kognitive Verarbeitung als vernetzte Regionen mit gewichteten
Synapsen – analog zu neuronalen Schaltkreisen, ohne externes Deep Learning.
Gewichte werden über Hebbian-artige Verstärkung und die LearningEngine
angepasst.

Regionen entsprechen der Isaac-Kernpipeline:
  perception → retrieval → integration → strategy → execution → evaluation → consolidation
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR

log = logging.getLogger("Isaac.NeuralCore")

WEIGHTS_PATH = DATA_DIR / "neural_weights.json"


class NeuralRegion(str, Enum):
    PERCEPTION = "perception"
    RETRIEVAL = "retrieval"
    INTEGRATION = "integration"
    STRATEGY = "strategy"
    EXECUTION = "execution"
    EVALUATION = "evaluation"
    CONSOLIDATION = "consolidation"


PIPELINE_ORDER: tuple[NeuralRegion, ...] = (
    NeuralRegion.PERCEPTION,
    NeuralRegion.RETRIEVAL,
    NeuralRegion.INTEGRATION,
    NeuralRegion.STRATEGY,
    NeuralRegion.EXECUTION,
    NeuralRegion.EVALUATION,
    NeuralRegion.CONSOLIDATION,
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "perception:retrieval": 0.90,
    "retrieval:integration": 0.85,
    "integration:strategy": 0.80,
    "strategy:execution": 0.95,
    "execution:evaluation": 1.00,
    "evaluation:consolidation": 0.90,
    "evaluation:strategy": 0.30,
}


def _edge_key(source: NeuralRegion, target: NeuralRegion) -> str:
    return f"{source.value}:{target.value}"


@dataclass(frozen=True)
class NeuralSignal:
    region: NeuralRegion
    activation: float
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "region": self.region.value,
            "activation": round(self.activation, 4),
            "payload": self.payload,
        }


@dataclass
class PropagationTrace:
    signals: list[NeuralSignal] = field(default_factory=list)
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "signals": [signal.as_dict() for signal in self.signals],
        }


@dataclass
class StrategyModulation:
    allow_tools: Optional[bool] = None
    allow_followup: Optional[bool] = None
    allow_provider_switch: Optional[bool] = None
    neural_note: str = ""


class NeuralCortex:
    """7-Regionen-Kognitivgraph mit plastischen Synapsen."""

    def __init__(self):
        self._weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
        self._load_weights()
        log.info("NeuralCortex online │ Regionen=%d │ Synapsen=%d", len(PIPELINE_ORDER), len(self._weights))

    def _load(self) -> None:
        self._load_weights()

    def _load_weights(self) -> None:
        if not WEIGHTS_PATH.exists():
            return
        try:
            data = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in DEFAULT_WEIGHTS:
                        self._weights[key] = max(0.1, min(1.0, float(value)))
        except Exception as exc:
            log.debug("Neural weight load fehlgeschlagen: %s", exc)

    def _save_weights(self) -> None:
        try:
            WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            WEIGHTS_PATH.write_text(
                json.dumps(self._weights, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log.debug("Neural weight save fehlgeschlagen: %s", exc)

    def get_weight(self, source: NeuralRegion, target: NeuralRegion) -> float:
        return self._weights.get(_edge_key(source, target), 0.5)

    def _perception_activation(self, interaction_class: str, word_count: int) -> float:
        base = 0.55
        if interaction_class in ("NORMAL_CHAT", "TOOL_REQUEST"):
            base = 0.75
        elif interaction_class in ("SOCIAL_GREETING", "SOCIAL_ACKNOWLEDGMENT"):
            base = 0.35
        elif interaction_class in ("STATUS_QUERY", "SHORT_CLARIFICATION"):
            base = 0.45
        length_boost = min(0.2, word_count * 0.02)
        return min(1.0, base + length_boost)

    def _retrieval_activation(self, retrieval_ctx: dict[str, Any]) -> float:
        hits = (
            len(retrieval_ctx.get("relevant_facts", []))
            + len(retrieval_ctx.get("conversation_history", []))
            + len(retrieval_ctx.get("relevant_task_results", []))
            + len(retrieval_ctx.get("relevant_procedures", []))
        )
        semantic = 0.15 if (retrieval_ctx.get("semantic_context") or "").strip() else 0.0
        return min(1.0, 0.25 + hits * 0.08 + semantic)

    def _integration_activation(self, retrieval_ctx: dict[str, Any]) -> float:
        directives = len(retrieval_ctx.get("active_directives", []))
        risks = len(retrieval_ctx.get("behavioral_risks", []))
        return min(1.0, 0.35 + directives * 0.05 + risks * 0.1)

    def _strategy_activation(self, intent: str, interaction_class: str) -> float:
        if interaction_class == "TOOL_REQUEST":
            return 0.9
        if intent in ("search", "code", "file"):
            return 0.85
        if interaction_class in ("SHORT_CLARIFICATION", "SOCIAL_ACKNOWLEDGMENT"):
            return 0.3
        return 0.6

    def propagate(
        self,
        *,
        interaction_class: str,
        intent: str,
        retrieval_ctx: dict[str, Any],
        word_count: int = 0,
        execution_score: Optional[float] = None,
    ) -> PropagationTrace:
        """Vorwärtsdurchlauf durch die kognitiven Regionen."""
        trace = PropagationTrace()
        region_inputs = {
            NeuralRegion.PERCEPTION: self._perception_activation(interaction_class, word_count),
            NeuralRegion.RETRIEVAL: self._retrieval_activation(retrieval_ctx),
            NeuralRegion.INTEGRATION: self._integration_activation(retrieval_ctx),
            NeuralRegion.STRATEGY: self._strategy_activation(intent, interaction_class),
            NeuralRegion.EXECUTION: 0.7,
            NeuralRegion.EVALUATION: (execution_score or 5.0) / 10.0,
            NeuralRegion.CONSOLIDATION: 0.5,
        }

        prev_region: Optional[NeuralRegion] = None
        prev_activation = 1.0
        for region in PIPELINE_ORDER:
            intrinsic = region_inputs[region]
            if prev_region is None:
                activation = intrinsic
            else:
                weight = self.get_weight(prev_region, region)
                activation = min(1.0, (prev_activation * weight * 0.65) + (intrinsic * 0.35))
            signal = NeuralSignal(
                region=region,
                activation=activation,
                payload={
                    "interaction_class": interaction_class,
                    "intent": intent,
                },
            )
            trace.signals.append(signal)
            prev_region = region
            prev_activation = activation
        return trace

    def modulate_strategy(
        self,
        *,
        allow_tools: bool,
        allow_followup: bool,
        allow_provider_switch: bool,
        trace: PropagationTrace,
    ) -> StrategyModulation:
        """Konservative Strategieanpassung basierend auf Aktivierungsniveau."""
        strategy_signal = next(
            (signal for signal in trace.signals if signal.region == NeuralRegion.STRATEGY),
            None,
        )
        if strategy_signal is None:
            return StrategyModulation()

        activation = strategy_signal.activation
        modulation = StrategyModulation()
        if activation < 0.35:
            modulation.allow_tools = False
            modulation.allow_followup = False
            modulation.neural_note = "[Neural] Niedrige Strategieaktivierung → konservativer Modus."
        elif activation < 0.5 and allow_tools:
            modulation.allow_tools = False
            modulation.neural_note = "[Neural] Moderate Aktivierung → Tools zurückhaltend."
        if activation > 0.85 and not allow_tools:
            modulation.neural_note = "[Neural] Hohe Aktivierung erkannt, bestehende Tool-Policy bleibt maßgeblich."

        retrieval_signal = next(
            (signal for signal in trace.signals if signal.region == NeuralRegion.RETRIEVAL),
            None,
        )
        if retrieval_signal and retrieval_signal.activation < 0.3:
            modulation.allow_provider_switch = False
            if modulation.neural_note:
                modulation.neural_note += " Wenig Kontext → Provider stabil halten."
            else:
                modulation.neural_note = "[Neural] Wenig Kontext → Provider stabil halten."

        return modulation

    def reinforce(self, trace: PropagationTrace, outcome_score: float) -> dict[str, float]:
        """Hebbian-artige Gewichtsanpassung aus Task-Ergebnis."""
        delta = 0.01 * ((outcome_score - 5.0) / 5.0)
        changed: dict[str, float] = {}
        for idx in range(1, len(trace.signals)):
            source = trace.signals[idx - 1].region
            target = trace.signals[idx].region
            key = _edge_key(source, target)
            if key not in self._weights:
                continue
            old = self._weights[key]
            new = max(0.1, min(1.0, old + delta))
            if abs(new - old) >= 0.0001:
                self._weights[key] = new
                changed[key] = new
        if changed:
            self._save_weights()
        return changed

    def snapshot(self) -> dict[str, Any]:
        return {
            "regions": [region.value for region in PIPELINE_ORDER],
            "weights": dict(self._weights),
        }

    def stats(self) -> dict[str, Any]:
        weights = list(self._weights.values())
        return {
            "regions": len(PIPELINE_ORDER),
            "synapses": len(self._weights),
            "avg_weight": round(sum(weights) / len(weights), 3) if weights else 0.0,
            "min_weight": round(min(weights), 3) if weights else 0.0,
            "max_weight": round(max(weights), 3) if weights else 0.0,
            "pipeline": [region.value for region in PIPELINE_ORDER],
            "weights": dict(self._weights),
        }


_cortex: Optional[NeuralCortex] = None


def get_neural_cortex() -> NeuralCortex:
    global _cortex
    if _cortex is None:
        _cortex = NeuralCortex()
    return _cortex