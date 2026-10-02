import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROVIDERS = {
    "linkedin": {
        "auth": "oauth",
        "setup_url": "https://www.linkedin.com/developers/apps",
        "env": "OTH_SOCIAL_LINKEDIN_TOKEN",
        "client_id_env": "OTH_SOCIAL_LINKEDIN_CLIENT_ID",
        "client_secret_env": "OTH_SOCIAL_LINKEDIN_CLIENT_SECRET",
        "redirect_env": "OTH_SOCIAL_LINKEDIN_REDIRECT_URI",
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "capabilities": ["publish_posts", "mentions", "lead_sync", "analytics"],
        "scopes": ["openid", "profile", "email", "w_member_social"],
        "redirect_note": "LinkedIn requires the exact HTTPS redirect URI to be registered in the developer app.",
    },
    "youtube": {
        "auth": "oauth",
        "setup_url": "https://console.cloud.google.com/",
        "env": "OTH_SOCIAL_YOUTUBE_TOKEN",
        "client_id_env": "OTH_SOCIAL_YOUTUBE_CLIENT_ID",
        "client_secret_env": "OTH_SOCIAL_YOUTUBE_CLIENT_SECRET",
        "redirect_env": "OTH_SOCIAL_YOUTUBE_REDIRECT_URI",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "capabilities": ["upload_video", "comments", "analytics"],
        "scopes": ["https://www.googleapis.com/auth/youtube"],
        "redirect_note": "Google permits localhost redirect URIs for local testing when configured in the OAuth client.",
    },
    "x": {
        "auth": "oauth",
        "setup_url": "https://developer.x.com/",
        "env": "OTH_SOCIAL_X_TOKEN",
        "capabilities": ["publish_posts", "mentions", "analytics"],
        "scopes": [],
        "redirect_note": "Configure the provider's OAuth application and callback according to the current developer portal settings.",
    },
    "instagram": {
        "auth": "oauth",
        "setup_url": "https://developers.facebook.com/",
        "env": "OTH_SOCIAL_INSTAGRAM_TOKEN",
        "capabilities": ["publish_media", "comments", "insights"],
        "scopes": [],
        "redirect_note": "Configure the provider's Meta app and callback according to the current developer portal settings.",
    },
}

@dataclass
class AccountResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialAccountManager:
    id = "social-accounts"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "social_accounts.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def supports(self, capability: str) -> bool:
        return capability == "social-accounts"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"accounts": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def execute(self, action: str, payload: dict) -> AccountResult:
        source = payload.get("input", {})
        provider = str(source.get("provider", "")).lower()
        if action in {"setup", "onboard"}:
            providers = [provider] if provider else list(PROVIDERS)
            checklist = []
            for name in providers:
                spec = PROVIDERS.get(name)
                if not spec:
                    continue
                credential_present = bool(os.getenv(spec["env"]))
                client_id_present = bool(spec.get("client_id_env") and os.getenv(spec["client_id_env"]))
                redirect_present = bool(spec.get("redirect_env") and os.getenv(spec["redirect_env"]))
                checklist.append({
                    "provider": name,
                    "setup_url": spec["setup_url"],
                    "auth": spec["auth"],
                    "credential_env": spec["env"],
                    "client_id_env": spec.get("client_id_env"),
                    "client_secret_env": spec.get("client_secret_env"),
                    "redirect_env": spec.get("redirect_env"),
                    "redirect_note": spec.get("redirect_note"),
                    "scopes": spec.get("scopes", []),
                    "capabilities": spec["capabilities"],
                    "configured": credential_present,
                    "oauth_ready": bool(client_id_present and redirect_present),
                    "next_step": (
                        "probe_account"
                        if credential_present
                        else ("start_oauth" if client_id_present and redirect_present else "configure_app_credentials")
                    ),
                })
            return AccountResult(True, {
                "mode": "guided_social_onboarding",
                "checklist": checklist,
                "security": "tokens and client secrets are referenced by environment variable names; secret values are never persisted by OTH.",
            })
        if action == "connect":
            spec = PROVIDERS.get(provider)
            if not spec:
                return AccountResult(False, {}, f"Unsupported social provider: {provider}")
            configured = bool(os.getenv(spec["env"]))
            data = self._load()
            record = {
                "provider": provider,
                "account_label": str(source.get("account_label", provider)),
                "status": "ready" if configured else "awaiting_credentials",
                "setup_url": spec["setup_url"],
                "auth": spec["auth"],
                "credential_env": spec["env"],
                "capabilities": spec["capabilities"],
                "credential_present": configured,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            data["accounts"] = [
                a for a in data["accounts"]
                if not (a["provider"] == provider and a["account_label"] == record["account_label"])
            ]
            data["accounts"].append(record)
            self._save(data)
            return AccountResult(True, record)
        if action == "status":
            data = self._load()
            for account in data["accounts"]:
                env = account.get("credential_env")
                account["credential_present"] = bool(env and os.getenv(env))
                account["status"] = "ready" if account["credential_present"] else "awaiting_credentials"
            self._save(data)
            return AccountResult(True, {"accounts": data["accounts"]})
        return AccountResult(False, {}, f"Unsupported social-accounts action: {action}")
