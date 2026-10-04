from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

READ_ONLY_MARKERS = (
    "inspect",
    "review",
    "analyze",
    "analyse",
    "status",
    "report",
    "diagnose",
    "list ",
    "show ",
    "explain",
    "check ",
    "verify ",
    "read-only",
    "read only",
)

MUTATION_MARKERS = (
    "add ",
    "build ",
    "create ",
    "develop ",
    "edit ",
    "fix ",
    "implement ",
    "integrate ",
    "modify ",
    "remove ",
    "refactor ",
    "repair ",
    "replace ",
    "update ",
    "write ",
)


def implementation_expected(action: str, task: str, payload: dict | None = None) -> bool:
    payload = payload or {}
    if payload.get("read_only") is True:
        return False
    if action not in {"execute", "build", "repair"}:
        return False
    text = str(task or "").strip().lower()
    if not text:
        return True
    if any(marker in text for marker in MUTATION_MARKERS):
        return True
    return not any(marker in text for marker in READ_ONLY_MARKERS)


def _git_fingerprint(root: Path) -> str | None:
    try:
        diff = subprocess.run(
            ["git", "diff", "HEAD", "--binary", "--"],
            cwd=root,
            capture_output=True,
            timeout=30,
            check=False,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if diff.returncode != 0 or untracked.returncode != 0:
            return None

        hasher = hashlib.sha256()
        hasher.update(diff.stdout)
        for raw_path in untracked.stdout.split(b"\x00"):
            if not raw_path:
                continue
            relative = raw_path.decode("utf-8", errors="replace")
            path = (root / relative).resolve()
            if root not in path.parents and path != root:
                continue
            hasher.update(relative.encode("utf-8", errors="replace"))
            if path.is_file():
                try:
                    hasher.update(path.read_bytes())
                except OSError:
                    hasher.update(b"<unreadable>")
        return hasher.hexdigest()
    except (OSError, subprocess.SubprocessError):
        return None


def _tree_fingerprint(root: Path) -> str:
    hasher = hashlib.sha256()
    skip = {".git", ".venv", "node_modules", "__pycache__"}
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in skip)
        for name in sorted(files):
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            hasher.update(relative.encode("utf-8", errors="replace"))
            try:
                hasher.update(path.read_bytes())
            except OSError:
                hasher.update(b"<unreadable>")
    return hasher.hexdigest()


def workspace_fingerprint(root: str | Path) -> str:
    root = Path(root).resolve()
    return _git_fingerprint(root) or _tree_fingerprint(root)


def workspace_changed(before: str, after: str) -> bool:
    return bool(before) and bool(after) and before != after


def engineering_result_valid(action: str, output: dict | None, success: bool) -> bool:
    if not success:
        return False
    output = output or {}
    if action not in {"execute", "build", "repair"}:
        return True
    if not output.get("implementation_expected", False):
        return True
    return output.get("implementation_changed") is True
