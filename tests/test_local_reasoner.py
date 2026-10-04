import unittest

from oth.core.local_reasoner import LocalReasonerWorker


class LocalReasonerTests(unittest.TestCase):
    def test_reasoning_fallback_is_structured(self):
        result = LocalReasonerWorker().execute(
            "prompt",
            {"prompt": "debug the broken workflow and implement the fix"},
        )
        self.assertTrue(result.success)
        self.assertTrue(result.output["fallback"])
        self.assertIn("response", result.output)
        self.assertGreaterEqual(len(result.output["response"]["steps"]), 2)


if __name__ == "__main__":
    unittest.main()
