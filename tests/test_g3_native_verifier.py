"""Offline, deterministic G3 proof checks; no AI, GitHub, or Docker needed."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "agents" / "automation" / "g3_native_verifier.py"
spec = importlib.util.spec_from_file_location("g3_native_verifier_test", MODULE)
g3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g3)


def checked(status="PASS"):
    return [{"id": k, "status": status, "reproducible": True} for k in g3.REQUIRED]


class G3VerdictTests(unittest.TestCase):
    def test_all_real_checks_green(self):
        self.assertEqual(g3.verdict(checked()), "PASS")

    def test_three_llm_passes_with_red_test_must_reject(self):
        checks = checked()
        checks[4]["status"] = "FAIL"
        self.assertEqual(g3.verdict(checks, reported_llm_passes=("PASS", "PASS", "PASS")), "REJECTED")

    def test_one_red_one_unknown_must_reject(self):
        checks = checked()
        checks[0]["status"] = "NEEDS_HUMAN"
        checks[-1]["status"] = "FAIL"
        self.assertEqual(g3.verdict(checks), "REJECTED")

    def test_no_proof_needs_human(self):
        self.assertEqual(g3.verdict([]), "NEEDS_HUMAN")

    def test_missing_check_needs_human(self):
        self.assertEqual(g3.verdict(checked()[:-1]), "NEEDS_HUMAN")

    def test_manual_check_needs_human(self):
        checks = checked()
        checks[2]["status"] = "NEEDS_HUMAN"
        self.assertEqual(g3.verdict(checks), "NEEDS_HUMAN")

    def test_non_reproducible_claim_needs_human(self):
        checks = checked()
        checks[2]["reproducible"] = False
        self.assertEqual(g3.verdict(checks), "NEEDS_HUMAN")

    def test_duplicate_check_rejected(self):
        self.assertEqual(g3.verdict(checked() + [checked()[0]]), "REJECTED")

    def test_bad_shape_rejected(self):
        self.assertEqual(g3.verdict([{"id": None}]), "REJECTED")

    def test_sha_or_scope_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(g3, "git", return_value=b"00\n"):
                with self.assertRaises(g3.Rejected):
                    g3.verify_pinned_commit(Path(td))

    def test_missing_git_entry_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(g3, "git", return_value=b""):
                with self.assertRaises(g3.Rejected):
                    g3.read_blob(Path(td), g3.COMMIT, "missing.py")

    def test_cli_never_claims_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "evidence.json"
            with patch.object(g3, "verify_pinned_commit", side_effect=g3.NeedsHuman("no verification")):
                self.assertEqual(g3.main(["--candidate", td, "--output", str(out)]), 2)
            import json
            recorded = json.loads(out.read_text())
            self.assertEqual(recorded["verdict"], "NEEDS_HUMAN")
            self.assertIs(recorded["accepted"], False)
            self.assertEqual(recorded["provider_calls"], 0)


if __name__ == "__main__":
    unittest.main()
