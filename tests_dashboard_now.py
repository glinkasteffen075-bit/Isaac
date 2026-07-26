"""Dashboard v6 NOW snapshot unit tests."""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ISAAC_DISABLE_VECTOR_MEMORY", "1")


class TestMonitorNow(unittest.TestCase):
    def test_idle_snapshot_shape(self):
        from monitor_now import PIPELINE_ORDER, build_now_snapshot, clear_now_override

        clear_now_override()
        exe = MagicMock()
        exe.running_tasks.return_value = []
        exe.all_tasks.return_value = []
        snap = build_now_snapshot(executor=exe, provider="groq")
        self.assertIn("headline", snap)
        self.assertIn("pipeline_phase", snap)
        self.assertIn("phases", snap)
        self.assertEqual(snap["pipeline_phase"], "idle")
        for p in PIPELINE_ORDER:
            self.assertIn(p, snap["phases"])
            self.assertEqual(snap["phases"][p]["status"], "idle")
        self.assertEqual(snap.get("provider"), "groq")

    def test_running_task_sets_phase(self):
        from monitor_now import build_now_snapshot, clear_now_override

        clear_now_override()
        task = {
            "id": "t_test1",
            "status": "running",
            "typ": "CHAT",
            "beschreibung": "Testfrage",
            "progress": 0.5,
            "strategy": {"allow_tools": False, "allow_followup": True},
            "decision_trace": [
                {"phase": "classification", "event": "ok", "data": {}},
                {"phase": "execution", "event": "llm", "data": {"n": 1}},
            ],
        }
        exe = MagicMock()
        exe.running_tasks.return_value = [task]
        snap = build_now_snapshot(executor=exe, provider="groq")
        self.assertEqual(snap["pipeline_phase"], "execution")
        self.assertEqual(snap["active_task_id"], "t_test1")
        self.assertIn("Testfrage", snap["headline"])
        self.assertEqual(snap["phases"]["execution"]["status"], "active")
        self.assertEqual(snap["phases"]["classification"]["status"], "done")

    def test_set_now_phase_override(self):
        from monitor_now import build_now_snapshot, clear_now_override, set_now_phase

        clear_now_override()
        set_now_phase("retrieval", headline="Hole Kontext", subline="blau")
        exe = MagicMock()
        exe.running_tasks.return_value = []
        exe.all_tasks.return_value = []
        snap = build_now_snapshot(executor=exe)
        self.assertEqual(snap["pipeline_phase"], "retrieval")
        self.assertIn("Hole Kontext", snap["headline"])
        clear_now_override()

    def test_build_state_includes_now(self):
        from monitor_server import MonitorServer

        mon = object.__new__(MonitorServer)
        mon.gate = MagicMock()
        mon.gate.is_paused = False
        mon.gate.status_dict.return_value = {}
        mon.gate.active_directives.return_value = []
        mon.memory = MagicMock()
        mon.memory.stats.return_value = {}
        mon.memory.recent_development_events.return_value = []
        mon.executor = MagicMock()
        mon.executor.stats.return_value = {"total": 0}
        mon.executor.running_tasks.return_value = []
        mon.executor.all_tasks.return_value = []
        mon.logic = MagicMock()
        mon.logic.stats.return_value = {}
        mon.relay = MagicMock()
        mon.relay.provider_status.return_value = []
        mon.cfg = MagicMock()
        mon.cfg.owner_name = "Steffen"
        mon.cfg.relay = MagicMock(primary_provider="groq")
        mon.cfg.monitor = MagicMock(push_interval=0.5)
        mon.cfg.memory = MagicMock()
        mon.cfg.browser = MagicMock()
        mon.cfg.filesystem_full_access = False
        mon.cfg.browser_automation = False
        mon.cfg.browser_external_sites = False
        mon.cfg.auto_provision_providers = True
        mon.cfg.auto_provision_all_providers = True
        mon.cfg.free_only_providers = True
        mon.cfg.multi_tool_mode = False
        mon.bound_host = "127.0.0.1"
        mon.bound_port = 8765
        mon.kernel = None
        mon._get_directives = lambda: []
        mon._get_open_questions = lambda: []
        mon._get_regelwerk_status = lambda: {}

        with patch("monitor_server.AuditLog") as al:
            al.stats.return_value = {}
            with patch("monitor_server.get_config", return_value=mon.cfg):
                with patch("monitor_server.get_dashboard") as gd:
                    gd.return_value = MagicMock(bound_port=8766)
                    state = mon._build_state()
        self.assertIn("now", state)
        self.assertIn("pipeline_phase", state["now"])
        self.assertIn("goals", state)
        self.assertIn("missions", state)
        self.assertIn("remote_smoke", state)


if __name__ == "__main__":
    unittest.main()
