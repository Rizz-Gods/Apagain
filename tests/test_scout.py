import json
import tempfile
import unittest
from pathlib import Path

from oth.core.analyst import OpportunityAnalyst
from oth.core.kernel import OTHKernel
from oth.core.scout import ScoutWorker

class FakeScout(ScoutWorker):
    def _search(self, query):
        return f"""Bing Search
Open links in new tab
example.com
https://example.com/result
## {query} complaint and alternative
Users report the workflow is manual, expensive and frustrating.
other.com
https://other.com/result
## {query} best software
Teams are looking for faster software and alternatives.
"""

class ScoutTests(unittest.TestCase):
    def test_scout_extracts_and_analyst_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "agents.json").write_text('{"agents":[]}')
            (root / "config" / "skills.json").write_text('{"skills":[]}')
            (root / "config" / "policies.json").write_text(
                '{"external_actions_require_approval":true,'
                '"financial_actions_require_approval":true}'
            )
            (root / "config" / "tools.json").write_text('{"tools":[]}')
            (root / "config" / "schedules.json").write_text('{"schedules":[]}')
            kernel = OTHKernel(root)
            kernel.workers = [FakeScout(), OpportunityAnalyst()]
            result = kernel.submit("scout", "scan", {
                "queries": ["small business software complaints"],
                "next": [{"capability": "opportunity-analysis", "action": "score"}],
            })
            scout = kernel.dispatch(result.id)
            self.assertEqual(scout["status"], "succeeded")
            self.assertGreaterEqual(scout["count"], 1)
            child = kernel.tasks()[-1]
            self.assertEqual(child["capability"], "opportunity-analysis")
            analyst = kernel.dispatch(child["id"])
            self.assertEqual(analyst["status"], "succeeded")
            self.assertGreaterEqual(analyst["count"], 1)
            self.assertTrue(kernel.db.top_opportunities())
            kernel.close()

if __name__ == "__main__":
    unittest.main()
