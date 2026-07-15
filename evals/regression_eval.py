from __future__ import annotations

from unittest.mock import patch

from security_policy import get_confirmation_policy
from privilege import get_gate, isaac_ctx
from config import get_config


def run() -> dict:
    """Regression-Evals ohne Admin-Mode, damit Review-Pflicht messbar bleibt."""
    cfg = get_config()
    previous_mode = getattr(cfg, "privilege_mode", "user")
    try:
        cfg.privilege_mode = "user"
        with (
            patch("privilege.is_owner_equivalent_mode", return_value=False),
            patch("security_policy.is_owner_equivalent_mode", return_value=False),
            patch("config.is_owner_equivalent_mode", return_value=False),
        ):
            gate = get_gate()
            pol = get_confirmation_policy()
            before = len(pol.pending())
            ok, reason = gate.authorize(
                "execute_code",
                isaac_ctx("Eval", "Auditierter Test für hochriskante Codeausführung mit Außenwirkung"),
            )
            after = len(pol.pending())
            cases = [
                {"name": "high_risk_action_requires_review", "ok": (not ok), "detail": reason},
                {
                    "name": "review_queue_grows",
                    "ok": after >= before + 1,
                    "detail": {"before": before, "after": after},
                },
            ]
    finally:
        cfg.privilege_mode = previous_mode
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "regression", "passed": passed, "total": len(cases), "cases": cases}
