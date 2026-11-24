"""Offline integration tests for Antigravity IDE orchestration, specialist dispatch, leases & cockpit."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from unittest.mock import patch

from scripts.agents import specialist_dispatch
from scripts.agents.automation import (
    env_doctor,
    github_multi_mandate_session as multi,
    ide_coordination,
    local_team,
    multi_cockpit,
    ollama_native,
)
from scripts.agents.native.provider import ProviderError
from scripts.agents.protocol.store import FileStore
from tests.test_github_multi_mandate_session import spec as campaign_spec

ROOT = Path(__file__).resolve().parents[1]


class SpecialistDispatchTests(unittest.TestCase):
    def test_lists_all_12_specialists_with_3_active_and_9_reserved(self):
        rows = specialist_dispatch.list_specialists()
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(1 for r in rows if r["active"]), 3)
        self.assertEqual(sum(1 for r in rows if not r["active"]), 9)
        self.assertTrue(all(r["read_only"] is True for r in rows))

    def test_select_specialists_mobilizes_reserved_roles_without_launching_all_12(self):
        picked = specialist_dispatch.select_specialists(
            "Run a security guard audit and check Kraken market data freshness",
            include_verifier=True,
            max_specialists=3,
        )
        self.assertEqual(len(picked), 3)
        names = [row["name"] for row in picked]
        self.assertIn("tel99-security", names)
        self.assertIn("tel99-verifier", names)
        self.assertLessEqual(len(picked), specialist_dispatch.MAX_CONCURRENT_SPECIALISTS)
        with self.assertRaises(ValueError):
            specialist_dispatch.select_specialists("audit", max_specialists=12)

    def test_build_subagent_brief_preserves_read_only_and_budget_contracts(self):
        brief = specialist_dispatch.build_subagent_brief(
            "tel99-security",
            task="Verify CAS lease conflict rejection.",
            mission_id="val-ide-20261124",
            memory_lessons=["[fix|verified] Lease check: reject overlapping branch and path."],
            run_suffix="001122",
        )
        self.assertEqual(brief["agent_id"], "tel99-security-001122")
        self.assertFalse(brief["active"])
        self.assertEqual(brief["mobilization"], "on_demand_reserved")
        self.assertIn("LECTURE SEULE", brief["system_prompt"])
        self.assertIn("DISCIPLINE DE BUDGET", brief["system_prompt"])
        self.assertIn("Lease check", brief["prompt"])


class IdeCoordinationAndCockpitTests(unittest.TestCase):
    def test_lease_acquire_conflict_expiry_and_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lease = ide_coordination.acquire_lease(
                root,
                actor="antigravity-ide",
                resource_id="mission:val-ide-1",
                branch="agents/tel99-antigravity-v2-20261124",
                paths=["scripts/agents/automation/policy.py"],
                ttl_seconds=600,
                now=1000.0,
            )
            self.assertEqual(lease["actor"], "antigravity-ide")
            with self.assertRaises(ide_coordination.LeaseConflict):
                ide_coordination.acquire_lease(
                    root,
                    actor="codex-cli",
                    resource_id="mission:other",
                    branch="agents/tel99-antigravity-v2-20261124",
                    paths=["./scripts\\agents\\automation\\policy.py"],
                    ttl_seconds=600,
                    now=1005.0,
                )
            with self.assertRaises(ide_coordination.LeaseConflict):
                ide_coordination.release_lease(root, lease["lease_id"], actor="codex-cli", now=1005.0)
            rel = ide_coordination.release_lease(root, lease["lease_id"], actor="antigravity-ide", now=1010.0)
            self.assertTrue(rel["released"])

            # Expired lease no longer blocks another actor.
            ide_coordination.acquire_lease(
                root,
                actor="codex-cli",
                resource_id="mission:after-ttl",
                branch="agents/tel99-antigravity-v2-20261124",
                paths=["scripts/agents/automation/policy.py"],
                ttl_seconds=10,
                now=1020.0,
            )
            snap = ide_coordination.active_leases(root, now=1035.0)
            self.assertEqual(snap["active"], [])
            self.assertEqual(snap["expired_count"], 1)

    def test_multi_mandate_detects_ide_lease_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = campaign_spec(240)
            ledger = FileStore(root / "campaign-240" / "ledger")
            ledger.put_cas("kilo-github/approvals/m1", {
                "mission": {"id": "m1", "path": "scripts/agents/automation/policy.py"},
            }, None)
            ide_coordination.acquire_lease(
                root,
                actor="antigravity-ide",
                resource_id="mission:ide-edit",
                branch=s["base_ref"],
                paths=["scripts/agents/automation/policy.py"],
            )
            collisions = multi.detect_campaign_collisions([s], root)
            self.assertIn(240, collisions)
            self.assertIn("antigravity-ide", collisions[240])

            # Even before campaign-241/ledger exists, a controller lease is detected.
            s241 = campaign_spec(241)
            ide_coordination.acquire_lease(
                root,
                actor="codex-cli",
                resource_id="controller:241",
                branch=s241["base_ref"],
            )
            collisions2 = multi.detect_campaign_collisions([s241], root)
            self.assertIn(241, collisions2)
            self.assertIn("codex-cli", collisions2[241])

    def test_cockpit_snapshot_exposes_team_catalog_and_coordination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ide_coordination.acquire_lease(
                root,
                actor="antigravity-ide",
                resource_id="mission:cockpit-check",
                branch="agents/tel99-antigravity-v2-20261124",
                paths=["scripts/agents/specialist_dispatch.py"],
            )
            snap = multi_cockpit.build_snapshot(root)
            self.assertEqual(snap["team_catalog"]["total"], 12)
            self.assertEqual(snap["team_catalog"]["active_count"], 3)
            self.assertEqual(snap["team_catalog"]["reserved_on_demand_count"], 9)
            self.assertEqual(len(snap["coordination"]["active"]), 1)
            self.assertEqual(snap["coordination"]["active"][0]["actor"], "antigravity-ide")

    def test_config_reuses_existing_autofeed_state_without_spend(self):
        cfg = json.loads((ROOT / "scripts/agents/automation/tel99-config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["state_dir"], "~/Desktop/TEL99_ANTIGRAVITY_AUTOFEED_20261124_STATE")
        self.assertTrue(cfg["auto_feed"])
        self.assertTrue(cfg["isolate_blocked"])
        self.assertFalse(cfg["allow_subscription_cli"])
        self.assertEqual(cfg["cockpit_port"], 8765)

    def test_env_doctor_reports_worktree_gitdir_hint_when_git_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            (fake_root / ".git").write_text("gitdir: C:/fake/parent/.git/worktrees/w1\n", encoding="utf-8")
            info = env_doctor._probe_git(fake_root)
            self.assertFalse(info["ok"])
            self.assertEqual(info["worktree_gitdir"], "C:/fake/parent/.git/worktrees/w1")
            self.assertIn("without disabling sandbox", info["minimal_permission_hint"])

    def test_ide_coordination_cli_runs_standalone(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, "-B", "-m", "scripts.agents.automation.ide_coordination", "status", "--state", tmp],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["active"], [])

    def test_ollama_keep_alive_handoff_and_validation(self):
        default_provider = ollama_native.OllamaNativeProvider(model=local_team.ANALYST_MODEL)
        self.assertEqual(default_provider.keep_alive, "0s")
        with self.assertRaises(ProviderError):
            ollama_native.OllamaNativeProvider(model=local_team.ANALYST_MODEL, keep_alive="999m")

        mission = {
            "team": list(local_team.TEAM),
            "specialist": "tel99-dev",
            "objective": "Verify keep_alive handoff.",
            "port": 11434,
            "model": local_team.ANALYST_MODEL,
        }
        with patch.object(local_team, "OllamaNativeProvider") as mock_provider:
            mock_provider.return_value.keep_alive = "0s"
            mock_provider.return_value.complete.return_value = "Short review note."
            local_team.analyze(mission, "def f(x):\n    return x\n")
            mock_provider.assert_called_with(
                model=local_team.ANALYST_MODEL, timeout=55, max_tokens=256,
            )
            self.assertEqual(mock_provider.return_value.keep_alive, "90s")
            mock_provider.return_value.keep_alive = "0s"
            mission["model"] = "qwen2.5-coder:7b"
            local_team.analyze(mission, "def f(x):\n    return x\n")
            self.assertEqual(mock_provider.return_value.keep_alive, "0s")


if __name__ == "__main__":
    unittest.main()
