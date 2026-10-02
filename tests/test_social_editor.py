import tempfile
import unittest
from pathlib import Path

from oth.core.social_editor import SocialEditorialDirector


class SocialEditorialDirectorTests(unittest.TestCase):
    def test_brief_selects_platform_specific_format_and_edit_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = SocialEditorialDirector(root)
            result = worker.execute("brief", {
                "input": {
                    "campaign": {
                        "campaign_id": "campaign-1",
                        "market": "Appointment Scheduling",
                        "pain": "Manual booking causes missed appointments",
                        "proof": "Automated reminders reduce repetitive follow-up",
                    },
                    "platforms": ["instagram", "youtube"],
                    "purpose": "discovery",
                    "funnel_stage": "awareness",
                }
            })
            self.assertTrue(result.success)
            formats = {x["platform"]: x["format"] for x in result.output["briefs"]}
            self.assertEqual(formats["instagram"], "reel")
            self.assertEqual(formats["youtube"], "short")
            self.assertTrue(result.output["briefs"][0]["edit_recipe"])


if __name__ == "__main__":
    unittest.main()
