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


if __name__ == "__main__":
    unittest.main()
