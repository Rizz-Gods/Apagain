from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class Task:
    id: str
    capability: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    status: str = "queued"
    created_at: str = field(default_factory=now_iso)

@dataclass
class Agent:
    id: str
    name: str
    capabilities: list[str]
    status: str = "offline"
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class Skill:
    id: str
    name: str
    version: str
    capabilities: list[str]
