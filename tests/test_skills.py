import tempfile
import unittest
from pathlib import Path

from oth.core.skills import SkillAcquirer

class SkillTests(unittest.TestCase):
    def test_scan_and_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            skill = repo / "skills" / "demo-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: Demo capability\n---\n\nDo the thing.\n",
                encoding="utf-8",
            )
            manager = SkillAcquirer(root)
            entries = manager.scan(repo)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["name"], "demo-skill")
            target = manager.install(entries[0])
            self.assertTrue((target / "SKILL.md").exists())
            self.assertTrue((target / ".oth-source.json").exists())

if __name__ == "__main__":
    unittest.main()
