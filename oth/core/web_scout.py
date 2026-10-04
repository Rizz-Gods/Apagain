from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from subprocess import run, TimeoutExpired
from urllib.parse import parse_qs, quote_plus, unquote, urlparse


@dataclass
class WebScoutResult:
    success: bool
    output: dict
    error: str | None = None
    retryable: bool = False


class WebScoutHTTPWorker:
    """Scout lane using direct HTTPS instead of the browser automation transport."""

    id = "scout-http"

    def __init__(self, agent=None):
        self.timeout = int((agent.metadata if agent else {}).get("timeout", 30))
        self.command = str((agent.metadata if agent else {}).get("command", "curl.exe"))

    def supports(self, capability: str) -> bool:
        return capability in {"scout", "research"}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _classify(query: str) -> str:
        q = query.lower()
        if any(x in q for x in ("complaint", "problem", "sucks", "pain point")):
            return "complaint"
        if any(x in q for x in ("alternative", "competitor", "vs")):
            return "alternative"
        if any(x in q for x in ("how to", "manual", "spreadsheet", "template")):
            return "friction"
        if any(x in q for x in ("review", "negative")):
            return "review"
        return "demand"

    @staticmethod
    def _decode(value: str) -> str:
        return unescape(re.sub(r"<[^>]+>", " ", value)).strip()

    @staticmethod
    def _quality(query: str, title: str, snippet: str, url: str) -> float:
        hay = f"{title} {snippet}".lower()
        domain = re.sub(r"^https?://", "", url).split("/")[0].lower()
        blocked = ("wikipedia.org", "wikimedia.org", "cambridge.org", "merriam-webster.com", "dictionary.com")
        if any(domain.endswith(x) for x in blocked):
            return 0.0
        signal_terms = (
            "manual", "spreadsheet", "complaint", "expensive", "alternative",
            "problem", "problems", "frustrat", "scheduling", "invoicing",
            "follow", "lead", "booking", "workflow", "owner", "owners"
        )
        hits = sum(1 for term in signal_terms if term in hay)
        query_terms = {
            token for token in re.findall(r"[a-z0-9]{4,}", query.lower())
            if token not in {"what", "with", "from", "into", "software"}
        }
        overlap = sum(1 for token in query_terms if token in hay)
        candidate_terms = ("software", "platform", "service", "app", "tool", "scheduling", "booking")
        if overlap >= 2 and (hits or any(term in hay for term in candidate_terms)):
            return 0.65
        if overlap >= 1 and hits >= 2:
            return 0.5
        return 0.0

    @staticmethod
    def _target_url(url: str) -> str:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        raw = params.get("u", [None])[0]
        if not raw:
            return url
        try:
            token = raw[2:] if raw.startswith("a1") else raw
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8", "ignore")
            if decoded.startswith(("http://", "https://")):
                return decoded
        except Exception:
            pass
        return url

    def _search(self, query: str) -> str:
        url = "https://www.bing.com/search?q=" + quote_plus(query)
        proc = run(
            [self.command, "-L", "-sS", "--max-time", str(self.timeout),
             "-A", "Mozilla/5.0", url],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=self.timeout + 5, check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"curl exit_code={proc.returncode}")
        return proc.stdout

    def _extract(self, query: str, raw: str) -> list[dict]:
        results = []
        blocks = re.findall(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', raw, re.I | re.S)
        for block in blocks:
            match = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.I | re.S)
            if not match:
                continue
            url = self._target_url(unquote(unescape(match.group(1))).strip())
            title = self._decode(match.group(2))
            snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.I | re.S)
            snippet = self._decode(snippet_match.group(1)) if snippet_match else ""
            if not url.startswith(("http://", "https://")) or not title:
                continue
            quality = self._quality(query, title, snippet, url)
            if quality < 0.5:
                continue
            results.append({
                "source": "bing-http",
                "query": query,
                "title": title[:180],
                "url": url,
                "snippet": snippet[:600],
                "signal_type": self._classify(query),
                "quality": quality,
                "raw": raw[:8000],
                "discovered_at": self._now(),
            })
            if len(results) >= 10:
                break
        return results

    def execute(self, action: str, payload: dict) -> WebScoutResult:
        if action not in {"scan", "prompt"}:
            return WebScoutResult(False, {}, f"Unsupported scout-http action: {action}")
        if action == "prompt":
            prompt = str(payload.get("prompt", "")).strip()
            if not prompt:
                return WebScoutResult(False, {}, "Missing research prompt")
            queries = [prompt, f"{prompt} official", f"{prompt} discussion"]
        else:
            queries = payload.get("queries") or []
        if not isinstance(queries, list) or not queries:
            return WebScoutResult(False, {}, "queries must be a non-empty list")
        signals = []
        try:
            for query in queries[:8]:
                signals.extend(self._extract(str(query), self._search(str(query))))
            dedup = {(x["url"], x["query"]): x for x in signals}
            output = {
                "signals": list(dedup.values())[:40],
                "count": len(dedup),
                "transport": "https",
            }
            if action == "prompt":
                output["fallback"] = True
                output["fallback_reason"] = "external_research_unavailable"
                output["response"] = "Web evidence collected; synthesize from returned signals."
            return WebScoutResult(True, output)
        except TimeoutExpired as exc:
            return WebScoutResult(False, {"signals": signals}, str(exc), retryable=True)
        except Exception as exc:
            text = str(exc)
            retryable = any(x in text.lower() for x in ("timeout", "connection", "429", "502", "503", "504"))
            return WebScoutResult(False, {"signals": signals}, text, retryable=retryable)


__all__ = ["WebScoutHTTPWorker", "WebScoutResult"]
