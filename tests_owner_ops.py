"""Tests for ntfy owner push, remote smoke flags, login flow catalog."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class TestOwnerNotifyNtfy(unittest.TestCase):
    def test_status_text_without_topic(self):
        from owner_notify import status_text

        with mock.patch.dict(os.environ, {"ISAAC_NTFY_TOPIC": "", "NTFY_TOPIC": ""}, clear=False):
            text = status_text()
        self.assertIn("Owner-Push", text)
        self.assertIn("ntfy", text.lower())

    def test_send_ntfy_posts_when_topic_set(self):
        from owner_notify import _send_ntfy

        with mock.patch.dict(
            os.environ,
            {"ISAAC_NTFY_TOPIC": "isaac-test-topic", "ISAAC_NTFY_URL": "https://ntfy.sh"},
            clear=False,
        ):
            with mock.patch("owner_notify.urllib.request.urlopen") as uo:
                resp = mock.MagicMock()
                resp.status = 200
                resp.__enter__ = mock.MagicMock(return_value=resp)
                resp.__exit__ = mock.MagicMock(return_value=False)
                uo.return_value = resp
                out = _send_ntfy("t", "body", priority="high")
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("channel"), "ntfy")
        req = uo.call_args[0][0]
        self.assertIn("isaac-test-topic", req.full_url)


class TestLoginFlowCatalog(unittest.TestCase):
    def test_x_flow_in_catalog(self):
        from owner_login_probe import probe_targets

        targets = probe_targets(["x", "twitter", "google"])
        ids = {t.target_id for t in targets}
        self.assertIn("x", ids)
        self.assertIn("google", ids)
        x = next(t for t in targets if t.target_id == "x")
        self.assertIn("x.com", x.login_url)

    def test_named_flow_requires_admin_and_creds(self):
        import asyncio
        from owner_login_probe import run_named_login_flow

        with mock.patch("owner_login_probe.is_owner_equivalent_mode", return_value=False):
            out = asyncio.run(run_named_login_flow("x"))
        self.assertFalse(out.get("ok"))
        self.assertIn("Admin", out.get("error", "") + "Admin")

        with mock.patch("owner_login_probe.is_owner_equivalent_mode", return_value=True):
            with mock.patch(
                "owner_login_probe.load_probe_config",
                return_value={"emails": [], "passwords": []},
            ):
                out = asyncio.run(run_named_login_flow("x"))
        self.assertFalse(out.get("ok"))
        self.assertIn("Credential", out.get("error", ""))


class TestRemoteSmokeFlag(unittest.TestCase):
    def test_enabled_flag(self):
        from remote_smoke import remote_smoke_enabled

        with mock.patch.dict(os.environ, {"ISAAC_REMOTE_SMOKE": "1"}, clear=False):
            self.assertTrue(remote_smoke_enabled())
        with mock.patch.dict(os.environ, {"ISAAC_REMOTE_SMOKE": "0"}, clear=False):
            self.assertFalse(remote_smoke_enabled())


class TestIntentOps(unittest.TestCase):
    def test_detect_ntfy_and_login_flow(self):
        from isaac_core import detect_intent, Intent

        self.assertEqual(detect_intent("ntfy test"), Intent.EXT_MEMORY)
        self.assertEqual(detect_intent("remote smoke wake"), Intent.EXT_MEMORY)
        self.assertEqual(detect_intent("login flow: x"), Intent.EXT_MEMORY)
        self.assertEqual(detect_intent("browser login flow: google"), Intent.EXT_MEMORY)


if __name__ == "__main__":
    unittest.main()
