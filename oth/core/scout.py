import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

@dataclass
class ScoutResult:
    success: bool
    output: dict
    error: str | None = None
    retryable: bool = False

class ScoutWorker:
    id = "scout"
    BLOCKED_DOMAINS = {
        "wikipedia.org", "wikimedia.org", "cambridge.org",
        "merriam-webster.com", "dictionary.com", "geeksforgeeks.org",
        "smallpdf.com", "britannica.com"
    }

    def __init__(self, agent=None):
        self.session = (agent.metadata.get("session", "oth-scout")
                        if agent else "oth-scout")
        self.command = (agent.metadata.get("command", "agent-browser.cmd")
                        if agent else "agent-browser.cmd")

    def supports(self, capability: str) -> bool:
        return capability == "scout"

    @staticmethod
    def _now():
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

    def _search(self, query: str) -> str:
        url = "https://www.bing.com/search?q=" + quote_plus(query)
        proc = subprocess.run(
            [self.command, "--session", self.session,
             "--idle-timeout", "10s", "batch",
             f"open {url}", "read", "close"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=45, check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            raise RuntimeError(err or "browser batch failed")
        return (proc.stdout or "").strip()

    def _quality(self, query: str, title: str, snippet: str, url: str) -> float:
        q = query.lower()
        hay = f"{title} {snippet}".lower()
        domain = re.sub(r"^https?://", "", url).split("/")[0].lower()
        if any(domain.endswith(d) for d in self.BLOCKED_DOMAINS):
            return 0.0
        if "site:reddit.com" in q and "reddit.com" not in domain:
            return 0.0
        signal_terms = {
            "manual", "spreadsheet", "spreadsheets", "complaint",
            "complaints", "expensive", "alternative", "problem",
            "problems", "frustrat", "scheduling", "invoicing",
            "follow", "lead", "booking", "workflow", "owner", "owners"
        }
        hits = sum(1 for t in signal_terms if t in hay)
        if "reddit.com" in q:
            return 1.0 if "reddit.com" in domain else 0.0
        candidate_terms = ("software", "platform", "service", "app", "tool", "scheduling", "booking")
        if any(t in hay for t in candidate_terms):
            return 0.65
        if hits >= 1:
            return 0.5
        return 0.0

    def _extract(self, query: str, raw: str) -> list[dict]:
        lines = [x.strip() for x in raw.splitlines() if x.strip()]
        results = []
        current_url = None
        current_title = None
        for i, line in enumerate(lines):
            if line.startswith("http://") or line.startswith("https://"):
                if "bing.com/search" not in line:
                    current_url = line.split()[0]
                continue
            if current_url and i + 1 < len(lines):
                nxt = lines[i + 1]
                if len(line) <= 180 and not nxt.startswith("http"):
                    current_title = line
                    snippet = nxt[:600]
                    quality = self._quality(query, current_title, snippet, current_url)
                    if quality >= 0.5:
                        results.append({
                            "source": "bing",
                            "query": query,
                            "title": current_title,
                            "url": current_url,
                            "snippet": snippet,
                            "signal_type": self._classify(query),
                            "quality": quality,
                            "raw": raw[:8000],
                            "discovered_at": self._now(),
                        })
                    current_url = None
                    current_title = None
                    if len(results) >= 10:
                        break
        return results

    def execute(self, action: str, payload: dict) -> ScoutResult:
        if action != "scan":
            return ScoutResult(False, {}, f"Unsupported scout action: {action}")
        queries = payload.get("queries") or []
        if not isinstance(queries, list) or not queries:
            return ScoutResult(False, {}, "queries must be a non-empty list")
        all_signals = []
        try:
            for query in queries[:8]:
                raw = self._search(str(query))
                all_signals.extend(self._extract(str(query), raw))
            dedup = {}
            for signal in all_signals:
                dedup[(signal["url"], signal["query"])] = signal
            signals = list(dedup.values())[:40]
            return ScoutResult(True, {"signals": signals, "count": len(signals)})
        except subprocess.TimeoutExpired as exc:
            return ScoutResult(False, {"signals": all_signals}, str(exc), retryable=True)
        except Exception as exc:
            msg = str(exc)
            retryable = any(x in msg.lower() for x in ("timeout", "connection", "503", "502", "429"))
            return ScoutResult(False, {"signals": all_signals}, msg, retryable=retryable)
