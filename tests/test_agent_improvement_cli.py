"""Evaluation output remains a proposal and cannot overwrite routing inputs."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "agents"))

from intelligence import cli, demo, memory, router


class EvaluationOutputTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.outcomes = self.root / "outcomes.json"
        outcomes = [
            {"task_id": str(case), "model_id": model, "success": model == "candidate"}
            for case in range(10)
            for model in ("baseline", "candidate")
        ]
        self.outcomes.write_text(json.dumps(outcomes), encoding="utf-8")

    def improve(self, output):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return cli.main(["improve", "--baseline", "baseline", "--candidate", "candidate",
                             "--outcomes", str(self.outcomes), "--measured-out", str(output)])

    def test_keep_report_does_not_become_a_routing_input(self):
        output = self.root / "proposal.json"
        self.assertEqual(self.improve(output), 0)
        data = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(data["evaluation"]["verdict"], "keep")
        self.assertEqual(data["measured_quality"]["candidate"]["success_rate"], 1.0)
        self.assertEqual(router.load_measured_quality(str(output)), {})

    def test_active_quality_file_cannot_be_replaced_by_a_proposal(self):
        output = self.root / "measured_quality.json"
        original = b'{"baseline": {"success_rate": 0.8}}\n'
        output.write_bytes(original)
        self.assertEqual(self.improve(output), 2)
        self.assertEqual(output.read_bytes(), original)

    def test_demo_cli_archives_in_requested_memory_root_and_keeps_routing_inputs(self):
        output = self.root / "measured_quality.json"
        original = b'{"baseline": {"success_rate": 0.8}}\n'
        output.write_bytes(original)
        entry = memory.Entry(
            id="guard-git-value-options", project="tel99", kind="fix",
            title="guard git bypass", body="git options push and commit", verified=True,
            tags=("guard", "git", "security"),
        )
        fallback_repo = self.root / "fallback-repo"
        fallback_memory = fallback_repo / "memory"
        for root in (self.root, fallback_memory):
            memory.MemoryStore(root).record(entry)
        with (
            mock.patch.object(demo, "REPO_ROOT", fallback_repo),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(cli.main(["--memory-root", str(self.root), "demo"]), 0)
        self.assertEqual(output.read_bytes(), original)
        reports = list((self.root / "evaluations").glob("*.json"))
        self.assertEqual(len(reports), 1)
        self.assertEqual(router.load_measured_quality(str(reports[0])), {})
        self.assertFalse((fallback_memory / "evaluations").exists())
