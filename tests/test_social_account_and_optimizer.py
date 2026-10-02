import json
import os
import tempfile
import unittest
from pathlib import Path

from oth.core.secure_tokens import SecureTokenStore
from oth.core.social_accounts import SocialAccountManager
from oth.core.social_optimizer import SocialOptimizer

class SocialAccountAndOptimizerTests(unittest.TestCase):
    def test_setup_never_persists_secret_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            os.environ["OTH_SOCIAL_LINKEDIN_TOKEN"] = "secret-test-value"
            try:
                worker = SocialAccountManager(root)
                result = worker.execute("setup", {"input": {"provider": "linkedin"}})
                self.assertTrue(result.success)
                self.assertTrue(result.output["checklist"][0]["configured"])
                self.assertNotIn("secret-test-value", json.dumps(result.output))
            finally:
                os.environ.pop("OTH_SOCIAL_LINKEDIN_TOKEN", None)

    def test_onboard_reports_provider_specific_oauth_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = SocialAccountManager(root)
            result = worker.execute("onboard", {"input": {"provider": "linkedin"}})
            self.assertTrue(result.success)
            item = result.output["checklist"][0]
            self.assertEqual(item["provider"], "linkedin")
            self.assertIn("w_member_social", item["scopes"])
            self.assertEqual(item["next_step"], "configure_app_credentials")

    def test_oauth_start_generates_scoped_authorization_url_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["OTH_SOCIAL_LINKEDIN_CLIENT_ID"] = "client-demo"
            os.environ["OTH_SOCIAL_LINKEDIN_REDIRECT_URI"] = "https://example.test/oauth/callback"
            try:
                worker = SocialAccountManager(tmp)
                result = worker.execute("oauth_start", {"input": {"provider": "linkedin"}})
                self.assertTrue(result.success)
                self.assertIn("authorization_ready", result.output["status"])
                self.assertIn("client-demo", result.output["authorization_url"])
                self.assertNotIn("client_secret", result.output["authorization_url"])
            finally:
                os.environ.pop("OTH_SOCIAL_LINKEDIN_CLIENT_ID", None)
                os.environ.pop("OTH_SOCIAL_LINKEDIN_REDIRECT_URI", None)

    def test_oauth_callback_stores_tokens_only_in_secure_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["OTH_SOCIAL_LINKEDIN_CLIENT_ID"] = "client-demo"
            os.environ["OTH_SOCIAL_LINKEDIN_CLIENT_SECRET"] = "secret-demo"
            os.environ["OTH_SOCIAL_LINKEDIN_REDIRECT_URI"] = "https://example.test/oauth/callback"
            try:
                worker = SocialAccountManager(tmp)
                started = worker.execute("oauth_start", {"input": {"provider": "linkedin"}})
                state = started.output["state"]
                worker.token_store.set(f"oauth-code:{state}", {"code": "auth-code-demo"})
                worker._exchange_code = lambda provider, spec, code, redirect: {
                    "access_token": "access-demo",
                    "expires_in": 3600,
                    "refresh_token": "refresh-demo",
                    "scope": "openid w_member_social",
                    "token_type": "Bearer",
                }
                result = worker.execute("oauth_callback", {
                    "input": {"provider": "linkedin", "state": state}
                })
                self.assertTrue(result.success)
                self.assertEqual(result.output["status"], "connected")
                self.assertNotIn("access-demo", json.dumps(result.output))
                self.assertEqual(worker.token_store.get("linkedin")["access_token"], "access-demo")
                self.assertIsNone(worker.token_store.get(f"oauth-code:{state}"))
            finally:
                for name in (
                    "OTH_SOCIAL_LINKEDIN_CLIENT_ID",
                    "OTH_SOCIAL_LINKEDIN_CLIENT_SECRET",
                    "OTH_SOCIAL_LINKEDIN_REDIRECT_URI",
                ):
                    os.environ.pop(name, None)

    def test_secure_token_store_encrypts_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SecureTokenStore(tmp)
            store.set("linkedin", {"access_token": "secret-test", "expires_at": 9999999999})
            raw = (Path(tmp) / "data" / "social_tokens.secure").read_text(encoding="utf-8")
            self.assertNotIn("secret-test", raw)
            self.assertEqual(store.get("linkedin")["access_token"], "secret-test")

    def test_optimizer_recommends_from_recorded_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = SocialOptimizer(root)
            worker.execute("record", {
                "input": {
                    "platform": "linkedin",
                    "content_id": "a",
                    "hook": "manual work is killing sales",
                    "format": "carousel",
                    "pillar": "pain",
                    "metrics": {
                        "impressions": 1000,
                        "engagements": 100,
                        "qualified_leads": 12,
                        "conversions": 2,
                    },
                }
            })
            result = worker.execute("optimize", {"input": {"platform": "linkedin"}})
            self.assertTrue(result.success)
            self.assertEqual(result.output["best"][0]["content_id"], "a")
            self.assertTrue(result.output["recommendations"])
            self.assertEqual(len(result.output["next_experiments"]), 3)

if __name__ == "__main__":
    unittest.main()
