"""Regression: Letta cloud/config wiring (bounded, no live network)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from external_memory.config import ExternalMemoryConfig, load_external_memory_config
from external_memory.letta_adapter import LettaAdapter


class TestLettaConfig(unittest.TestCase):
    def test_load_cloud_fields_from_env(self) -> None:
        env = {
            "ISAAC_LETTA_ENABLED": "1",
            "ISAAC_LETTA_ALLOW_CLOUD": "1",
            "LETTA_API_KEY": "sk-let-test",
            "LETTA_BASE_URL": "https://api.letta.com",
            "LETTA_AGENT_ID": "agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            "LETTA_AGENT_NAME": "isaac",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = load_external_memory_config()
        self.assertTrue(cfg.letta_enabled)
        self.assertTrue(cfg.letta_allow_cloud)
        self.assertEqual(cfg.letta_api_key, "sk-let-test")
        self.assertEqual(cfg.letta_base_url, "https://api.letta.com")
        self.assertTrue(cfg.letta_agent_id.startswith("agent-"))

    def test_cloud_blocked_without_allow_flag(self) -> None:
        cfg = ExternalMemoryConfig(
            letta_enabled=True,
            letta_allow_cloud=False,
            letta_api_key="sk-let-test",
            letta_base_url="https://api.letta.com",
        )
        adapter = LettaAdapter(cfg)
        with mock.patch.object(adapter, "_http") as http:
            adapter._ensure()
            http.assert_not_called()
        self.assertFalse(adapter._cloud_ok)
        self.assertIn("ALLOW_CLOUD", adapter._init_error)

    def test_search_cloud_passages_text_only(self) -> None:
        cfg = ExternalMemoryConfig(
            letta_enabled=True,
            letta_allow_cloud=True,
            letta_api_key="sk-let-test",
            letta_base_url="https://api.letta.com",
            letta_agent_id="agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        )
        adapter = LettaAdapter(cfg)
        adapter._tried = True
        adapter._cloud_ok = True
        adapter._mode = "cloud"
        adapter._agent_id = cfg.letta_agent_id

        def fake_http(method, path, body=None, timeout=20.0):
            if path == "/v1/passages/search":
                return [
                    {
                        "score": 0.9,
                        "passage": {
                            "text": "Owner prefers privacy-first AI.",
                            "embedding": [0.0] * 8,
                        },
                    }
                ]
            if "core-memory" in path:
                return {"blocks": [{"label": "human", "value": "Owner is Steffen."}]}
            return {}

        with mock.patch.object(adapter, "_http", side_effect=fake_http):
            hits = adapter.search("privacy", limit=3)
        self.assertTrue(hits)
        self.assertTrue(any("privacy-first" in h.get("text", "") for h in hits))
        # embeddings must not leak into hit text
        self.assertFalse(any("0.0, 0.0" in h.get("text", "") for h in hits))

    def test_remember_requires_write_flag(self) -> None:
        cfg = ExternalMemoryConfig(
            letta_enabled=True,
            letta_allow_cloud=True,
            write_enabled=False,
            letta_api_key="sk-let-test",
            letta_agent_id="agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        )
        adapter = LettaAdapter(cfg)
        adapter._tried = True
        adapter._cloud_ok = True
        adapter._agent_id = cfg.letta_agent_id
        with mock.patch.object(adapter, "_http") as http:
            ok = adapter.remember(
                [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]
            )
            http.assert_not_called()
        self.assertFalse(ok)

    def test_remember_posts_archival(self) -> None:
        cfg = ExternalMemoryConfig(
            letta_enabled=True,
            letta_allow_cloud=True,
            write_enabled=True,
            letta_api_key="sk-let-test",
            letta_agent_id="agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        )
        adapter = LettaAdapter(cfg)
        adapter._tried = True
        adapter._cloud_ok = True
        adapter._agent_id = cfg.letta_agent_id
        with mock.patch.object(adapter, "_http", return_value=[{"id": "passage-1"}]) as http:
            ok = adapter.remember(
                [{"role": "user", "content": "prefers local"}, {"role": "assistant", "content": "ok"}]
            )
        self.assertTrue(ok)
        self.assertEqual(http.call_args[0][0], "POST")
        self.assertIn("archival-memory", http.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
