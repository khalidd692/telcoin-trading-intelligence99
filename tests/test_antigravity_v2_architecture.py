"""Comprehensive offline tests for the TEL99 Antigravity V2 5-layer architecture."""
from __future__ import annotations

import ast
import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.agents import project_kit
from scripts.agents.automation import (
    env_doctor,
    github_multi_mandate_session as multi,
    github_owner_feed as feed,
    learning_loop,
    local_codegen,
    local_model_routing as routing,
    local_team,
    multi_cockpit,
    proposal_builder,
)
from scripts.agents.automation.autonomy_runtime import Runtime, fingerprint, seal
from scripts.agents.intelligence.memory import Entry, MemoryStore
from scripts.agents.protocol.store import FileStore
from tests.test_github_owner_feed import BASE, REF, FakeGitHub, fixture as owner_fixture
from tests.test_local_model_routing import LARGE, SMALL, SOURCE as ROUTE_SOURCE, binding, endpoint, mission as route_mission
from tests.test_multiagent_pilot import FUNCTION, FIX, advice, mission as pilot_mission


class FiveRoleTeamAndSecurityTests(unittest.TestCase):
    def test_coordinate_binds_scope_and_analyst_accepts_bounded_lessons(self):
        m = pilot_mission()
        coord = local_team.coordinate(m, FUNCTION)
        self.assertEqual(coord["role"], local_team.COORDINATOR)
        self.assertTrue(coord["ok"])
        self.assertEqual(len(coord["scope_sha256"]), 64)
        self.assertEqual([s["role"] for s in coord["steps"]], local_team.TEAM)

        with patch.object(local_team, "OllamaNativeProvider") as provider:
            provider.return_value.complete.return_value = advice()["analysis"]
            result = local_team.analyze(
                m, FUNCTION, lessons=["[fix|verified] Check empty dict: Return {} safely."]
            )
        self.assertEqual(result["role"], "tel99-analyst")
        prompt = provider.return_value.complete.call_args.kwargs["prompt"]
        self.assertIn("Verified project memory notes", prompt)
        self.assertIn("Check empty dict", prompt)

    def test_retry_passes_sanitized_repair_context_to_analyst(self):
        m = pilot_mission(
            max_attempts=2,
            test="assert False, 'PRIVATE_TEST_SECRET'  # case: malformed-names | expected: Ignore blank strings.",
        )
        previous = "def load_json(path):\n    SECRET_VAR = 'SECRET_STR'\n    return {'ok': True}\n"
        digest = hashlib.sha256(previous.encode("utf-8")).hexdigest()
        feedback = {"kind": "candidate-test", "line": 1, "candidate_sha256": digest}
        with (
            patch.object(local_codegen.sandbox, "require_local_image"),
            patch.object(local_codegen, "_source", return_value=FUNCTION),
            patch.object(local_team, "OllamaNativeProvider") as analyst_provider,
            patch.object(local_codegen, "OllamaNativeProvider") as dev_provider,
            patch.object(local_codegen.local_model_routing, "available_memory_mib", return_value=2048),
        ):
            analyst_provider.return_value.complete.return_value = advice()["analysis"]
            dev_provider.return_value.complete.return_value = FIX
            receipt = local_codegen.execute(m, feedback=feedback, previous=previous)
        self.assertTrue(local_team.valid_trace(m, receipt))
        analyst_prompt = analyst_provider.return_value.complete.call_args.kwargs["prompt"]
        self.assertIn("Previous attempt failed independent verification", analyst_prompt)
        self.assertIn("malformed-names", analyst_prompt)
        self.assertIn("Ignore blank strings.", analyst_prompt)
        self.assertNotIn("PRIVATE_TEST_SECRET", analyst_prompt)
        self.assertNotIn("SECRET_VAR", analyst_prompt)
        self.assertNotIn("SECRET_STR", analyst_prompt)

    def test_security_review_blocks_non_stdlib_imports_before_docker(self):
        m = pilot_mission()
        bad_fix = "def load_json(path):\n    import requests\n    return requests.get(path).json()\n"
        result = {
            "artifact": bad_fix,
            "sha256": hashlib.sha256(bad_fix.encode()).hexdigest(),
            "specialist_id": "tel99-dev",
            "provider": local_codegen.PROVIDER,
            "model": m["model"],
            "agent_trace": local_team.trace(advice(), developer_model=m["model"], artifact=bad_fix),
        }
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(local_codegen, "_source", return_value=FUNCTION),
            patch.object(local_codegen, "_behavior") as docker_mock,
        ):
            report = local_codegen.verify(m, result, Path(tmp))
        docker_mock.assert_not_called()
        self.assertFalse(report["ok"])
        self.assertEqual(report["coordination"]["role"], local_team.COORDINATOR)
        self.assertEqual(report["security_review"]["role"], local_team.SECURITY)
        self.assertFalse(report["security_review"]["ok"])
        self.assertEqual(report["security_review"]["code"], "new-non-stdlib-import")
        self.assertEqual(report["feedback"]["kind"], "candidate-diff")

    def test_security_review_blocks_outside_function_modification(self):
        before = "CONST = 1\n\ndef f(x):\n    return x\n"
        after = "CONST = 2\n\ndef f(x):\n    return x + 1\n"
        before_fn = ast.parse(before).body[1]
        after_fn = ast.parse(after).body[1]
        sec = local_team.review_candidate(before, before_fn, after, after_fn)
        self.assertFalse(sec["ok"])
        self.assertEqual(sec["code"], "outside-approved-function")


class LearningLoopTests(unittest.TestCase):
    def test_capitalizes_repaired_fix_and_retrieves_project_isolated_lessons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem_root = root / "learning" / "memory"
            other = MemoryStore(mem_root)
            other.record(Entry(
                id="foreign-fix", project="other-project", kind="fix",
                title="Secret other project fix", body="Should never leak to tel99.",
                verified=True, verified_by="tester",
            ))

            m = pilot_mission(id="learn-fix-1", path="scripts/agents/automation/verify_runtime.py",
                              function="tool_names", objective="Filter non-empty tool_names.")
            state = {
                "status": "ACCEPTED",
                "attempt": 2,
                "attempt_history": [{"number": 1, "feedback": {"kind": "candidate-test", "line": 3}}],
                "verification": {"model": m["model"], "verifier": local_codegen.VERIFIER,
                                 "generation_seconds": 12.5, "verification_seconds": 3.2, "checks": []},
            }
            recorded = learning_loop.record_outcome(mem_root, m, state)
            self.assertEqual(recorded, ["fix-learn-fix-1"])
            # Idempotent re-call does not create duplicates or bump versions.
            self.assertEqual(learning_loop.record_outcome(mem_root, m, state), [])

            lessons = learning_loop.retrieve_lessons(mem_root, "tel99", m)
            self.assertEqual(len(lessons), 1)
            self.assertIn("fix|verified", lessons[0])
            self.assertIn("tool_names", lessons[0])
            self.assertNotIn("other-project", "".join(lessons))

    def test_collects_more_than_two_missions_and_feeds_measured_quality_into_router(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camp = root / "campaign-250"
            store = FileStore(camp / "ledger")
            store.put_cas("github-local-code/config", {"issue": 250, "mandate_id": 1}, None)
            for idx in range(1, 5):
                mid = f"m-{idx}"
                store.put_cas(f"kilo-local/{mid}", {
                    "id": mid,
                    "status": "ACCEPTED" if idx <= 3 else "BLOCKED",
                    "attempt": 1 if idx != 2 else 2,
                    "attempt_history": [] if idx != 2 else [{"number": 1}],
                    "verification": {
                        "model": "qwen2.5-3b-instruct",
                        "generation_seconds": 4.0,
                        "verification_seconds": 2.0,
                        "checks": [{"name": "candidate-passes", "ok": idx <= 3}],
                    },
                }, None)
            report = learning_loop.sync_measured_quality(root)
            self.assertEqual(report["missions_total"], 4)
            self.assertEqual(report["accepted"], 3)
            self.assertEqual(report["repaired"], 1)
            mq = json.loads((root / "learning" / "measured_quality.json").read_text(encoding="utf-8"))
            self.assertEqual(mq["local/llama-qwen2.5-3b"]["success_rate"], 0.75)

            # Measured quality makes router prefer LARGE (prior 0.68) over SMALL when SMALL measured low.
            with endpoint([SMALL[1]]) as (p_small, _), endpoint([LARGE[1]]) as (p_large, _), patch.object(
                routing, "available_memory_mib", return_value=2048
            ):
                small, large = binding(SMALL, p_small), binding(LARGE, p_large)
                chosen = routing.choose(
                    route_mission(small, large), ROUTE_SOURCE,
                    measured_quality={"local/llama-qwen2.5-3b": 0.20, "local/llama-qwen2.5-coder-7b": 0.90},
                )
                self.assertEqual(chosen["decision"]["chosen"], LARGE[0])


class OwnerFeedArchiveTests(unittest.TestCase):
    def test_completed_closed_controller_archives_cleanly_while_uncompleted_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gh = FakeGitHub()
            pins = feed.pinned_owner_feed(root, fetcher=gh)
            self.assertEqual([p["issue"] for p in pins], [211])

            # Without completed local ledger proof, hiding #211 must still fail closed.
            gh.hide = True
            with self.assertRaisesRegex(ValueError, "disappeared"):
                feed.pinned_owner_feed(root, fetcher=gh)

            # Populate full verified local ledger + RESULT + draft PR receipts for #211.
            ledger = FileStore(root / "campaign-211" / "ledger")
            ledger.put_cas("github-local-code/config", {
                "repo": feed.REPO, "issue": 211,
                "mandate_id": pins[0]["mandate_comment"],
                "mandate_sha256": pins[0]["mandate_sha256"],
            }, None)
            for mid in ("first", "second"):
                ledger.put_cas(f"kilo-github/approvals/{mid}", {"mission": {"id": mid}}, None)
                ledger.put_cas(f"kilo-local/{mid}", {"id": mid, "status": "ACCEPTED"}, None)
                ledger.put_cas(f"kilo-github/outbox/{mid}/RESULT", {
                    "url": f"https://github.com/{feed.REPO}/issues/211#issuecomment-1",
                    "event": {
                        "status": "ACCEPTED",
                        "evidence_url": f"https://github.com/{feed.REPO}/issues/211#issuecomment-2",
                        "pull_request_url": f"https://github.com/{feed.REPO}/pull/999",
                    },
                }, None)

            # Now #211 is closed on GitHub and a new controller #212 appears.
            row212, comment212 = owner_fixture(212)
            class NextFeedGitHub:
                def __call__(self, endpoint):
                    if endpoint == "user":
                        return gh("user")
                    if endpoint.startswith(f"repos/{feed.REPO}/issues?"):
                        return [row212]
                    if endpoint.startswith(f"repos/{feed.REPO}/issues/212/comments?"):
                        return [comment212]
                    raise AssertionError(endpoint)

            next_pins = feed.pinned_owner_feed(root, fetcher=NextFeedGitHub())
            self.assertEqual([p["issue"] for p in next_pins], [212])
            archived = FileStore(root / "feed-ledger").get(feed.ARCHIVE_KEY)
            self.assertEqual([p["issue"] for p in archived["pins"]], [211])


class HarnessAndPortabilityTests(unittest.TestCase):
    def test_env_doctor_reports_ready_and_blockers(self):
        ok = env_doctor.diagnose(
            git_probe=lambda: {"ok": True, "branch": "agents/test", "head": "a" * 40, "dirty": False},
            gh_probe=lambda: {"ok": True, "owner": "khalidd692", "push": True},
            ollama_probe=lambda: {"ok": True, "installed": ["gemma4:e4b-tel99-8k"], "analyst_ready": True},
            docker_probe=lambda _img: {"ok": True, "server_version": "29.9.2"},
            memory_probe=lambda: 8192,
        )
        self.assertTrue(ok["ready"])
        self.assertEqual(ok["blockers"], [])

        bad = env_doctor.diagnose(
            git_probe=lambda: {"ok": True},
            gh_probe=lambda: {"ok": False, "error": "no auth"},
            ollama_probe=lambda: {"ok": False, "error": "down"},
            docker_probe=lambda _img: {"ok": False, "error": "down"},
            memory_probe=lambda: 256,
        )
        self.assertFalse(bad["ready"])
        self.assertIn("GITHUB_AUTH_OR_PUSH_UNAVAILABLE", bad["blockers"])
        self.assertIn("OLLAMA_OR_ANALYST_MODEL_UNAVAILABLE", bad["blockers"])
        self.assertIn("DOCKER_OR_SANDBOX_IMAGE_UNAVAILABLE", bad["blockers"])
        self.assertIn("INSUFFICIENT_FREE_MEMORY", bad["blockers"])

    def test_proposal_builder_validates_hashes_and_baseline_red(self):
        spec = {
            "controller_issue": 220,
            "mandate_comment_id": 999999,
            "expires_at": "2026-12-10T23:59:59Z",
            "base_ref": REF,
            "base_sha": BASE,
            "missions": [
                {
                    "id": "prop-a", "issue": 221, "dependencies": [],
                    "path": "scripts/agents/automation/verify_runtime.py",
                    "function": "tool_names",
                    "objective": "Ignore blank tool names.",
                    "test": "assert False, 'red'",
                },
                {
                    "id": "prop-b", "issue": 222, "dependencies": ["prop-a"],
                    "path": "scripts/agents/automation/pilot_recipe.py",
                    "function": "dedup_key",
                    "objective": "Normalize whitespace.",
                    "test": "assert False, 'red'",
                },
            ],
        }
        proposal = proposal_builder.build_proposal(
            spec,
            verify_baseline=True,
            source_loader=lambda m: f"def {m['function']}(x):\n    return x\n",
            behavior_runner=lambda _img, _src, _test: (False, 1),
        )
        self.assertEqual(proposal["github_writes_performed"], 0)
        self.assertEqual(len(proposal["missions"]), 2)
        self.assertTrue(all(m["baseline_check"]["baseline_red"] for m in proposal["missions"]))
        with self.assertRaisesRegex(ValueError, "already passes"):
            proposal_builder.build_proposal(
                spec,
                verify_baseline=True,
                source_loader=lambda m: f"def {m['function']}(x):\n    return x\n",
                behavior_runner=lambda _img, _src, _test: (True, None),
            )

    def test_multi_cockpit_snapshot_and_loopback_host_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = FileStore(root / "campaign-205" / "ledger")
            ledger.put_cas("github-local-code/config", {
                "issue": 205, "mandate_id": 711, "base_ref": REF, "base_sha": BASE,
            }, None)
            ledger.put_cas("kilo-github/approvals/m1", {
                "issue": 206,
                "mission": {"id": "m1", "model": "gemma4:e4b-tel99-8k", "team": local_team.TEAM,
                            "objective": "PRIVATE_OBJECTIVE", "test": "PRIVATE_TEST"},
            }, None)
            ledger.put_cas("kilo-local/m1", {
                "id": "m1", "status": "ACCEPTED", "attempt": 1,
                "result": {"artifact": "PRIVATE_CODE_ARTIFACT", "model": "gemma4:e4b-tel99-8k"},
                "verification": {"model": "gemma4:e4b-tel99-8k", "generation_seconds": 5.0,
                                 "verification_seconds": 2.0, "checks": [{"name": "c1", "ok": True}]},
            }, None)
            snap = multi_cockpit.build_snapshot(root)
            serialized = json.dumps(snap)
            self.assertNotIn("PRIVATE_OBJECTIVE", serialized)
            self.assertNotIn("PRIVATE_TEST", serialized)
            self.assertNotIn("PRIVATE_CODE_ARTIFACT", serialized)
            self.assertEqual(snap["summary"]["accepted"], 1)

            server = multi_cockpit.make_server(root, port=0)
            thread = threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True)
            thread.start()
            try:
                conn = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                conn.request("GET", "/api/snapshot.json", headers={"Host": f"127.0.0.1:{server.server_port}"})
                resp = conn.getresponse()
                self.assertEqual(resp.status, 200)
                conn.close()

                bad = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                bad.request("GET", "/api/snapshot.json", headers={"Host": "evil.example:80"})
                self.assertEqual(bad.getresponse().status, 403)
                bad.close()
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()

    def test_project_kit_scaffolds_isolated_external_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "saas-bot"
            rc = project_kit.main([
                "scaffold", "--project", "saas-bot",
                "--repository", "khalidd692/saas-bot",
                "--directory", str(target),
            ])
            self.assertEqual(rc, 0)
            loaded = project_kit.load(target)
            self.assertEqual(loaded.profile["project"], "saas-bot")
            self.assertTrue(loaded.memory.is_dir())


if __name__ == "__main__":
    unittest.main()
