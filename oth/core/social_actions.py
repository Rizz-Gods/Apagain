import json
import os
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from oth.core.secure_tokens import SecureTokenStore

@dataclass
class SocialActionResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialActionBus:
    id = "social-actions"

    def __init__(self, root=None, requester=None):
        self.root = Path(root) if root else None
        self.requester = requester or self._request
        self.token_store = SecureTokenStore(root) if root else None
        self.specs = {
            "linkedin": {
                "token_env": "OTH_SOCIAL_LINKEDIN_TOKEN",
                "health_url": "https://api.linkedin.com/v2/userinfo",
                "publish_url": "https://api.linkedin.com/rest/posts",
                "version_env": "OTH_LINKEDIN_API_VERSION",
                "default_version": "202608",
                "local_capabilities": ["draft", "adapt", "prepare", "queue"],
                "live_capabilities": ["publish_text", "health"],
            },
            "youtube": {
                "token_env": "OTH_SOCIAL_YOUTUBE_TOKEN",
                "health_url": "https://www.googleapis.com/youtube/v3/channels?part=snippet%2Cstatistics&mine=true",
                "local_capabilities": ["draft", "adapt", "prepare", "queue", "metadata"],
                "live_capabilities": ["health", "metadata"],
            },
            "x": {
                "token_env": "OTH_SOCIAL_X_TOKEN",
                "health_url": "https://api.x.com/2/users/me",
                "publish_url": "https://api.x.com/2/tweets",
                "local_capabilities": ["draft", "adapt", "prepare", "queue"],
                "live_capabilities": ["publish_text", "health"],
            },
            "instagram": {
                "token_env": "OTH_SOCIAL_INSTAGRAM_TOKEN",
                "local_capabilities": ["draft", "adapt", "prepare", "queue", "media_brief"],
                "live_capabilities": ["health"],
            },
        }

    def supports(self, capability: str) -> bool:
        return capability == "social-actions"

    @staticmethod
    def _request(method, url, token, headers=None, body=None):
        hdrs = {"Authorization": f"Bearer {token}"}
        hdrs.update(headers or {})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(url, data=data, headers=hdrs, method=method)
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}

    def _spec(self, provider):
        return self.specs.get(str(provider).lower())

    def _refresh_youtube(self, stored: dict[str, Any]) -> str | None:
        refresh_token = stored.get("refresh_token")
        client_id = os.getenv("OTH_SOCIAL_YOUTUBE_CLIENT_ID")
        client_secret = os.getenv("OTH_SOCIAL_YOUTUBE_CLIENT_SECRET")
        if not refresh_token or not client_id:
            return None
        form = urllib.parse.urlencode({
            "client_id": client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        if client_secret:
            form = urllib.parse.urlencode({
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
        request = Request(
            "https://oauth2.googleapis.com/token",
            data=form.encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            token = payload.get("access_token")
            if not token or not self.token_store:
                return None
            stored["access_token"] = token
            stored["expires_at"] = time.time() + int(payload.get("expires_in", 3600))
            self.token_store.set("youtube", stored)
            return token
        except Exception:
            return None

    def _token(self, provider, spec):
        if not spec:
            return None
        if self.token_store:
            stored = self.token_store.get(provider)
            if stored:
                expires_at = float(stored.get("expires_at", 0) or 0)
                token = stored.get("access_token")
                if token and (not expires_at or expires_at > time.time() + 30):
                    return token
                if provider == "youtube":
                    refreshed = self._refresh_youtube(stored)
                    if refreshed:
                        return refreshed
        return os.getenv(spec["token_env"])

    def _health(self, provider):
        spec = self._spec(provider)
        if not spec:
            return SocialActionResult(False, {}, f"Unsupported social provider: {provider}")
        token = self._token(provider, spec)
        if not token:
            return SocialActionResult(True, {
                "provider": provider,
                "status": "awaiting_credentials",
                "live": False,
                "reason": f"Missing {spec['token_env']}",
            })
        if "health_url" not in spec:
            return SocialActionResult(True, {
                "provider": provider,
                "status": "credential_present",
                "live": False,
                "reason": "Provider requires additional account metadata before a safe API probe",
            })
        headers = {}
        if provider == "linkedin":
            headers["Linkedin-Version"] = os.getenv(
                spec["version_env"], spec["default_version"]
            )
            headers["X-Restli-Protocol-Version"] = "2.0.0"
        try:
            status, data = self.requester("GET", spec["health_url"], token, headers)
            return SocialActionResult(True, {
                "provider": provider,
                "status": "healthy" if 200 <= status < 300 else "unhealthy",
                "http_status": status,
                "identity": data,
            })
        except HTTPError as exc:
            return SocialActionResult(True, {
                "provider": provider,
                "status": "permission_or_api_error",
                "http_status": exc.code,
                "reason": "Credential exists but the requested API capability is unavailable",
            })
        except URLError as exc:
            return SocialActionResult(False, {}, f"Network error: {exc}", retryable=True)

    def _update_queue(self, content_id: str | None, status: str, **extra):
        if not self.root or not content_id:
            return
        path = self.root / "data" / "social_queue.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data.get("items", []):
                if item.get("content_id") == content_id or item.get("id") == content_id:
                    item["status"] = status
                    item["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    item.update(extra)
                    break
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            return

    def _publish_text(self, provider, text, actor=None, content_id=None):
        spec = self._spec(provider)
        if not spec or "publish_url" not in spec:
            return SocialActionResult(False, {}, f"Text publishing is not implemented for {provider}")
        token = self._token(provider, spec)
        if not token:
            self._update_queue(content_id, "waiting_credentials", last_error="missing_credentials")
            return SocialActionResult(True, {
                "provider": provider,
                "status": "awaiting_credentials",
                "action": "publish_text",
            })
        if provider == "linkedin":
            actor = actor or os.getenv("OTH_SOCIAL_LINKEDIN_ACTOR")
            if not actor:
                return SocialActionResult(False, {}, "LinkedIn publish requires OTH_SOCIAL_LINKEDIN_ACTOR")
            body = {
                "author": actor,
                "commentary": text,
                "visibility": "PUBLIC",
                "distribution": {"feedDistribution": "MAIN_FEED"},
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }
            headers = {
                "Linkedin-Version": os.getenv(
                    spec["version_env"], spec["default_version"]
                ),
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            }
        else:
            body = {"text": text}
            headers = {"Content-Type": "application/json"}
        try:
            status, data = self.requester(
                "POST", spec["publish_url"], token, headers, body
            )
            published = 200 <= status < 300
            self._update_queue(
                content_id,
                "published" if published else "failed",
                external_response=data if published else None,
                last_error=None if published else "provider_rejected",
            )
            return SocialActionResult(True, {
                "provider": provider,
                "status": "published" if published else "rejected",
                "http_status": status,
                "response": data,
            })
        except HTTPError as exc:
            self._update_queue(content_id, "failed", last_error=f"provider_http_{exc.code}")
            return SocialActionResult(True, {
                "provider": provider,
                "status": "permission_or_validation_error",
                "http_status": exc.code,
                "reason": "Provider rejected the live action",
            })
        except URLError as exc:
            self._update_queue(content_id, "dispatching", last_error=f"network_error:{exc}")
            return SocialActionResult(False, {}, f"Network error: {exc}", retryable=True)

    def _prepare_publish(self, provider: str, source: dict[str, Any]) -> SocialActionResult:
        limits = {
            "linkedin": {"text": 3000, "media": True, "adapter": "live_text"},
            "x": {"text": 280, "media": True, "adapter": "live_text"},
            "youtube": {"text": 5000, "media": True, "adapter": "metadata_only"},
            "instagram": {"text": 2200, "media": True, "adapter": "queued_media"},
        }
        spec = limits.get(provider)
        if not spec:
            return SocialActionResult(False, {}, f"Unsupported social provider: {provider}")
        text = str(source.get("text", "")).strip()
        if len(text) > spec["text"]:
            return SocialActionResult(False, {}, f"Text exceeds the {provider} preparation limit")
        media_required = bool(source.get("media_required", False))
        ready = bool(text) and (not media_required or bool(source.get("media_ref")))
        return SocialActionResult(True, {
            "provider": provider,
            "status": "ready_for_approval" if ready else "needs_input",
            "adapter": spec["adapter"],
            "payload": {
                "text": text,
                "media_ref": source.get("media_ref"),
                "title": source.get("title"),
                "description": source.get("description"),
            },
            "requirements": {
                "approval": "external",
                "media_required": media_required,
                "media_present": bool(source.get("media_ref")),
                "credential_required_for_live": True,
            },
            "live_action_available": spec["adapter"] == "live_text" and provider in {"linkedin", "x"},
        })

    def execute(self, action: str, payload: dict) -> SocialActionResult:
        source = payload.get("input", {})
        provider = str(source.get("provider", "")).lower()
        if action == "prepare_publish":
            return self._prepare_publish(provider, source)
        if action == "health":
            return self._health(provider)
        if action == "publish_text":
            text = str(source.get("text", "")).strip()
            if not text:
                return SocialActionResult(False, {}, "text is required")
            if len(text) > 30000:
                return SocialActionResult(False, {}, "text exceeds safety limit")
            return self._publish_text(
                provider, text, source.get("actor"), source.get("content_id")
            )
        if action == "doctor":
            providers = [provider] if provider else list(self.specs)
            results = []
            for name in providers:
                result = self._health(name)
                results.append({
                    "provider": name,
                    "local_capabilities": self.specs[name].get("local_capabilities", []),
                    "live_capabilities": self.specs[name].get("live_capabilities", []),
                    "credential_required_for_live": True,
                    **result.output,
                    "error": result.error,
                })
            return SocialActionResult(True, {
                "providers": results,
                "policy": "No publish action is attempted by doctor; it only verifies readiness.",
            })
        return SocialActionResult(False, {}, f"Unsupported social action: {action}")
