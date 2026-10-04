import unittest

from oth.core.automation_design_fallback import AutomationDesignerFallback
from oth.core.opportunity_fallback import OpportunityAnalystFallback
from oth.core.review_miner_fallback import ReviewMinerFallback


class FallbackContractTests(unittest.TestCase):
    def test_opportunity_fallback_preserves_analysis_contract(self):
        result = OpportunityAnalystFallback().execute(
            "score",
            {
                "input": {
                    "signals": [
                        {
                            "title": "Manual scheduling problem",
                            "snippet": "Small businesses complain about repetitive spreadsheets.",
                            "query": "scheduling software complaints",
                            "signal_type": "complaint",
                            "quality": 1.0,
                        }
                    ]
                }
            },
        )
        self.assertTrue(result.success)
        item = result.output["opportunities"][0]
        self.assertIn("score", item)
        self.assertIn("pain", item["score"])
        self.assertTrue(result.output["fallback"])

    def test_review_fallback_preserves_signal_contract(self):
        result = ReviewMinerFallback().execute(
            "mine",
            {
                "input": {
                    "signals": [
                        {
                            "title": "Scheduling software complaint",
                            "snippet": "Users report slow and expensive workflows.",
                            "query": "scheduling complaints",
                            "url": "https://example.com/review",
                            "quality": 0.9,
                        }
                    ]
                }
            },
        )
        self.assertTrue(result.success)
        signal = result.output["signals"][0]
        self.assertEqual(signal["signal_type"], "review")
        self.assertIn("candidate", signal)
        self.assertTrue(result.output["fallback"])

    def test_automation_fallback_preserves_blueprint_contract(self):
        result = AutomationDesignerFallback().execute(
            "design",
            {
                "input": {
                    "opportunities": [
                        {
                            "title": "Scheduling workflow",
                            "snippet": "Manual booking is slow.",
                            "score": {"pain": 80, "automation": 75},
                        }
                    ]
                }
            },
        )
        self.assertTrue(result.success)
        blueprint = result.output["blueprints"][0]["blueprint"]
        self.assertIn("workflow", blueprint)
        self.assertIn("stack", blueprint)
        self.assertTrue(result.output["fallback"])


if __name__ == "__main__":
    unittest.main()
