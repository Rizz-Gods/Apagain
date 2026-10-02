import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

FRONTMATTER = re.compile(r"\A---\s*\r?\n(.*?)\r?\n---\s*\r?\n", re.S)

class SkillAcquirer:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.sources = self.root / "data" / "skill_sources"
        self.candidates = self.root / "skills" / "candidates"
        self.installed = self.root / "skills" / "installed"
        for path in (self.sources, self.candidates, self.installed):
            path.mkdir(parents=True, exist_ok=True)

    def _slug(self, repo: str) -> str:
        repo = repo.rstrip("/")
        tail = repo.rsplit("/", 1)[-1]
        return re.sub(r"[^A-Za-z0-9._-]+", "-", tail.removesuffix(".git")).lower()

    def clone(self, repo_url: str, ref: str | None = None) -> Path:
        slug = self._slug(repo_url)
        target = self.sources / slug
        if not (target / ".git").exists():
            subprocess.run(["git", "clone", "--depth", "1", repo_url, str(target)],
                           check=True, capture_output=True, text=True)
        if ref:
            subprocess.run(["git", "-C", str(target), "fetch", "origin", ref],
                           check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(target), "checkout", ref],
                           check=True, capture_output=True, text=True)
        return target

    def _git(self, repo: Path, *args: str) -> str:
        result = subprocess.run(["git", "-C", str(repo), *args],
                                check=True, capture_output=True, text=True)
        return result.stdout.strip()

    def _parse_frontmatter(self, text: str) -> dict[str, Any]:
        match = FRONTMATTER.match(text)
        if not match:
            return {}
        data: dict[str, Any] = {}
        for line in match.group(1).splitlines():
            if ":" not in line or line.startswith((" ", "\t")):
                continue
            key, value = line.split(":", 1)
            value = value.strip().strip('"').strip("'")
            data[key.strip()] = value
        return data

    def _digest(self, path: Path) -> str:
        digest = hashlib.sha256()
        for file in sorted(path.rglob("*")):
            if file.is_file() and ".git" not in file.parts:
                digest.update(str(file.relative_to(path)).encode())
                digest.update(file.read_bytes())
        return digest.hexdigest()

    def scan(self, repo: Path) -> list[dict[str, Any]]:
        try:
            commit = self._git(repo, "rev-parse", "HEAD")
        except subprocess.CalledProcessError:
            commit = None
        results: list[dict[str, Any]] = []
        for marker in repo.rglob("SKILL.md"):
            if ".git" in marker.parts:
                continue
            text = marker.read_text(encoding="utf-8", errors="replace")
            meta = self._parse_frontmatter(text)
            name = meta.get("name")
            description = meta.get("description")
            if not name or not description:
                continue
            skill_root = marker.parent
            rel = str(skill_root.relative_to(repo)).replace("\\", "/")
            skill_id = f"github:{self._slug(str(repo))}:{rel}"
            results.append({
                "id": skill_id,
                "name": name,
                "description": description,
                "source": str(repo),
                "path": rel,
                "commit": commit,
                "sha256": self._digest(skill_root),
                "skill_file": str(marker),
            })
        return results

    def index(self, entries: list[dict[str, Any]], output: str | Path):
        Path(output).write_text(json.dumps({
            "version": 1,
            "skills": entries,
        }, indent=2), encoding="utf-8")

    def install(self, entry: dict[str, Any]) -> Path:
        source = Path(entry["skill_file"]).parent
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", entry["name"]).strip("-").lower()
        target = self.installed / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        (target / ".oth-source.json").write_text(
            json.dumps(entry, indent=2), encoding="utf-8"
        )
        return target

    def catalog(self) -> list[dict[str, Any]]:
        index = self.root / "data" / "skills-index.json"
        if not index.exists():
            return []
        return json.loads(index.read_text(encoding="utf-8")).get("skills", [])

    def find(self, query: str, limit: int = 2) -> list[dict[str, Any]]:
        words = set(re.findall(r"[A-Za-z0-9_+-]{3,}", query.lower()))
        scored = []
        for entry in self.catalog():
            hay = f'{entry["name"]} {entry["description"]}'.lower()
            score = sum(1 for word in words if word in hay)
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1]["name"]))
        return [entry for _, entry in scored[:limit]]

    def context_for(self, query: str, limit: int = 2, chars: int = 12000) -> str:
        chunks = []
        for entry in self.find(query, limit):
            path = Path(entry["skill_file"])
            if not path.exists():
                continue
            body = path.read_text(encoding="utf-8", errors="replace")
            chunks.append(
                f'### Skill: {entry["name"]}\n'
                f'Source commit: {entry.get("commit") or "local"}\n{body}'
            )
        return "\n\n".join(chunks)[:chars]
