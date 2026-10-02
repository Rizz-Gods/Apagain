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
        "capabilities": ["publish_posts", "mentions", "lead_sync", "analytics"],
    },
    "youtube": {
        "auth": "oauth",
        "setup_url": "https://console.cloud.google.com/",
        "env": "OTH_SOCIAL_YOUTUBE_TOKEN",
        "capabilities": ["upload_video", "comments", "analytics"],
    },
    "x": {
        "auth": "oauth",
        "setup_url": "https://developer.x.com/",
        "env": "OTH_SOCIAL_X_TOKEN",
        "capabilities": ["publish_posts", "mentions", "analytics"],
    },
    "instagram": {
        "auth": "oauth",
        "setup_url": "https://developers.facebook.com/",
        "env": "OTH_SOCIAL_INSTAGRAM_TOKEN",
        "capabilities": ["publish_media", "comments", "insights"],
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
        if action == "setup":
            providers = [provider] if provider else list(PROVIDERS)
            checklist = []
            for name in providers:
                spec = PROVIDERS.get(name)
                if not spec:
                    continue
                checklist.append({
                    "provider": name,
                    "setup_url": spec["setup_url"],
                    "auth": spec["auth"],
                    "credential_env": spec["env"],
                    "capabilities": spec["capabilities"],
                    "configured": bool(os.getenv(spec["env"])),
                })
            return AccountResult(True, {
                "mode": "one_step_provider_setup",
                "checklist": checklist,
                "security": "tokens are referenced by environment variable names; values are never persisted",
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
