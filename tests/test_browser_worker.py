import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from oth.workers.browser import BrowserWorker


class BrowserWorkerTests(unittest.TestCase):
    def test_browser_worker_builds_chrome_profile_command(self):
        agent = SimpleNamespace(
            metadata={
                "command": "agent-browser.cmd",
                "session": "test",
                "browser_executable": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "browser_profile": "data\\browser_profiles\\test",
            }
        )
        worker = BrowserWorker(agent)
        fake = SimpleNamespace(
            returncode=0,
            stdout="ok",
            stderr="",
        )
        with patch("oth.workers.browser.subprocess.run", return_value=fake) as run:
            result = worker.execute("command", {
                "command": "open",
                "args": ["https://example.com"],
            })
        self.assertTrue(result.success)
        command = run.call_args.args[0]
        self.assertIn("--executable-path", command)
        self.assertIn("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", command)
        self.assertIn("--profile", command)
        self.assertIn("data\\browser_profiles\\test", command)
        self.assertEqual(result.output["session"], "test")


if __name__ == "__main__":
    unittest.main()
