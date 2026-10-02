import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

@dataclass
class SocialActionResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialActionBus:
    id = "social-actions"

    def __init__(self, root=None, requester=None):
        self.root = root
        self.requester = requester or self._request
        self.specs = {
            "linkedin": {
                "token_env": "OTH_SOCIAL_LINKEDIN_TOKEN",
                "health_url": "https://api.linkedin.com/v2/userinfo",
                "publish_url": "https://api.linkedin.com/rest/posts",
                "version_env": "OTH_LINKEDIN_API_VERSION",
                "default_version": "202608",
            },
            "youtube": {
                "token_env": "OTH_SOCIAL_YOUTUBE_TOKEN",
                "health_url": "https://www.googleapis.com/youtube/v3/channels?part=snippet%2Cstatistics&mine=true",
            },
            "x": {
                "token_env": "OTH_SOCIAL_X_TOKEN",
                "health_url": "https://api.x.com/2/users/me",
                "publish_url": "https://api.x.com/2/tweets",
            },
            "instagram": {
                "token_env": "OTH_SOCIAL_INSTAGRAM_TOKEN",
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

    def _token(self, spec):
        return os.getenv(spec["token_env"]) if spec else None

    def _health(self, provider):
        spec = self._spec(provider)
        if not spec:
            return SocialActionResult(False, {}, f"Unsupported social provider: {provider}")
        token = self._token(spec)
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

    def _publish_text(self, provider, text, actor=None):
        spec = self._spec(provider)
        if not spec or "publish_url" not in spec:
            return SocialActionResult(False, {}, f"Text publishing is not implemented for {provider}")
        token = self._token(spec)
        if not token:
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
            return SocialActionResult(True, {
                "provider": provider,
                "status": "published" if 200 <= status < 300 else "rejected",
                "http_status": status,
                "response": data,
            })
        except HTTPError as exc:
            return SocialActionResult(True, {
                "provider": provider,
                "status": "permission_or_validation_error",
                "http_status": exc.code,
                "reason": "Provider rejected the live action",
            })
        except URLError as exc:
            return SocialActionResult(False, {}, f"Network error: {exc}", retryable=True)

    def execute(self, action: str, payload: dict) -> SocialActionResult:
        source = payload.get("input", {})
        provider = str(source.get("provider", "")).lower()
        if action == "health":
            return self._health(provider)
        if action == "publish_text":
            text = str(source.get("text", "")).strip()
            if not text:
                return SocialActionResult(False, {}, "text is required")
            if len(text) > 30000:
                return SocialActionResult(False, {}, "text exceeds safety limit")
            return self._publish_text(
                provider, text, source.get("actor")
            )
        if action == "doctor":
            providers = [provider] if provider else list(self.specs)
            results = []
            for name in providers:
                result = self._health(name)
                results.append({
                    "provider": name,
                    **result.output,
                    "error": result.error,
                })
            return SocialActionResult(True, {
                "providers": results,
                "policy": "No publish action is attempted by doctor; it only verifies readiness.",
            })
        return SocialActionResult(False, {}, f"Unsupported social action: {action}")
