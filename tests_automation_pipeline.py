"""Stage 0–1 automation pipeline unit tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from automation_pipeline import (
    auto_pipeline_enabled,
    build_automation_status,
    build_ops_snapshot_text,
    format_automation_status,
    write_ops_snapshot_to_memory,
)


class TestAutomationPipeline(unittest.TestCase):
    def test_auto_pipeline_default_off(self):
        with patch.dict(os.environ, {"ISAAC_AUTO_PIPELINE": ""}, clear=False):
            os.environ.pop("ISAAC_AUTO_PIPELINE", None)
            self.assertFalse(auto_pipeline_enabled())
        with patch.dict(os.environ, {"ISAAC_AUTO_PIPELINE": "1"}):
            self.assertTrue(auto_pipeline_enabled())

    def test_build_status_shape(self):
        st = build_automation_status()
        for key in (
            "isaac", "render", "cognee", "letta", "github", "sentry", "local_llm", "flags", "ready",
        ):
            self.assertIn(key, st)
        self.assertIn("memory_loop", st["ready"])
        self.assertIn("local_llm", st["ready"])
        text = format_automation_status(st)
        self.assertIn("[Automation Pipeline]", text)
        self.assertIn("Render:", text)
        self.assertIn("Cognee:", text)
        self.assertIn("GitHub:", text)
        self.assertIn("Sentry:", text)
        self.assertIn("LocalLLM:", text)

    def test_probe_local_llm_ollama_mock(self):
        from automation_pipeline import _probe_local_llm

        with patch.dict(
            os.environ,
            {"ACTIVE_PROVIDER": "ollama", "OLLAMA_HOST": "http://127.0.0.1:9", "OLLAMA_MODEL": "x"},
        ):
            with patch(
                "automation_pipeline._http_json",
                return_value=(True, {"models": [{"name": "x:latest"}]}),
            ):
                out = _probe_local_llm()
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("mode"), "ollama")
        self.assertIn("x:latest", out.get("models_hint") or [])

    def test_ops_snapshot_text_contains_markers(self):
        st = {
            "ts": "2026-01-01T00:00:00",
            "render": {"ok": True, "git_commit": "abc", "active_provider": "openrouter"},
            "cognee": {"ok": True, "mode": "cloud", "health_ok": True},
            "github": {"ok": True, "login": "tester", "auto_pr": False},
            "sentry": {
                "dsn_set": True,
                "unresolved_count_sample": 1,
                "unresolved_preview": [
                    {"shortId": "ISAAC-4", "count": "10", "title": "Unclosed connector"}
                ],
            },
        }
        text = build_ops_snapshot_text(st)
        self.assertIn("isaac_ops snapshot", text)
        self.assertIn("ISAAC-4", text)
        self.assertIn("render_ok=True", text)

    def test_write_skipped_when_pipeline_off(self):
        with patch.dict(os.environ, {"ISAAC_AUTO_PIPELINE": "0"}):
            result = write_ops_snapshot_to_memory(force=False)
        self.assertFalse(result.get("ok"))
        self.assertIn("ISAAC_AUTO_PIPELINE", result.get("skipped") or "")

    def test_status_pipeline_intent(self):
        from isaac_core import detect_intent, Intent

        self.assertEqual(detect_intent("status:pipeline"), Intent.EXT_MEMORY)
        self.assertEqual(detect_intent("status:pipeline sync"), Intent.EXT_MEMORY)
        self.assertEqual(detect_intent("pipeline status"), Intent.EXT_MEMORY)

    def test_daily_stack_health_scheduled(self):
        from owner_autonomy import DEFAULT_SCHEDULED_OWNER_TASKS

        ids = {t.task_id for t in DEFAULT_SCHEDULED_OWNER_TASKS}
        self.assertIn("daily_stack_health", ids)
        task = next(t for t in DEFAULT_SCHEDULED_OWNER_TASKS if t.task_id == "daily_stack_health")
        self.assertEqual(task.action_kind, "automation_ops")

    def test_daily_remote_smoke_scheduled(self):
        from owner_autonomy import DEFAULT_SCHEDULED_OWNER_TASKS

        task = next(
            t for t in DEFAULT_SCHEDULED_OWNER_TASKS if t.task_id == "daily_remote_smoke"
        )
        self.assertEqual(task.action_kind, "automation_ops")
        self.assertEqual((task.params or {}).get("op"), "remote_smoke")

    def test_remote_smoke_wake_interval_under_sleep(self):
        from remote_smoke import (
            RENDER_SLEEP_THRESHOLD_S,
            MAX_WAKE_INTERVAL_S,
            classify_expectation,
            build_smoke_memory_text,
            wake_interval_s,
        )

        self.assertLess(MAX_WAKE_INTERVAL_S, RENDER_SLEEP_THRESHOLD_S)
        with patch.dict(os.environ, {"ISAAC_REMOTE_SMOKE_WAKE_INTERVAL_S": "99999"}):
            # hard-capped so Free cannot sleep between pings
            self.assertLessEqual(wake_interval_s(), MAX_WAKE_INTERVAL_S)
            self.assertLess(wake_interval_s(), RENDER_SLEEP_THRESHOLD_S)
        with patch.dict(os.environ, {"ISAAC_REMOTE_SMOKE_WAKE_INTERVAL_S": "600"}):
            self.assertEqual(wake_interval_s(), 600.0)

        ok, _ = classify_expectation("A", "Hallo Steffen!")
        self.assertTrue(ok)
        ok_g, note = classify_expectation(
            "G", "Ich habe mich erfolgreich bei Google eingeloggt"
        )
        self.assertFalse(ok_g)
        self.assertIn("hallucin", note.lower())

        text = build_smoke_memory_text(
            {
                "mode": "full",
                "ts": "t",
                "ok": True,
                "url": "https://isaac-free.onrender.com",
                "git_commit": "abc",
                "active_provider": "groq",
                "wake_interval_s": 600,
                "full_interval_s": 7200,
                "health": {"ok": True, "ms": 12},
                "cases": [
                    {
                        "case": "A",
                        "pass": True,
                        "ms": 100,
                        "expect_note": "greeting",
                        "response": "Hallo",
                    }
                ],
                "sentry": {
                    "ok": True,
                    "unresolved_count_sample": 1,
                    "unresolved_preview": [
                        {"shortId": "ISAAC-1", "count": 2, "title": "x"}
                    ],
                },
            }
        )
        self.assertIn("remote_smoke", text)
        self.assertIn("ISAAC-1", text)
        self.assertIn("case A", text)

    def test_status_smoke_intent(self):
        from isaac_core import detect_intent, Intent

        self.assertEqual(detect_intent("status:smoke"), Intent.EXT_MEMORY)
        self.assertEqual(detect_intent("status:smoke wake"), Intent.EXT_MEMORY)
        self.assertEqual(detect_intent("smoke:remote full"), Intent.EXT_MEMORY)


if __name__ == "__main__":
    unittest.main()
