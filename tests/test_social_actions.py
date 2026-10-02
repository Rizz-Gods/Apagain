import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.core.secure_tokens import SecureTokenStore
from oth.core.social_actions import SocialActionBus

class SocialActionTests(unittest.TestCase):
    def test_doctor_does_not_call_network_without_credentials(self):
        called = []
        def requester(*args, **kwargs):
            called.append((args, kwargs))
            return 200, {}
        for name in (
            "OTH_SOCIAL_LINKEDIN_TOKEN",
            "OTH_SOCIAL_YOUTUBE_TOKEN",
            "OTH_SOCIAL_X_TOKEN",
            "OTH_SOCIAL_INSTAGRAM_TOKEN",
        ):
            os.environ.pop(name, None)
        worker = SocialActionBus(requester=requester)
        result = worker.execute("doctor", {"input": {}})
        self.assertTrue(result.success)
        self.assertEqual(called, [])
        self.assertTrue(all(
            item.get("status") == "awaiting_credentials"
            for item in result.output["providers"]
        ))

    def test_linkedin_publish_uses_common_action_contract(self):
        calls = []
        def requester(method, url, token, headers=None, body=None):
            calls.append({
                "method": method,
                "url": url,
                "token": token,
                "headers": headers,
                "body": body,
            })
            return 201, {"id": "urn:li:share:demo"}
        os.environ["OTH_SOCIAL_LINKEDIN_TOKEN"] = "test-token"
        try:
            worker = SocialActionBus(requester=requester)
            result = worker.execute("publish_text", {
                "input": {
                    "provider": "linkedin",
                    "actor": "urn:li:person:test",
                    "text": "Hello from OTH.",
                }
            })
            self.assertTrue(result.success)
            self.assertEqual(result.output["status"], "published")
            self.assertEqual(calls[0]["method"], "POST")
            self.assertIn("/rest/posts", calls[0]["url"])
            self.assertEqual(calls[0]["body"]["author"], "urn:li:person:test")
        finally:
            os.environ.pop("OTH_SOCIAL_LINKEDIN_TOKEN", None)

    def test_youtube_refreshes_expired_secure_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["OTH_SOCIAL_YOUTUBE_CLIENT_ID"] = "youtube-client"
            os.environ["OTH_SOCIAL_YOUTUBE_CLIENT_SECRET"] = "youtube-secret"
            try:
                store = SecureTokenStore(tmp)
                store.set("youtube", {
                    "access_token": "expired-token",
                    "refresh_token": "refresh-token",
                    "expires_at": time.time() - 60,
                })
                import oth.core.social_actions as social_actions_module

                class FakeResponse:
                    def __enter__(self):
                        return self
                    def __exit__(self, *args):
                        return None
                    def read(self):
                        return b'{"access_token":"refreshed-token","expires_in":3600}'

                original_urlopen = social_actions_module.urlopen
                social_actions_module.urlopen = lambda *args, **kwargs: FakeResponse()
                try:
                    worker = SocialActionBus(root=tmp)
                    token = worker._token("youtube", worker._spec("youtube"))
                    self.assertEqual(token, "refreshed-token")
                    self.assertEqual(
                        store.get("youtube")["access_token"], "refreshed-token"
                    )
                finally:
                    social_actions_module.urlopen = original_urlopen
            finally:
                os.environ.pop("OTH_SOCIAL_YOUTUBE_CLIENT_ID", None)
                os.environ.pop("OTH_SOCIAL_YOUTUBE_CLIENT_SECRET", None)

    def test_public_publish_is_blocked_until_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "agents.json").write_text('{"agents":[]}')
            (root / "config" / "skills.json").write_text('{"skills":[]}')
            (root / "config" / "tools.json").write_text('{"tools":[]}')
            (root / "config" / "schedules.json").write_text('{"schedules":[]}')
            (root / "config" / "policies.json").write_text(
                '{"external_actions_require_approval":true,"financial_actions_require_approval":true}'
            )
            kernel = OTHKernel(root)
            task = kernel.submit("social-actions", "publish_text", {
                "input": {"provider": "linkedin", "text": "hello"}
            })
            result = kernel.dispatch(task.id)
            self.assertEqual(result["status"], "blocked")
            kernel.close()

if __name__ == "__main__":
    unittest.main()
