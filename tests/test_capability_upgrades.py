"""Offline unit tests for TEL99 global agent capability upgrades.

Covers:
- Adaptive Ollama budgets & RAM safety clamping + fence extraction
- Auto-decomposition & dynamic re-planning after failure (preserving completed_ids)
- Smart repair (bounded diff, self-critique checklist, anti-repeat SHA-256, strategy escalation)
- Specialty-aware multi-model local routing & zero-paid fallback selection
- Native multi-project / multi-file contracts (`owner == "project-file"`) + 6-class error taxonomy
- 12-role specialist governance metadata (`specialist_dispatch`)
- Scoped & verified memory retrieval (`learning_loop.retrieve_scoped_lessons`)
- Agent Academy curriculum, improvement gate (`PROMOTE`/`ROLLBACK`), and versioned profile rollback
- Real cockpit metrics (`first_pass_rate`, `final_success_rate`, `skills_count`, `academy_summary`)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_DIR = ROOT / "scripts" / "agents" / "automation"
for p in (str(ROOT), str(AUTOMATION_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.agents import specialist_dispatch
from scripts.agents.automation import (
    agent_academy,
    autonomy_runtime,
    learning_loop,
    mission_planner,
    multi_cockpit,
    ollama_native,
    provider_router,
    smart_repair,
)
from scripts.agents.intelligence.memory import COMMON_PROJECT, Entry, MemoryStore


class CapabilityUpgradeTests(unittest.TestCase):
    def test_adaptive_budget_scales_safely_with_profile_and_ram(self):
        patch_b = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="patch", available_memory_mib=4000)
        self.assertLessEqual(patch_b["max_tokens"], 1024)
        self.assertLessEqual(patch_b["timeout"], 90)

        mod_b = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="module", estimated_lines=95, available_memory_mib=4000)
        self.assertEqual(mod_b["max_tokens"], 2048)
        self.assertGreater(mod_b["timeout"], 90)

        large_ok = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="large_module", estimated_lines=180, available_memory_mib=4500)
        self.assertEqual(large_ok["max_tokens"], 4096)

        large_low_ram = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="large_module", estimated_lines=180, available_memory_mib=1600)
        self.assertLessEqual(large_low_ram["max_tokens"], 2048)
        self.assertTrue(large_low_ram["ram_clamped"])

        # Resident 7.5B model leaving ~1200 MiB free must NOT falsely clamp module down to 90s patch
        mod_resident = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="module", estimated_lines=65, available_memory_mib=1200)
        self.assertEqual(mod_resident["effective_profile"], "module")
        self.assertFalse(mod_resident["ram_clamped"])
        self.assertGreater(mod_resident["timeout"], 90)

        # True OOM danger (< 700 MiB) must still clamp module down to safe patch
        mod_oom = ollama_native.compute_adaptive_budget("gemma4:e4b-tel99-8k", task_profile="module", estimated_lines=65, available_memory_mib=600)
        self.assertEqual(mod_oom["effective_profile"], "patch")
        self.assertTrue(mod_oom["ram_clamped"])

    def test_extract_code_block_handles_closed_and_truncated_fences(self):
        closed = "Here is code:\n```python\ndef f(x):\n    return x + 1\n```\nDone."
        self.assertEqual(ollama_native.extract_code_block(closed).strip(), "def f(x):\n    return x + 1")
        truncated = "```python\ndef f(x):\n    return x + 1"
        self.assertEqual(ollama_native.extract_code_block(truncated).strip(), "def f(x):\n    return x + 1")

    def test_ollama_provider_preserves_legacy_patch_limits_and_allows_module_profile(self):
        with self.assertRaises(ollama_native.ProviderError):
            ollama_native.OllamaNativeProvider(model="gemma4:e4b-tel99-8k", max_tokens=2048, timeout=90)
        p = ollama_native.OllamaNativeProvider(model="gemma4:e4b-tel99-8k", max_tokens=2048, timeout=220, task_profile="module")
        self.assertEqual(p.max_tokens, 2048)
        self.assertEqual(p.timeout, 220)

        # Seamless continuation join must not break mid-line comma/assignment into unexpected indent
        calls = iter(["def f():\n    a,", "b = 1, 2\n    return a + b\n"])
        def _fake_complete(*, system: str, prompt: str) -> str:
            out = next(calls)
            p.last_metadata = {"done_reason": "length" if out.endswith(",") else "stop"}
            return out
        p.complete = _fake_complete  # type: ignore[method-assign]
        joined = p.complete_with_continuation(system="s", prompt="p", max_continuations=1)
        self.assertIn("a, b = 1, 2", joined)

    def test_mission_planner_auto_decomposes_and_revises_after_failure(self):
        big_task = {
            "id": "radar-engine",
            "path": "app/radar_engine.py",
            "estimated_lines": 150,
            "functions": ["load_dataset", "search_models", "compare_models", "check_pc_compatibility", "recommend_models", "import_payload"],
            "objective": "Implement all 6 functions for AI Radar.",
        }
        plan = mission_planner.assess_and_decompose_mission(big_task, model_id="local/ollama-gemma4-e4b", max_safe_lines=65)
        self.assertTrue(plan["needs_decomposition"])
        self.assertEqual(len(plan["subtasks"]), 3)
        self.assertEqual(plan["subtasks"][0]["dependencies"], [])
        self.assertEqual(plan["subtasks"][1]["dependencies"], [plan["subtasks"][0]["id"]])
        self.assertEqual(plan["subtasks"][2]["dependencies"], [plan["subtasks"][1]["id"]])

        # Revise only a failed task while preserving already completed tasks
        tasks = [
            {"id": "step-1", "path": "app/a.py", "functions": ["f1"], "estimated_lines": 30, "dependencies": []},
            {
                "id": "step-2",
                "path": "app/b.py",
                "functions": ["g1", "g2", "g3", "g4"],
                "estimated_lines": 120,
                "dependencies": ["step-1"],
                "objective": "Build g1..g4",
            },
            {"id": "step-3", "path": "app/c.py", "functions": ["h1"], "estimated_lines": 30, "dependencies": ["step-2"]},
        ]
        revised = mission_planner.revise_plan_after_failure(
            tasks,
            failed_id="step-2",
            error_class="ENVIRONMENT_ERROR",
            completed_ids={"step-1"},
        )
        self.assertEqual(revised["action"], "split_failed_task")
        self.assertEqual(revised["preserved_completed"], ["step-1"])
        self.assertGreater(len(revised["subtasks"]), len(tasks))
        self.assertEqual(revised["subtasks"][0]["id"], "step-1")
        self.assertEqual(revised["subtasks"][1]["dependencies"], ["step-1"])
        self.assertEqual(revised["subtasks"][-1]["id"], "step-3")
        self.assertEqual(revised["subtasks"][-1]["dependencies"], [revised["subtasks"][-2]["id"]])

    def test_smart_repair_bounds_errors_diff_checklist_and_strategy(self):
        fp1 = smart_repair.code_fingerprint("def f():\n    return 1  \n")
        self.assertTrue(smart_repair.detect_repeated_attempt("def f():\n    return 1\n", [fp1]))
        self.assertFalse(smart_repair.detect_repeated_attempt("def f():\n    return 2\n", [fp1]))

        diff = smart_repair.compute_bounded_diff("def f():\n    return 1\n", "def f():\n    return 2\n")
        self.assertIn("-    return 1", diff)
        self.assertIn("+    return 2", diff)

        checklist = smart_repair.build_self_critique_checklist("tel99-mobile", "app/ui.js")
        self.assertIn("Balanced braces/tags", checklist)

        prompt = smart_repair.build_smart_repair_prompt(
            previous_code="def f():\n    return 1",
            exact_error="E" * 10000,
            passed_checks=["syntax", "security"],
            failed_checks=["behavior"],
            prior_attempts=[{"attempt": 1, "code_sha256": fp1, "error": "wrong return"}],
            memory_lessons=["Return int 2"],
            previous_diff=diff,
            target_file="app/f.py",
        )
        self.assertLess(len(prompt), 3600)
        self.assertIn("DO NOT REPEAT", prompt)
        self.assertIn("Checks already PASSING", prompt)
        self.assertIn("Previous diff", prompt)

        self.assertEqual(
            smart_repair.suggest_repair_strategy([{"attempt": 1, "repeated": True}], "gemma4:e4b-tel99-8k")["strategy"],
            "switch_local_model",
        )
        self.assertEqual(
            smart_repair.suggest_repair_strategy(
                [{"attempt": 1, "done_reason": "length"}, {"attempt": 2, "done_reason": "length"}],
                "gemma4:e4b-tel99-8k",
            )["strategy"],
            "decompose_task",
        )
        self.assertEqual(
            smart_repair.suggest_repair_strategy([{"attempt": 1, "repeated": False}], "gemma4:e4b-tel99-8k")["strategy"],
            "targeted_patch",
        )

    def test_provider_router_specialty_and_local_free_fallback(self):
        probe = {
            "providers": {
                "ollama": {
                    "billing_class": "LOCAL_FREE",
                    "available": True,
                    "quota_status": "READY",
                    "models": [
                        {
                            "id": "local/ollama-gemma4-e4b",
                            "provider": "ollama",
                            "served_model": "gemma4:e4b-tel99-8k",
                            "role_tier": "executor",
                            "latency_tier": "fast",
                            "quality_prior": 0.78,
                        },
                        {
                            "id": "local/ollama-qwen3.5-9b",
                            "provider": "ollama",
                            "served_model": "qwen3.5:9b-q4_K_M",
                            "role_tier": "executor",
                            "latency_tier": "medium",
                            "quality_prior": 0.78,
                        },
                    ],
                },
                "codex": {
                    "billing_class": "SUBSCRIPTION_OPT_IN",
                    "available": True,
                    "quota_status": "READY",
                    "models": [{"id": "gpt-5.4", "provider": "codex", "served_model": "gpt-5.4", "quality_prior": 0.95}],
                },
            }
        }
        sel = provider_router.select_executor_for_specialty("documentation", difficulty="medium", inventory=probe)
        self.assertTrue(sel["ok"])
        self.assertEqual(sel["specialty"], "documentation")
        self.assertEqual(sel["chosen"]["id"], "local/ollama-gemma4-e4b")
        self.assertEqual(sel["chosen"]["billing_class"], "LOCAL_FREE")

        fb = provider_router.select_fallback_model(
            ("gemma4:e4b-tel99-8k",),
            specialty="python",
            inventory=probe,
        )
        self.assertTrue(fb["ok"])
        self.assertEqual(fb["chosen"]["provider"], "ollama")
        self.assertEqual(fb["chosen"]["served_model"], "qwen3.5:9b-q4_K_M")
        self.assertEqual(fb["chosen"]["billing_class"], "LOCAL_FREE")

        # Excluding all local models must NOT fall back to subscription/paid codex
        fb_none = provider_router.select_fallback_model(
            ("gemma4:e4b-tel99-8k", "qwen3.5:9b-q4_K_M"),
            specialty="python",
            inventory=probe,
        )
        self.assertFalse(fb_none["ok"])
        self.assertIsNone(fb_none["chosen"])

    def test_autonomy_runtime_error_taxonomy_and_project_file_contract(self):
        self.assertEqual(autonomy_runtime.classify_failure("CASConflict lease collision"), "COORDINATION_ERROR")
        self.assertEqual(autonomy_runtime.classify_failure("path traversal outside allowed"), "CONTRACT_ERROR")
        self.assertEqual(autonomy_runtime.classify_failure("HTTP 429 quota exceeded"), "PROVIDER_ERROR")
        self.assertEqual(autonomy_runtime.classify_failure("Docker timeout OOM low RAM"), "ENVIRONMENT_ERROR")
        self.assertEqual(autonomy_runtime.classify_failure("verifier assertion SyntaxError"), "VERIFICATION_ERROR")
        self.assertEqual(autonomy_runtime.classify_failure("wrong return value"), "MODEL_ERROR")

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "proj"
            ws.mkdir()
            valid = {
                "id": "demo-mod-1",
                "owner": "project-file",
                "project": "demo-app",
                "specialist": "tel99-dev",
                "priority": "P1",
                "dependencies": [],
                "objective": "Create app/calc.py with add(a, b).",
                "workspace_root": str(ws),
                "allowed_paths": ["app/calc.py"],
                "target_file": "app/calc.py",
                "task_profile": "module",
                "max_attempts": 2,
            }
            self.assertTrue(autonomy_runtime.validate_project_file_contract(valid))

            bad_traversal = {**valid, "allowed_paths": ["../escape.py"], "target_file": "../escape.py"}
            with self.assertRaises(ValueError):
                autonomy_runtime.validate_project_file_contract(bad_traversal)

            bad_outside = {**valid, "target_file": "app/other.py"}
            with self.assertRaises(ValueError):
                autonomy_runtime.validate_project_file_contract(bad_outside)

            bad_specialist = {**valid, "specialist": "unknown-bot"}
            with self.assertRaises(ValueError):
                autonomy_runtime.validate_project_file_contract(bad_specialist)

            # End-to-end Runtime.run_queue with owner="project-file"
            state_dir = Path(tmp) / "state"
            code = "def add(a, b):\n    return a + b\n"
            code_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()

            def fake_exec(m):
                out_file = Path(m["workspace_root"]) / m["target_file"]
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(code, encoding="utf-8")
                return {"artifact": code, "sha256": code_sha, "model": "gemma4:e4b-tel99-8k"}

            def fake_verify(m, res):
                return {
                    "ok": True,
                    "verifier": "demo-independent-verifier-v1",
                    "project": m["project"],
                    "target_file": m["target_file"],
                    "artifact_sha256": res["sha256"],
                    "checks": [{"name": "unit", "ok": True}],
                }

            rt = autonomy_runtime.Runtime(state_dir, executor=fake_exec, verifier=fake_verify)
            rt.run_queue([valid], autonomy_runtime.seal([valid]))
            st = rt.status()["missions"]["demo-mod-1"]
            self.assertEqual(st["status"], "ACCEPTED")
            mem = MemoryStore(state_dir / "memory")
            entry = mem.get("demo-app", "demo-mod-1")
            self.assertIsNotNone(entry)
            self.assertIn("app/calc.py", entry.body)

    def test_specialist_dispatch_all_12_roles_metadata_and_audit(self):
        audit = specialist_dispatch.audit_all_specialists()
        self.assertEqual(audit["total"], 12)
        self.assertTrue(audit["all_ok"])
        rows = specialist_dispatch.list_specialists()
        for row in rows:
            self.assertTrue(row["specialty"])
            self.assertTrue(row["memory_scope"])
            self.assertTrue(row["delegation_rules"])
            self.assertTrue(row["escalation_rule"])
            self.assertTrue(row["repair_protocol"])

    def test_learning_loop_scoped_and_verified_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_root = Path(tmp) / "memory"
            store = MemoryStore(mem_root)
            store.record(Entry(
                id="fix-1", project="ai-radar", kind="fix",
                title="Fix radar server port", body="Always bind 127.0.0.1 in radar server",
                tags=("radar", "server"), source="test", author="tel99-dev", verified=True, confidence=0.95,
            ))
            store.record(Entry(
                id="err-1", project="ai-radar", kind="error",
                title="Unverified radar server hint", body="Unverified rumor about radar server",
                tags=("radar", "server"), source="test", author="tel99-analyst", verified=False, confidence=0.4,
            ))
            store.record(Entry(
                id="proc-1", project=COMMON_PROJECT, kind="procedure",
                title="Procedure radar server verification", body="Verify radar server endpoints independently",
                tags=("radar", "server"), source="test", author="learning-loop", verified=True, confidence=0.95,
            ))
            res = learning_loop.retrieve_scoped_lessons(
                mem_root,
                "ai-radar",
                {"target_file": "app/server.py", "objective": "radar server"},
                role="tel99-dev",
                verified_only=True,
                limit=3,
            )
            self.assertTrue(res["verified_only"])
            self.assertEqual(len(res["by_scope"]["individual"]), 1)
            self.assertEqual(len(res["by_scope"]["procedural"]), 1)
            self.assertTrue(all("Unverified rumor" not in line for line in res["lessons"]))

    def test_agent_academy_curriculum_gate_and_profile_rollback(self):
        cur = agent_academy.audit_12_roles_curriculum()
        self.assertEqual(cur["total_roles"], 12)
        self.assertGreaterEqual(cur["calibration_count"], 2)
        self.assertGreaterEqual(cur["held_out_count"], 3)

        before = {
            "success_rate": 0.3333,
            "first_pass": 1,
            "results": [
                {"id": "e1", "ok": True},
                {"id": "e2", "ok": False},
                {"id": "e3", "ok": False},
            ],
        }
        after_good = {
            "success_rate": 1.0,
            "first_pass": 3,
            "results": [
                {"id": "e1", "ok": True},
                {"id": "e2", "ok": True},
                {"id": "e3", "ok": True},
            ],
        }
        after_reg = {
            "success_rate": 0.3333,
            "first_pass": 1,
            "results": [
                {"id": "e1", "ok": False},
                {"id": "e2", "ok": True},
                {"id": "e3", "ok": False},
            ],
        }
        self.assertEqual(agent_academy.evaluate_improvement_gate(before, after_good)["decision"], "PROMOTE")
        self.assertEqual(agent_academy.evaluate_improvement_gate(before, after_reg)["decision"], "ROLLBACK")

        with tempfile.TemporaryDirectory() as tmp:
            p1 = agent_academy.snapshot_agent_profile_version(tmp, version_id="v1", profile_data={"budget": 1024})
            agent_academy.snapshot_agent_profile_version(tmp, version_id="v2", profile_data={"budget": 2048})
            self.assertTrue(p1.is_file())
            restored = agent_academy.rollback_agent_profile_version(tmp, target_version="v1")
            self.assertEqual(restored["version_id"], "v1")
            active = json.loads((Path(tmp) / "active_profile.json").read_text(encoding="utf-8"))
            self.assertEqual(active["active_version"], "v1")
            self.assertTrue(active["rolled_back"])

    def test_cockpit_snapshot_surfaces_real_metrics_and_academy_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "learning").mkdir(parents=True)
            (root / "learning" / "academy_summary.json").write_text(
                json.dumps({"model": "gemma4:e4b-tel99-8k", "held_out_rate": 1.0}),
                encoding="utf-8",
            )
            snap = multi_cockpit.build_snapshot(root)
            self.assertIn("first_pass_rate", snap["summary"])
            self.assertIn("final_success_rate", snap["summary"])
            self.assertGreaterEqual(snap["summary"]["skills_count"], 1)
            self.assertEqual(snap["learning"]["academy_summary"]["held_out_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
