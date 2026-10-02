import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from .scout import ScoutWorker

@dataclass
class ReviewMinerResult:
    success: bool
    output: dict[str, Any]
    error: str | None = None
    retryable: bool = False

class ReviewMiner(ScoutWorker):
    id = "review-miner"

    REVIEW_DOMAINS = {
        "reddit.com",
        "trustpilot.com",
        "g2.com",
        "capterra.com",
        "producthunt.com",
        "appsumo.com",
        "getapp.com",
        "softwareadvice.com",
    }

    def supports(self, capability: str) -> bool:
        return capability == "review-mining"

    @staticmethod
    def _candidate_name(signal: dict) -> str:
        title = re.sub(r"^#+\s*", "", str(signal.get("title", ""))).strip()
        title = title.split("|")[0].strip()
        title = re.sub(
            r"\b(best|free|online|software|platform|app|tool|reviews?)\b",
            "",
            title,
            flags=re.I,
        )
        return re.sub(r"\s+", " ", title).strip()[:100]

    def _quality(self, url: str, title: str, snippet: str) -> float:
        domain = re.sub(r"^https?://", "", url).split("/")[0].lower()
        if not any(domain.endswith(d) for d in self.REVIEW_DOMAINS):
            return 0.0
        hay = f"{title} {snippet}".lower()
        pain = (
            "complaint", "problem", "issue", "expensive", "slow",
            "bad", "missing", "difficult", "frustrat", "alternative",
            "negative", "review", "rating"
        )
        hits = sum(1 for token in pain if token in hay)
        return min(1.0, 0.4 + hits * 0.1) if hits else 0.35

    def _search_review(self, name: str) -> str:
        query = f'"{name}" complaints reviews alternative'
        return self._search(query)

    def _extract_review_signals(self, query: str, raw: str, candidate: dict) -> list[dict]:
        lines = [x.strip() for x in raw.splitlines() if x.strip()]
        out = []
        current_url = None
        for i, line in enumerate(lines):
            if line.startswith("http://") or line.startswith("https://"):
                if "bing.com/search" not in line:
                    current_url = line.split()[0]
                continue
            if not current_url or i + 1 >= len(lines):
                continue
            snippet = lines[i + 1]
            if len(line) > 180 or snippet.startswith("http"):
                continue
            quality = self._quality(current_url, line, snippet)
            if quality <= 0:
                current_url = None
                continue
            out.append({
                "source": "bing-review",
                "query": query,
                "title": line,
                "url": current_url,
                "snippet": snippet[:600],
                "signal_type": "review",
                "quality": quality,
                "candidate": candidate.get("name"),
                "candidate_url": candidate.get("url"),
                "raw": raw[:8000],
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            })
            current_url = None
            if len(out) >= 8:
                break
        return out

    def execute(self, action: str, payload: dict) -> ReviewMinerResult:
        if action != "mine":
            return ReviewMinerResult(False, {}, f"Unsupported review-mining action: {action}")
        candidates = payload.get("input", {}).get("signals", [])
        if not isinstance(candidates, list):
            return ReviewMinerResult(False, {}, "input.signals must be a list")
        signals = []
        seen = set()
        try:
            for source_signal in candidates[:6]:
                name = self._candidate_name(source_signal)
                if not name:
                    continue
                raw = self._search_review(name)
                for signal in self._extract_review_signals(
                    f'"{name}" complaints reviews alternative', raw, {
                        "name": name, "url": source_signal.get("url")
                    }
                ):
                    key = (signal["url"], signal["candidate"])
                    if key in seen:
                        continue
                    seen.add(key)
                    signals.append(signal)
            return ReviewMinerResult(True, {
                "signals": signals[:30],
                "count": len(signals),
                "candidates_scanned": min(len(candidates), 6),
                "next": [{"capability": "opportunity-analysis", "action": "score", "priority": 65}],
            })
        except Exception as exc:
            msg = str(exc)
            retryable = any(x in msg.lower() for x in ("timeout", "connection", "502", "503", "429"))
            return ReviewMinerResult(
                False, {"signals": signals}, msg, retryable=retryable
            )
