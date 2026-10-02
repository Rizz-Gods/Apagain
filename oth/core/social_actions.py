import http.client
import json
import mimetypes
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

    def __init__(self, root=None, requester=None, video_uploader=None):
        self.root = Path(root) if root else None
        self.requester = requester or self._request
        self.video_uploader = video_uploader or self._upload_youtube_resumable
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
                "local_capabilities": ["draft", "adapt", "prepare", "queue", "metadata", "video"],
                "live_capabilities": ["health", "metadata", "publish_video"],
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

    def _stored_actor(self, provider: str):
        if not self.root:
            return None
        path = self.root / "data" / "social_accounts.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        account = next((a for a in data.get("accounts", []) if a.get("provider") == provider), None)
        return ((account or {}).get("identity") or {}).get("actor")

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
            actor = actor or os.getenv("OTH_SOCIAL_LINKEDIN_ACTOR") or self._stored_actor("linkedin")
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

    def _resolve_media_path(self, media_ref: str) -> Path:
        if not self.root:
            raise ValueError("media publishing requires an OTH workspace root")
        path = Path(str(media_ref)).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        root = self.root.resolve()
        if not path.is_relative_to(root):
            raise ValueError("media_ref must resolve inside the OTH workspace")
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return path

    def _upload_youtube_resumable(self, token: str, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        size = file_path.stat().st_size
        mime_type = mimetypes.guess_type(file_path.name)[0] or "video/mp4"
        body = json.dumps(metadata).encode("utf-8")
        start_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        request = Request(
            start_url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(size),
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            location = response.headers.get("Location")
            if response.status not in {200, 201} or not location:
                raise RuntimeError(f"YouTube upload session could not be created: HTTP {response.status}")

        parsed = urllib.parse.urlsplit(location)
        connection = http.client.HTTPSConnection(parsed.netloc, timeout=120)
        try:
            target = parsed.path or "/"
            if parsed.query:
                target = f"{target}?{parsed.query}"
            connection.putrequest("PUT", target)
            connection.putheader("Authorization", f"Bearer {token}")
            connection.putheader("Content-Type", mime_type)
            connection.putheader("Content-Length", str(size))
            connection.endheaders()
            with file_path.open("rb") as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    connection.send(chunk)
            response = connection.getresponse()
            raw = response.read().decode("utf-8", errors="replace")
            if not 200 <= response.status < 300:
                raise RuntimeError(f"YouTube upload rejected: HTTP {response.status} {raw[:500]}")
            return json.loads(raw) if raw else {}
        finally:
            connection.close()

    def _publish_youtube_video(self, source: dict[str, Any]) -> SocialActionResult:
        provider = "youtube"
        spec = self._spec(provider)
        media_ref = str(source.get("media_ref", "")).strip()
        title = str(source.get("title", "")).strip()
        description = str(source.get("description", "")).strip()
        privacy_status = str(source.get("privacy_status", "private")).lower().strip()
        content_id = source.get("content_id")
        if not media_ref:
            return SocialActionResult(False, {}, "YouTube publishing requires media_ref")
        if not title:
            return SocialActionResult(False, {}, "YouTube publishing requires title")
        if privacy_status not in {"private", "unlisted", "public"}:
            return SocialActionResult(False, {}, "privacy_status must be private, unlisted, or public")
        token = self._token(provider, spec)
        if not token:
            self._update_queue(content_id, "waiting_credentials", last_error="missing_credentials")
            return SocialActionResult(True, {
                "provider": provider,
                "status": "awaiting_credentials",
                "action": "publish_video",
            })
        try:
            media_path = self._resolve_media_path(media_ref)
            metadata = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "categoryId": str(source.get("category_id", "22")),
                },
                "status": {
                    "privacyStatus": privacy_status,
                },
            }
            response = self.video_uploader(token, media_path, metadata)
        except FileNotFoundError as exc:
            self._update_queue(content_id, "failed", last_error="media_not_found")
            return SocialActionResult(False, {}, f"Media file not found: {exc}")
        except (ValueError, OSError, RuntimeError) as exc:
            self._update_queue(content_id, "failed", last_error="youtube_upload_error")
            return SocialActionResult(False, {}, str(exc), retryable=False)
        except Exception as exc:
            self._update_queue(content_id, "dispatching", last_error=f"youtube_network_error:{exc}")
            return SocialActionResult(False, {}, f"YouTube upload failed: {exc}", retryable=True)
        self._update_queue(content_id, "published", external_response=response, last_error=None)
        return SocialActionResult(True, {
            "provider": provider,
            "status": "published",
            "action": "publish_video",
            "video_id": response.get("id"),
            "response": response,
        })

    def _prepare_publish(self, provider: str, source: dict[str, Any]) -> SocialActionResult:
        limits = {
            "linkedin": {"text": 3000, "media": True, "adapter": "live_text"},
            "x": {"text": 280, "media": True, "adapter": "live_text"},
            "youtube": {"text": 5000, "media": True, "adapter": "live_video"},
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
            "live_action_available": (spec["adapter"] == "live_text" and provider in {"linkedin", "x"}) or (spec["adapter"] == "live_video" and provider == "youtube" and bool(source.get("media_ref"))),
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
        if action == "publish_video":
            if provider != "youtube":
                return SocialActionResult(False, {}, "Video publishing is currently implemented for YouTube only")
            return self._publish_youtube_video(source)
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
