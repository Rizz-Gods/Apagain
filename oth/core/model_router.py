from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelRoute:
    tier: str
    model: str
    complexity: float
    reason: str


class ModelRouter:
    """Choose an execution model by task complexity without coupling OTH to one vendor."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "config" / "model_routing.json"
        self.config = self._load()

    def _load(self) -> dict:
        default = {
            "models": {
                "local": {"provider": "ollama", "model": "qwen2.5-coder:0.5b-instruct-q5_1"},
                "standard": {"provider": "ollama", "model": "qwen2.5-coder:1.5b-instruct"},
                "strong": {"provider": "ollama", "model": "qwen2.5-coder:7b-instruct"},
                "frontier": {"provider": "", "model": ""},
            },
            "thresholds": {"standard": 0.32, "strong": 0.58, "frontier": 0.82},
        }
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else default
        except (OSError, ValueError):
            return default

    def _profile(self, tier: str) -> str:
        profile = self.config.get("models", {}).get(tier, {}) or {}
        provider = str(profile.get("provider", "")).strip()
        model = str(profile.get("model", "")).strip()
        if not provider or not model:
            return ""
        return f"{provider}/{model}"

    def complexity(self, task: str) -> float:
        text = task.lower()
        score = 0.10
        score += min(len(task) / 5000.0, 0.20)
        if re.search(r"\b(refactor|migrate|architect|integrate|concurrency|distributed|security|debug|race|performance)\b", text):
            score += 0.22
        if re.search(r"\b(build|implement|create|develop|modify|repair|fix)\b", text):
            score += 0.12
        if re.search(r"\b(database|api|browser|oauth|authentication|deployment|docker|kubernetes)\b", text):
            score += 0.14
        if text.count(" and ") >= 3:
            score += 0.08
        if text.count("/") + text.count("\\") >= 4:
            score += 0.04
        return round(min(score, 1.0), 4)

    def available_ollama_models(self) -> set[str]:
        if os.getenv("OTH_MODEL_BASE_URL"):
            base = os.getenv("OTH_MODEL_BASE_URL").rstrip("/")
        else:
            base = ""
        if not base:
            return set()
        try:
            req = urllib.request.Request(base.replace("/v1", "") + "/api/tags")
            with urllib.request.urlopen(req, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return {
                str(item.get("name", "")).strip()
                for item in payload.get("models", [])
                if item.get("name")
            }
        except Exception:
            return set()

    def route(self, task: str) -> ModelRoute:
        override = os.getenv("OTH_OPENCODE_MODEL", "").strip()
        complexity = self.complexity(task)
        if override:
            return ModelRoute("override", override, complexity, "operator model override")

        thresholds = self.config.get("thresholds", {}) or {}
        frontier = self._profile("frontier")
        strong = self._profile("strong")
        standard = self._profile("standard")
        local = self._profile("local")

        if complexity >= float(thresholds.get("frontier", 0.82)) and frontier:
            return ModelRoute("frontier", frontier, complexity, "high-complexity mission")
        if complexity >= float(thresholds.get("strong", 0.58)) and strong:
            return ModelRoute("strong", strong, complexity, "complex engineering mission")
        if complexity >= float(thresholds.get("standard", 0.32)) and standard:
            return ModelRoute("standard", standard, complexity, "moderate engineering mission")
        if local:
            return ModelRoute("local", local, complexity, "light engineering mission")
        return ModelRoute("unavailable", "", complexity, "no configured model route")
