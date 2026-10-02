import json
import os
import tempfile
import unittest
from pathlib import Path

from oth.core.social_accounts import SocialAccountManager
from oth.core.social_actions import SocialActionBus


class SocialAccountTests(unittest.TestCase):
    def test_probe_discovers_linkedin_actor(self):
        def requester(method, url, token, headers=None, body=None):
            return 200, {"sub": "member-123", "name": "Demo Account"}

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["OTH_SOCIAL_LINKEDIN_TOKEN"] = "test-token"
            try:
                worker = SocialAccountManager(tmp, requester=requester)
                result = worker.execute("probe", {"input": {"provider": "linkedin"}})
                self.assertTrue(result.success)
                self.assertEqual(
                    result.output["identity"]["actor"],
                    "urn:li:person:member-123",
                )
                saved = json.loads(
                    (Path(tmp) / "data" / "social_accounts.json").read_text()
                )
                self.assertEqual(
                    saved["accounts"][0]["identity"]["id"],
                    "member-123",
                )
            finally:
                os.environ.pop("OTH_SOCIAL_LINKEDIN_TOKEN", None)

    def test_probe_without_credentials_is_non_networking(self):
        calls = []

        def requester(*args, **kwargs):
            calls.append((args, kwargs))
            return 500, {}

        with tempfile.TemporaryDirectory() as tmp:
            os.environ.pop("OTH_SOCIAL_LINKEDIN_TOKEN", None)
            worker = SocialAccountManager(tmp, requester=requester)
            result = worker.execute("probe", {"input": {"provider": "linkedin"}})
            self.assertTrue(result.success)
            self.assertEqual(result.output["status"], "awaiting_credentials")
            self.assertEqual(calls, [])

    def test_oauth_browser_uses_chrome_and_loopback_listener(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "chrome.exe"
            browser.write_bytes(b"fake")
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "config" / "browser.json").write_text(json.dumps({
                "chrome_executable": str(browser),
                "profile": str(root / "profile"),
            }))
            os.environ["OTH_SOCIAL_LINKEDIN_CLIENT_ID"] = "client"
            os.environ["OTH_SOCIAL_LINKEDIN_REDIRECT_URI"] = "http://127.0.0.1:49123/callback"
            try:
                worker = SocialAccountManager(root)
                launched = []
                listeners = []
                worker._launch_chrome = lambda url: launched.append(url) or {"launched": True}
                worker._spawn_oauth_listener = lambda provider, state, host, port: listeners.append((provider, state, host, port)) or {"started": True, "pid": 42}
                result = worker.execute("oauth_browser", {"input": {"provider": "linkedin"}})
                self.assertTrue(result.success)
                self.assertEqual(result.output["callback_mode"], "loopback_auto_capture")
                self.assertTrue(result.output["browser"]["launched"])
                self.assertEqual(len(launched), 1)
                self.assertEqual(listeners[0][0], "linkedin")
                self.assertEqual(listeners[0][2:], ("127.0.0.1", 49123))
            finally:
                os.environ.pop("OTH_SOCIAL_LINKEDIN_CLIENT_ID", None)
                os.environ.pop("OTH_SOCIAL_LINKEDIN_REDIRECT_URI", None)

    def test_linkedin_publish_uses_discovered_actor(self):
        calls = []

        def requester(method, url, token, headers=None, body=None):
            calls.append((method, url, token, headers, body))
            return 201, {"id": "post-1"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts = root / "data" / "social_accounts.json"
            accounts.parent.mkdir(parents=True, exist_ok=True)
            accounts.write_text(json.dumps({
                "accounts": [{
                    "provider": "linkedin",
                    "account_label": "linkedin",
                    "identity": {"actor": "urn:li:person:member-123"}
                }]
            }))
            os.environ["OTH_SOCIAL_LINKEDIN_TOKEN"] = "test-token"
            try:
                worker = SocialActionBus(root, requester=requester)
                result = worker.execute("publish_text", {"input": {
                    "provider": "linkedin",
                    "text": "hello",
                }})
                self.assertTrue(result.success)
                self.assertEqual(calls[0][4]["author"], "urn:li:person:member-123")
            finally:
                os.environ.pop("OTH_SOCIAL_LINKEDIN_TOKEN", None)


if __name__ == "__main__":
    unittest.main()
