import tempfile
import unittest
from pathlib import Path

from oth.core.kernel import OTHKernel
from oth.core.review_miner import ReviewMiner

class FakeReviewMiner(ReviewMiner):
    def _search_review(self, name):
        return f"""Bing Search
{name} reviews complaints
trustpilot.com
https://www.trustpilot.com
## {name} Reviews
Users report expensive pricing and missing features.
reddit.com
https://www.reddit.com/r/smallbusiness/comments/example
## {name} complaint
A business owner says the workflow is slow and manual.
"""

class ReviewMinerTests(unittest.TestCase):
    def test_review_miner_finds_review_evidence(self):
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
            kernel.workers = [FakeReviewMiner()]
            t = kernel.submit("review-mining", "mine", {
                "input": {"signals": [{
                    "title": "Calendly Scheduling Software",
                    "url": "https://calendly.com"
                }]}
            })
            result = kernel.dispatch(t.id)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["count"], 2)
            self.assertEqual(len(kernel.db.list_opportunities()), 2)
            kernel.close()

if __name__ == "__main__":
    unittest.main()
