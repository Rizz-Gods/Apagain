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
