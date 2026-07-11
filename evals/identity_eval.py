from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import self_model as self_model_module
from self_model import SelfModel, get_self_model
from constitution import get_constitution
from self_model_hooks import (
    process_interaction,
    enrich_retrieval_with_self_model,
    detect_self_model_fact_contradictions,
)


def run() -> dict:
    sm = get_self_model()
    sm.sync_constitutional_state()
    snapshot = sm.snapshot()
    c = get_constitution().summary()
    cases = [
        {"name": "identity_has_core", "ok": bool(snapshot.get("identity_core", {}).get("name")), "detail": snapshot.get("identity_core", {})},
        {"name": "constitution_version_linked", "ok": snapshot.get("constitutional_state", {}).get("constitution_version") == c.get("version"), "detail": {"self_model": snapshot.get("constitutional_state", {}).get("constitution_version"), "constitution": c.get("version")}},
        {"name": "immutable_claims_present", "ok": len(snapshot.get("identity_core", {}).get("immutable_claims", [])) >= 2, "detail": snapshot.get("identity_core", {}).get("immutable_claims", [])},
    ]

    updates = process_interaction(
        user_input="Ich bevorzuge kurze nüchterne Antworten",
        interaction_class="NORMAL_CHAT",
        score=7.0,
    )
    pref = sm.relevant_preferences(limit=5)
    cases.append({
        "name": "preference_extracted_from_owner_statement",
        "ok": bool(updates.get("preferences")) and any("kurz" in str(p.get("value", "")).lower() or p.get("key") == "prefer" for p in pref),
        "detail": {"updates": updates.get("preferences", [])[:2], "prefs": pref[:2]},
    })

    enriched = enrich_retrieval_with_self_model({"preferences_context": []})
    cases.append({
        "name": "self_model_preferences_in_retrieval",
        "ok": bool(enriched.get("self_model_preferences") or enriched.get("preferences_context")),
        "detail": {"count": len(enriched.get("self_model_preferences", []))},
    })

    confirm_updates = process_interaction(
        user_input="Danke, genau so",
        interaction_class="SOCIAL_ACKNOWLEDGMENT",
        score=6.5,
    )
    cases.append({
        "name": "confirmation_boosts_pending_preferences",
        "ok": confirm_updates.get("confirmations", 0) >= 1,
        "detail": {"confirmations": confirm_updates.get("confirmations", 0)},
    })

    casual_updates = process_interaction(
        user_input="Kannst du das Wetter als Motiv kürzer erklären?",
        interaction_class="NORMAL_CHAT",
        score=7.0,
    )
    cases.append({
        "name": "casual_style_mention_not_recorded",
        "ok": not casual_updates.get("preferences"),
        "detail": {"preferences": len(casual_updates.get("preferences", []))},
    })

    class FakeMemory:
        def __init__(self, facts: dict[str, str]):
            self._facts = dict(facts)

        def get_fact_record(self, key: str):
            value = self._facts.get(key)
            if value is None:
                return None
            return {"key": key, "value": value, "confidence": 1.0, "source": "Steffen"}

        def all_facts(self):
            return dict(self._facts)

        def set_fact(self, key, value, source="", confidence=1.0):
            self._facts[key] = value
            return True

        def log_development_event(self, **kwargs):
            return None

    with tempfile.TemporaryDirectory() as tmp:
        isolated = SelfModel(path=Path(tmp) / "self_model.json")
        previous = self_model_module._model
        self_model_module._model = isolated
        try:
            isolated.record_owner_preference(
                key="response_style",
                value="kurz und knapp",
                confidence=0.9,
                source="owner_correction",
            )
            fact_key = isolated._preference_fact_key({
                "key": "response_style",
                "value": "kurz und knapp",
            })
            fake_memory = FakeMemory({fact_key: "ausführlich und detailliert"})
            contradictions = detect_self_model_fact_contradictions(memory=fake_memory)
            enriched = enrich_retrieval_with_self_model(
                {"preferences_context": [], "risk_flags": []},
                memory=fake_memory,
            )
            cases.append({
                "name": "contradiction_detected_via_hooks",
                "ok": bool(contradictions) and any(
                    c.get("kind") in {
                        "self_model_vs_memory",
                        "avoid_conflicts_memory_fact",
                    }
                    for c in contradictions
                ),
                "detail": {"count": len(contradictions), "kinds": [c.get("kind") for c in contradictions[:3]]},
            })
            cases.append({
                "name": "contradictions_surface_in_retrieval",
                "ok": bool(enriched.get("self_model_contradictions"))
                and "self_model_fact_contradiction" in (enriched.get("risk_flags") or []),
                "detail": {
                    "risk_flags": enriched.get("risk_flags", []),
                    "count": len(enriched.get("self_model_contradictions", [])),
                },
            })
        finally:
            self_model_module._model = previous

    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "identity", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
