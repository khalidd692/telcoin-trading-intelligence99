"""Keep the forward journal connected to successful live publication."""
import re
import unittest
from pathlib import Path


class ForwardWorkflowWiring(unittest.TestCase):
    def test_monitor_runs_forward_journal_after_successful_live_publication(self):
        monitor=Path('.github/workflows/monitor.yml').read_text()
        match=re.search(r'(?ms)^  tel99-forward-observation:\s*\n(.*?)(?=^  [a-zA-Z0-9_-]+:\s*$|\Z)',monitor)
        self.assertIsNotNone(match,'Le monitor doit chaîner le journal prospectif')
        job=match.group(1)
        self.assertRegex(job,r'(?m)^    needs: tel99-publication\s*$')
        self.assertIn("needs.tel99-publication.result == 'success'",job)
        self.assertIn("github.ref == 'refs/heads/main'",job)
        self.assertRegex(job,r'(?m)^    uses: \./\.github/workflows/tel99-forward-evaluation\.yml\s*$')

    def test_forward_workflow_allows_reuse_without_removing_existing_triggers(self):
        workflow=Path('.github/workflows/tel99-forward-evaluation.yml').read_text()
        self.assertRegex(workflow,r'(?m)^  workflow_call:\s*$')
        self.assertRegex(workflow,r'(?m)^  schedule:\s*$')
        self.assertRegex(workflow,r'(?m)^  workflow_run:\s*$')
        self.assertIn('cancel-in-progress: false',workflow)


if __name__=='__main__':
    unittest.main()
