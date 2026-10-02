import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oth.core.secure_tokens import SecureTokenStore
from oth.core.social_actions import SocialActionBus

@dataclass
class SocialAnalyticsResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class SocialAnalytics:
    id = "social-analytics"

    def __init__(self, root: str | Path, requester=None):
        self.root = Path(root)
        self.path = self.root / "data" / "social_metrics.json"
        self.queue = self.root / "data" / "social_queue.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.actions = SocialActionBus(self.root, requester=requester)

    def supports(self, capability: str) -> bool:
        return capability == "social-analytics"

    def _read(self, path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _save(self, data):
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _token(self, provider):
        spec = self.actions._spec(provider)
        return self.actions._token(provider, spec) if spec else None

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _fetch_youtube(self, video_id: str):
        token = self._token("youtube")
        if not token:
            return SocialAnalyticsResult(True, {
                "provider": "youtube",
                "status": "awaiting_credentials",
                "live": False,
            })
        query = urllib.parse.urlencode({"part": "snippet,statistics,status", "id": video_id})
        url = f"https://www.googleapis.com/youtube/v3/videos?{query}"
        try:
            status, data = self.actions.requester("GET", url, token)
        except Exception as exc:
            return SocialAnalyticsResult(False, {}, f"Network error: {exc}", retryable=True)
        if not 200 <= status < 300:
            return SocialAnalyticsResult(False, {"http_status": status},
                                         "YouTube metrics request was rejected")
        items = data.get("items", [])
        if not items:
            return SocialAnalyticsResult(False, {}, "YouTube video was not found")
        raw = items[0]
        stats = raw.get("statistics", {})
        views = int(stats.get("viewCount", 0) or 0)
        likes = int(stats.get("likeCount", 0) or 0)
        comments = int(stats.get("commentCount", 0) or 0)
        return SocialAnalyticsResult(True, {
            "provider": "youtube",
            "external_id": video_id,
            "metrics": {
                "impressions": views,
                "views": views,
                "engagements": likes + comments,
                "likes": likes,
                "comments": comments,
            },
            "raw": raw,
        })
    def _linkedin_metric(self, entity: str, metric: str):
        token = self._token("linkedin")
        if not token:
            return None, "awaiting_credentials"
        spec = self.actions._spec("linkedin")
        version = spec.get("default_version", "202608")
        query = urllib.parse.urlencode({
            "q": "entity",
            "entity": entity,
            "queryType": metric,
            "aggregation": "TOTAL",
        })
        url = f"https://api.linkedin.com/rest/memberCreatorPostAnalytics?{query}"
        headers = {
            "Linkedin-Version": version,
            "X-Restli-Protocol-Version": "2.0.0",
        }
        try:
            status, data = self.actions.requester("GET", url, token, headers)
        except Exception as exc:
            return None, f"network:{exc}"
        if not 200 <= status < 300:
            return None, f"http_{status}"
        return data, None

    @staticmethod
    def _extract_linkedin_value(payload):
        elements = payload.get("elements", []) if isinstance(payload, dict) else []
        for element in elements:
            if not isinstance(element, dict):
                continue
            for key in ("value", "count"):
                value = element.get(key)
                if isinstance(value, (int, float)):
                    return value
            total = element.get("total")
            if isinstance(total, dict):
                value = total.get("value")
                if isinstance(value, (int, float)):
                    return value
        return 0

    def _fetch_linkedin(self, post_id: str):
        metrics = {}
        errors = {}
        requested = ["IMPRESSION", "MEMBERS_REACHED", "RESHARE", "REACTION", "COMMENT"]
        for metric in requested:
            data, error = self._linkedin_metric(post_id, metric)
            if error:
                errors[metric] = error
                continue
            key = {
                "IMPRESSION": "impressions",
                "MEMBERS_REACHED": "reach",
                "RESHARE": "shares",
                "REACTION": "reactions",
                "COMMENT": "comments",
            }[metric]
            metrics[key] = self._extract_linkedin_value(data)
        if not metrics and "awaiting_credentials" in errors.values():
            return SocialAnalyticsResult(True, {
                "provider": "linkedin",
                "status": "awaiting_credentials",
                "live": False,
            })
        if not metrics and errors:
            return SocialAnalyticsResult(False, {"errors": errors},
                                         "LinkedIn analytics request failed")
        metrics["engagements"] = (
            metrics.get("shares", 0)
            + metrics.get("reactions", 0)
            + metrics.get("comments", 0)
        )
        return SocialAnalyticsResult(True, {
            "provider": "linkedin",
            "external_id": post_id,
            "metrics": metrics,
            "errors": errors,
        })

    def _store_metric(self, content_id, platform, external_id, result):
        data = self._read(self.path, {"items": []})
        record = {
            "content_id": content_id,
            "platform": platform,
            "external_id": external_id,
            "fetched_at": self._now(),
            **result.output,
        }
        data["items"].append(record)
        data["items"] = [
            item for item in data["items"]
            if not (
                item.get("content_id") == content_id
                and item.get("external_id") == external_id
                and item is not record
            )
        ]
        self._save(data)
        return record
    def _published_items(self):
        data = self._read(self.queue, {"items": []})
        rows = []
        for item in data.get("items", []):
            if item.get("status") != "published":
                continue
            response = item.get("external_response") or {}
            external_id = response.get("id") or response.get("video_id")
            if external_id:
                rows.append({
                    "content_id": item.get("content_id"),
                    "campaign_id": item.get("campaign_id"),
                    "platform": item.get("platform"),
                    "external_id": external_id,
                    "payload": item.get("payload", {}),
                })
        return rows

    def _fetch_one(self, item):
        platform = str(item.get("platform", "")).lower()
        external_id = str(item.get("external_id", "")).strip()
        if platform == "youtube":
            return self._fetch_youtube(external_id)
        if platform == "linkedin":
            return self._fetch_linkedin(external_id)
        return SocialAnalyticsResult(True, {
            "provider": platform,
            "status": "capability_unavailable",
            "live": False,
        })

    def execute(self, action: str, payload: dict) -> SocialAnalyticsResult:
        source = payload.get("input", {})
        if action == "list":
            return SocialAnalyticsResult(True, {
                "items": self._read(self.path, {"items": []}).get("items", [])
            })

        if action == "record":
            content_id = str(source.get("content_id", "")).strip()
            platform = str(source.get("platform", "")).strip().lower()
            if not content_id or not platform:
                return SocialAnalyticsResult(False, {}, "content_id and platform are required")
            record = self._store_metric(
                content_id,
                platform,
                str(source.get("external_id", "")),
                SocialAnalyticsResult(True, {
                    "metrics": source.get("metrics", {}),
                    "status": "manual_record",
                }),
            )
            return SocialAnalyticsResult(True, {"record": record})

        if action == "fetch":
            item = {
                "content_id": str(source.get("content_id", "")),
                "campaign_id": str(source.get("campaign_id", "")),
                "platform": str(source.get("platform", "")).lower(),
                "external_id": str(source.get("external_id", "")),
                "payload": source.get("payload", {}),
            }
            if not item["external_id"]:
                return SocialAnalyticsResult(False, {}, "external_id is required")
            result = self._fetch_one(item)
            if not result.success or result.output.get("status") in {"awaiting_credentials", "capability_unavailable"}:
                return result
            record = self._store_metric(
                item["content_id"],
                item["platform"],
                item["external_id"],
                result,
            )
            metrics = result.output.get("metrics", {})
            return SocialAnalyticsResult(True, {
                "record": record,
                "next": [{
                    "capability": "social-optimization",
                    "action": "record",
                    "priority": 64,
                    "payload": {
                        "input": {
                            "platform": item["platform"],
                            "content_id": item["content_id"],
                            "format": item["payload"].get("format", ""),
                            "pillar": "acquisition",
                            "metrics": metrics,
                        }
                    }
                }],
            })

        if action == "sync":
            results = []
            handoffs = []
            for item in self._published_items():
                result = self._fetch_one(item)
                results.append({
                    "content_id": item.get("content_id"),
                    "platform": item.get("platform"),
                    "external_id": item.get("external_id"),
                    **result.output,
                    "error": result.error,
                })
                if result.success and result.output.get("metrics"):
                    record = self._store_metric(
                        item.get("content_id"),
                        item.get("platform"),
                        item.get("external_id"),
                        result,
                    )
                    handoffs.append({
                        "capability": "social-optimization",
                        "action": "record",
                        "priority": 64,
                        "payload": {
                            "input": {
                                "platform": item.get("platform"),
                                "content_id": item.get("content_id"),
                                "format": item.get("payload", {}).get("format", ""),
                                "pillar": "acquisition",
                                "metrics": record.get("metrics", {}),
                            }
                        },
                    })
            return SocialAnalyticsResult(True, {
                "results": results,
                "synced": len(results),
                "next": handoffs,
            })

        return SocialAnalyticsResult(False, {}, f"Unsupported social-analytics action: {action}")
