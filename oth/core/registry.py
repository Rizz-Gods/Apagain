import json
from pathlib import Path
from .models import Agent, Skill

class Registry:
    def __init__(self, agents_path: str, skills_path: str):
        self.agents_path = Path(agents_path)
        self.skills_path = Path(skills_path)

    def load_agents(self) -> list[Agent]:
        raw = json.loads(self.agents_path.read_text())
        return [Agent(**item) for item in raw.get("agents", [])]

    def load_skills(self) -> list[Skill]:
        raw = json.loads(self.skills_path.read_text())
        return [Skill(**item) for item in raw.get("skills", [])]

    def find_agent(self, capability: str) -> Agent | None:
        agents = [a for a in self.load_agents() if capability in a.capabilities]
        return agents[0] if agents else None

    def find_skill(self, skill_id: str) -> Skill | None:
        return next((s for s in self.load_skills() if s.id == skill_id), None)
