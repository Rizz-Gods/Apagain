import json
import os
import secrets
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oth.core.secure_tokens import SecureTokenStore

PROVIDERS = {
    "linkedin": {
        "auth": "oauth",
        "setup_url": "https://www.linkedin.com/developers/apps",
        "env": "OTH_SOCIAL_LINKEDIN_TOKEN",
        "client_id_env": "OTH_SOCIAL_LINKEDIN_CLIENT_ID",
        "client_secret_env": "OTH_SOCIAL_LINKEDIN_CLIENT_SECRET",
        "redirect_env": "OTH_SOCIAL_LINKEDIN_REDIRECT_URI",
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
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
        "token_url": "https://oauth2.googleapis.com/token",
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
        self.oauth_path = self.root / "data" / "social_oauth.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.token_store = SecureTokenStore(self.root)

    def supports(self, capability: str) -> bool:
        return capability == "social-accounts"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"accounts": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _oauth_load(self) -> dict[str, Any]:
        if not self.oauth_path.exists():
            return {"pending": {}}
        return json.loads(self.oauth_path.read_text(encoding="utf-8"))

    def _oauth_save(self, data: dict[str, Any]) -> None:
        self.oauth_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _exchange_code(self, provider: str, spec: dict[str, Any], code: str, redirect_uri: str) -> dict[str, Any]:
        client_id = os.getenv(spec.get("client_id_env", ""))
        client_secret = os.getenv(spec.get("client_secret_env", ""))
        if not client_id or not client_secret:
            raise RuntimeError("OAuth callback requires client ID and client secret environment variables")
        form = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }).encode("utf-8")
        request = urllib.request.Request(
            spec["token_url"],
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _oauth_start(self, provider: str) -> AccountResult:
        spec = PROVIDERS.get(provider)
        if not spec or not spec.get("auth_url"):
            return AccountResult(False, {}, f"OAuth start is not configured for {provider}")
        client_id = os.getenv(spec.get("client_id_env", ""))
        redirect_uri = os.getenv(spec.get("redirect_env", ""))
        if not client_id or not redirect_uri:
            return AccountResult(False, {}, "OAuth start requires the provider client ID and redirect URI environment variables")
        state = secrets.token_urlsafe(32)
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        scopes = spec.get("scopes", [])
        if scopes:
            params["scope"] = " ".join(scopes)
        if provider == "youtube":
            params.update({
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
            })
        query = urllib.parse.urlencode(params)
        data = self._oauth_load()
        data.setdefault("pending", {})[state] = {
            "provider": provider,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._oauth_save(data)
        return AccountResult(True, {
            "provider": provider,
            "status": "authorization_ready",
            "authorization_url": f"{spec['auth_url']}?{query}",
            "state": state,
            "redirect_uri": redirect_uri,
            "scopes": scopes,
            "security": "OAuth state is persisted; client secrets and authorization codes are not.",
        })

    def _oauth_callback(self, provider: str, state: str) -> AccountResult:
        spec = PROVIDERS.get(provider)
        if not spec or not spec.get("token_url"):
            return AccountResult(False, {}, f"OAuth callback is not configured for {provider}")
        pending = self._oauth_load().get("pending", {})
        session = pending.get(state)
        if not session or session.get("provider") != provider:
            return AccountResult(False, {}, "Invalid or unknown OAuth state")
        code_record = self.token_store.get(f"oauth-code:{state}")
        if not code_record or not code_record.get("code"):
            return AccountResult(False, {}, "OAuth authorization code is not available in the secure callback handoff")
        redirect_uri = os.getenv(spec.get("redirect_env", ""))
        if not redirect_uri:
            return AccountResult(False, {}, "OAuth callback requires the registered redirect URI environment variable")
        try:
            tokens = self._exchange_code(provider, spec, code_record["code"], redirect_uri)
        except Exception as exc:
            return AccountResult(False, {}, f"OAuth token exchange failed: {exc}", retryable=True)
        access_token = tokens.get("access_token")
        if not access_token:
            return AccountResult(False, {}, "OAuth provider returned no access token")
        expires_in = int(tokens.get("expires_in", 0) or 0)
        secure_payload = {
            "access_token": access_token,
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": datetime.now(timezone.utc).timestamp() + expires_in if expires_in else 0,
            "scope": tokens.get("scope", ""),
            "token_type": tokens.get("token_type", "Bearer"),
        }
        self.token_store.set(provider, secure_payload)
        pending.pop(state, None)
        self._oauth_save({"pending": pending})
        account = {
            "provider": provider,
            "account_label": provider,
            "status": "ready",
            "setup_url": spec["setup_url"],
            "auth": spec["auth"],
            "credential_env": spec["env"],
            "credential_present": True,
            "credential_source": "windows_dpapi",
            "capabilities": spec["capabilities"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        data = self._load()
        data["accounts"] = [
            a for a in data["accounts"]
            if not (a.get("provider") == provider and a.get("account_label") == provider)
        ]
        data["accounts"].append(account)
        self._save(data)
        self.token_store.delete(f"oauth-code:{state}")
        return AccountResult(True, {
            "provider": provider,
            "status": "connected",
            "credential_source": "windows_dpapi",
            "expires_at": secure_payload["expires_at"],
            "refresh_token_present": bool(secure_payload["refresh_token"]),
            "capabilities": spec["capabilities"],
        })

    def execute(self, action: str, payload: dict) -> AccountResult:
        source = payload.get("input", {})
        provider = str(source.get("provider", "")).lower()
        if action == "oauth_callback":
            return self._oauth_callback(provider, str(source.get("state", "")))
        if action == "oauth_start":
            return self._oauth_start(provider)
        if action in {"setup", "onboard"}:
            providers = [provider] if provider else list(PROVIDERS)
            checklist = []
            for name in providers:
                spec = PROVIDERS.get(name)
                if not spec:
                    continue
                credential_present = bool(os.getenv(spec["env"])) or self.token_store.has(name)
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
                account["credential_present"] = bool(env and os.getenv(env)) or self.token_store.has(account.get("provider", ""))
                account["status"] = "ready" if account["credential_present"] else "awaiting_credentials"
            self._save(data)
            return AccountResult(True, {"accounts": data["accounts"]})
        return AccountResult(False, {}, f"Unsupported social-accounts action: {action}")
