"""Regression cases for four Night Lab Qwen failures; no model calls."""
import unittest

from scripts.agents.automation import acceptance, policy


class NightQwenFailureRegressions(unittest.TestCase):
    def test_labels_refuse_nonlists_and_skip_invalid_elements(self):
        for issue in ({}, {"labels": None}, {"labels": 42}, {"labels": "ready"}):
            with self.subTest(issue=issue):
                self.assertEqual(policy._labels(issue), [])
        self.assertEqual(
            policy._labels({"labels": ["bad", None, {}, {"name": True},
                                      {"name": "ready"}, {"name": "bug"}]}),
            ["ready", "bug"],
        )

    def test_queue_filters_invalid_issue_numbers_and_dates(self):
        def pick(items, seen=()):
            issues = [{"labels": [{"name": "ready"}], **item} for item in items]
            result = policy.select_mission(issues, "ready", set(seen))
            return None if result is None else result["number"]

        self.assertEqual(pick([{"number": False}, {"number": 0},
                               {"number": -1}, {"number": 8}]), 8)
        self.assertEqual(pick([{"number": 1, "created_at": 99},
                               {"number": 8, "created_at": "2026-11-23"}]), 8)
        self.assertEqual(pick([{"number": 8}, {"number": 4, "created_at": None},
                               {"number": 2, "created_at": "2026-11-23"}], [4]), 8)
        self.assertEqual(pick([{"number": 1, "created_at": "2026-11-25"},
                               {"number": 3, "created_at": "2026-11-23"}]), 3)

    def test_approval_refuses_malformed_body_without_crashing(self):
        for body in (None, {"not": "text"}, 7):
            with self.subTest(body=body):
                record, reason = policy.read_approval({"body": body})
                self.assertIsNone(record)
                self.assertTrue(isinstance(reason, str) and reason)
        marker = policy.approval_marker("demo", approver="fixture-owner")
        record, reason = policy.read_approval({"body": marker})
        self.assertEqual(record["approved_by"], "fixture-owner")
        self.assertTrue(reason)
        for bad in (marker + "\n" + marker, "<!-- tel99-approval:broken -->"):
            record, reason = policy.read_approval({"body": bad})
            self.assertIsNone(record)
            self.assertTrue(reason)

    def test_artifact_path_accepts_crlf_but_not_ambiguity_or_traversal(self):
        line = "acceptance-artifact: docs/proof.json"
        self.assertEqual(acceptance._artifact_path(line + "\r\nrest"), "docs/proof.json")
        self.assertEqual(acceptance._artifact_path(line + "\nrest"), "docs/proof.json")
        for bad in (line + "\r\n" + line + "\r\n",
                    "acceptance-artifact: ../proof.json",
                    "acceptance-artifact: /proof.json"):
            with self.subTest(body=bad):
                self.assertIsNone(acceptance._artifact_path(bad))


if __name__ == "__main__":
    unittest.main()
