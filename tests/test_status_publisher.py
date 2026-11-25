"""Offline unit tests for G7/G8 sanitized GitHub status publisher."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import publish_status_report as psr


class TestStatusPublisher(unittest.TestCase):
    def test_sanitize_strips_personal_paths_and_private_keys(self) -> None:
        raw = {
            "path": r"C:\Users\sabri\Desktop\TEL99_BUDGET_FAMILIAL_V2",
            "unix": "/Users/alice/secret_project",
            "messages": [{"role": "user", "content": "private chat"}],
            "api_key": "gsk_123456789012345678901234567890",
            "safe_count": 12,
        }
        cleaned = psr.sanitize_value(raw)
        self.assertNotIn("messages", cleaned)
        self.assertNotIn("api_key", cleaned)
        self.assertNotIn("sabri", cleaned["path"])
        self.assertNotIn("alice", cleaned["unix"])
        self.assertEqual(cleaned["safe_count"], 12)
        psr.verify_sanitized_json(json.dumps(cleaned))

    def test_verify_sanitized_blocks_secrets_and_personal_paths(self) -> None:
        with self.assertRaises(psr.SecuritySanitizationError):
            psr.verify_sanitized_json('{"leak": "gsk_abcdefghijklmnopqrstuvwxyz123456"}')
        with self.assertRaises(psr.SecuritySanitizationError):
            psr.verify_sanitized_json('{"leak": "ghp_abcdefghijklmnopqrstuvwxyz123456"}')
        with self.assertRaises(psr.SecuritySanitizationError):
            psr.verify_sanitized_json(r'{"path": "C:\\Users\\sabri\\Desktop\\x"}')

    def test_build_status_report_offline_structure_and_sanitization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            report = psr.build_status_report(
                repo=ROOT,
                desktop=td_path,
                state_root=td_path / "state",
                probe_live=False,
            )
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["team"]["total_agents"], 12)
            self.assertIn("G0_command_center_live", report["delivery_gates"])
            self.assertIn("G7_github_status_published", report["delivery_gates"])
            self.assertIn("G8_proactive_initiative_and_brief", report["delivery_gates"])
            self.assertIn("600k theoretical total", report["groq_quotas"]["accounting_note"])
            self.assertIn("480k TPD max background", report["groq_quotas"]["accounting_note"])
            self.assertFalse(report["continuous_learning"]["lora_training_enabled"])
            psr.verify_sanitized_json(json.dumps(report, ensure_ascii=False))

    def test_refuses_publishing_to_main(self) -> None:
        with self.assertRaises(ValueError):
            psr.publish_status_to_branch({"ok": True}, branch="main", push=False)


if __name__ == "__main__":
    unittest.main()
