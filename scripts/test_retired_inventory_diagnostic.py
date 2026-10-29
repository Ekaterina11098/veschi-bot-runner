"""Offline regression: retired diagnostic must have no data-access path."""
import pathlib
import unittest

PATH = pathlib.Path(".github/workflows/inspect-china-returns-20261028.yml")
EXPECTED = "name: Retired China returns inspection\non:\n  workflow_dispatch:\npermissions: {}\njobs:\n  retired:\n    if: ${{ false }}\n    runs-on: ubuntu-latest\n    steps:\n      - name: Inspection retired\n        run: echo \"This diagnostic has been retired.\"\n"

class RetiredDiagnosticTest(unittest.TestCase):
    def test_retired_workflow_is_inert(self):
        self.assertEqual(PATH.read_text(encoding="utf-8"), EXPECTED)

    def test_no_credentials_network_or_automatic_trigger(self):
        text = PATH.read_text(encoding="utf-8")
        for forbidden in ("secrets.", "MOYSKLAD", "urllib", "requests", "checkout@", "upload-artifact", "push:", "schedule:", "workflow_call:"):
            self.assertNotIn(forbidden, text)
        self.assertIn("if: ${{ false }}", text)
        self.assertIn("permissions: {}", text)

if __name__ == "__main__":
    unittest.main()
