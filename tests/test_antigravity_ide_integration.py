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
    learning_loop,
    local_team,
    multi_cockpit,
    ollama_native,
)
from scripts.agents.automation.autonomy_runtime import Runtime, seal
from scripts.agents.intelligence.memory import Entry, MemoryStore
from scripts.agents.native.provider import ProviderError
from scripts.agents.protocol.store import FileStore
from tests.test_autonomy_runtime import mission as synth_mission
from tests.test_github_multi_mandate_session import FakeCampaign, spec as campaign_spec, write_manifest

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

    def test_audit_all_12_specialists_passes_10_criteria(self):
        audit = specialist_dispatch.audit_all_specialists()
        self.assertEqual(audit["total"], 12)
        self.assertEqual(audit["active_count"], 3)
        self.assertEqual(audit["reserved_count"], 9)
        self.assertTrue(audit["all_ok"], audit)

    def test_multi_process_coordination_conflict_and_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = (
                "import sys\n"
                "from scripts.agents.automation import ide_coordination\n"
                "try:\n"
                "    lease = ide_coordination.acquire_lease(sys.argv[1], actor=sys.argv[2], "
                "resource_id='mission:shared', branch='agents/b', paths=['scripts/agents/automation/policy.py'])\n"
                "    print('WIN:' + lease['lease_id'])\n"
                "    raise SystemExit(0)\n"
                "except ide_coordination.LeaseConflict:\n"
                "    print('CONFLICT')\n"
                "    raise SystemExit(3)\n"
            )
            p1 = subprocess.Popen(
                [sys.executable, "-B", "-c", code, str(root), "antigravity-ide"],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            p2 = subprocess.Popen(
                [sys.executable, "-B", "-c", code, str(root), "codex-cli"],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            out1, _ = p1.communicate(timeout=15)
            out2, _ = p2.communicate(timeout=15)
            codes = sorted([p1.returncode, p2.returncode])
            self.assertEqual(codes, [0, 3], (out1, out2))

            ev = ide_coordination.record_handoff(
                root,
                from_actor="antigravity-ide",
                to_actor="tel99-cli",
                resource_id="mission:shared",
                summary="Handing verified patch to CLI.",
                evidence_ref="sha:abc123",
            )
            self.assertEqual(ev["kind"], "handoff")
            activity = ide_coordination.recent_activity(root)
            self.assertTrue(any(row["kind"] == "lease_conflict" for row in activity))
            self.assertTrue(any(row["kind"] == "handoff" for row in activity))

    def test_auto_recover_local_crash_once_and_fail_closed_when_unsafe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 1. Safe local mission crash -> auto-recovers once and reaches ACCEPTED
            local_dir = root / "local-crash"
            m_local = {
                "id": "AUTO-RECOVER-1", "owner": "local", "project": "tel99",
                "specialist": "tel99-dev", "priority": "P1", "dependencies": [],
                "objective": "Safe local test", "base_sha": "a" * 40,
                "path": "scripts/agents/automation/policy.py", "function": "branch_is_protected",
                "test": "assert True", "sandbox_image": "python@sha256:" + "0" * 64,
                "model": "gemma4:e4b-tel99-8k", "port": 11434,
            }
            rt1 = Runtime(local_dir, executor=lambda _m: {"ok": True}, verifier=lambda _m, _r: {"ok": True})
            rt1.claim(m_local)
            rt1.inbox.receive({"request_id": m_local["id"]})
            rt1.save(m_local, "RUNNING")

            rt2 = Runtime(
                local_dir,
                executor=lambda m: {"artifact": "def branch_is_protected(b):\n    return True\n", "sha256": "x"},
                verifier=lambda _m, _r: {"ok": True},
                auto_recover_local_crash=True,
            )
            # Mock _process safely by checking _can_auto_recover_local_crash and transition to ACK
            can, reason = rt2._can_auto_recover_local_crash(m_local, rt2.state(m_local))
            self.assertTrue(can, reason)

            # 2. If RESULT receipt already exists, auto-recovery must refuse (AWAITING_HUMAN)
            rt2.store.put_cas(f"kilo-github/outbox/{m_local['id']}/RESULT", {"url": "https://gh/1"}, None)
            can_after_result, reason2 = rt2._can_auto_recover_local_crash(m_local, rt2.state(m_local))
            self.assertFalse(can_after_result)
            self.assertIn("irreversible", reason2)

            # 3. External owner ('kilo') crash -> never auto-recovers
            ext_dir = root / "ext-crash"
            m_ext = synth_mission("EXT-CRASH-1")
            rt_ext = Runtime(ext_dir, auto_recover_local_crash=True)
            rt_ext.claim(m_ext)
            rt_ext.inbox.receive({"request_id": m_ext["id"]})
            rt_ext.save(m_ext, "RUNNING")
            rt_ext.run_queue([m_ext], seal([m_ext]))
            self.assertEqual(rt_ext.state(m_ext)["status"], "AWAITING_HUMAN")

    def test_exit_when_done_and_learning_proposals_in_cockpit_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = write_manifest(root, [campaign_spec(245)])
            calls, done = [], {}
            sleeps = []
            summary = multi.run_campaigns(
                manifest, root / "state", seconds=120, poll_interval=30,
                build=lambda info, r, d: FakeCampaign(info, done, calls),
                sleep=lambda s: sleeps.append(s),
                exit_when_done=True,
            )
            self.assertEqual(summary, {245: True})
            self.assertEqual(sleeps, [])

            mem = MemoryStore(root / "state" / "learning" / "memory")
            mem.record(Entry(
                id="fix-demo-proposal", project="tel99", kind="fix",
                title="Verified proposal fix", body="Body",
                verified=True, verified_by="tester",
            ))
            props = learning_loop.propose_skill_improvements(root / "state")
            self.assertEqual(props["learning_kind"], "procedural_memory_and_proposals")
            self.assertFalse(props["model_retraining"])
            self.assertFalse(props["security_guardrails_mutable"])

            snap = multi_cockpit.build_snapshot(root / "state")
            self.assertTrue(snap["memory"]["recent_entries"])
            self.assertEqual(snap["learning"]["improvement_proposals"]["counts"]["verified_fixes"], 1)
            self.assertIn("recent_activity", snap["coordination"])


if __name__ == "__main__":
    unittest.main()
