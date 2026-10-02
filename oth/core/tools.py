import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class ToolInfo:
    id: str
    name: str
    executable: str | None
    available: bool
    capabilities: list[str]
    metadata: dict[str, Any]

class ToolRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.config = (
            json.loads(self.path.read_text(encoding="utf-8"))
            if self.path.exists() else {"tools": []}
        )

    def discover(self) -> list[ToolInfo]:
        tools = []
        for item in self.config.get("tools", []):
            exe = item.get("executable")
            found = shutil.which(exe) if exe else None
            tools.append(ToolInfo(
                id=item["id"],
                name=item["name"],
                executable=found,
                available=bool(found) if exe else bool(item.get("available", False)),
                capabilities=item.get("capabilities", []),
                metadata=item.get("metadata", {}),
            ))
        return tools
