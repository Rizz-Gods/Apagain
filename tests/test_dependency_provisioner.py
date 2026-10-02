import unittest
from oth.core.dependency_provisioner import DependencyProvisioner

class DependencyProvisionerTests(unittest.TestCase):
    def test_n8n_warning_creates_install_plan(self):
        worker = DependencyProvisioner()
        result = worker.execute("plan", {
            "input": {"warnings": ["tool not installed locally: n8n"]}
        })
        self.assertTrue(result.success)
        self.assertEqual(result.output["count"], 1)
        self.assertEqual(result.output["plans"][0]["dependency"], "n8n")

if __name__ == "__main__":
    unittest.main()
