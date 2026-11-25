"""Exhaustive regression test suite covering all 23+ ChatGPT P0/P1 audit scenarios."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.agents.automation import (
    autonomous_project_runner as runner,
    local_deterministic_tools as tools,
    provider_router,
)
from scripts.agents.intelligence.memory import MemoryStore
from scripts.agents.native.provider import ProviderError


def _write_and_hash(path: Path, text: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"artifact": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


class UltimateAuditRegressionTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # Scenarios 1-6: Requirements Manifest, Plan Verification, DAG, Coherence
    # ------------------------------------------------------------------
    def test_01_02_03_manifest_catches_omitted_requirement_missing_file_and_missing_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            goal = "Build local web app with app_srv.py, web/index.html, start.ps1, README.md and unittest tests"
            mf = runner.build_requirements_manifest(goal, project_slug="notes-demo")
            req_ids = {r["id"] for r in mf["requirements"]}
            self.assertIn("REQ-CORE", req_ids)
            self.assertIn("REQ-HTTP-SERVER", req_ids)
            self.assertIn("REQ-WEB-HTML", req_ids)
            self.assertIn("REQ-STARTUP-PS1", req_ids)
            self.assertIn("REQ-DOC-README", req_ids)
            self.assertIn("REQ-TESTS", req_ids)
            self.assertTrue(any(r.get("expected_file") == "app_srv.py" for r in mf["requirements"]))

            # Plan missing explicit file `app_srv.py`, HTML, and tests must FAIL independent plan verification
            incomplete_plan = runner.validate_and_normalize_plan(
                {
                    "summary": "Incomplete plan",
                    "missions": [
                        {
                            "id": "m1",
                            "specialist": "tel99-dev",
                            "target_file": "other.py",
                            "dependencies": [],
                            "objective": "Implement minimal helper function only.",
                        }
                    ],
                },
                project_root=root,
                project_slug="notes-demo",
                goal_text="",
                manifest=mf,
            )
            self.assertFalse(incomplete_plan["plan_verification"]["ok"])
            joined = " ".join(incomplete_plan["plan_verification"]["issues"])
            self.assertIn("REQ-TESTS", joined)
            self.assertIn("app_srv.py", joined)

    def test_04_05_06_rejects_unknown_self_cyclic_deps_and_symbol_extension_incoherence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Unknown dependency MUST be rejected (never silently dropped)
            with self.assertRaisesRegex(ValueError, "unknown dependency"):
                runner.validate_and_normalize_plan(
                    {
                        "missions": [
                            {
                                "id": "m1",
                                "specialist": "tel99-dev",
                                "target_file": "core.py",
                                "dependencies": ["ghost-mission"],
                                "objective": "Implement core module logic cleanly.",
                            }
                        ]
                    },
                    project_root=root,
                    project_slug="dep-test",
                )

            # Self-referential dependency MUST be rejected
            with self.assertRaisesRegex(ValueError, "self-referential"):
                runner.validate_and_normalize_plan(
                    {
                        "missions": [
                            {
                                "id": "m1",
                                "specialist": "tel99-dev",
                                "target_file": "core.py",
                                "dependencies": ["m1"],
                                "objective": "Implement core module logic cleanly.",
                            }
                        ]
                    },
                    project_root=root,
                    project_slug="dep-test",
                )

            # Cyclic dependency MUST be rejected
            with self.assertRaisesRegex(ValueError, "cycle"):
                runner.validate_and_normalize_plan(
                    {
                        "missions": [
                            {
                                "id": "m1",
                                "specialist": "tel99-dev",
                                "target_file": "a.py",
                                "dependencies": ["m2"],
                                "objective": "Implement module A depending on B.",
                            },
                            {
                                "id": "m2",
                                "specialist": "tel99-dev",
                                "target_file": "b.py",
                                "dependencies": ["m1"],
                                "objective": "Implement module B depending on A.",
                            },
                        ]
                    },
                    project_root=root,
                    project_slug="cyc-test",
                )

            # Incoherent Python class symbol on JSON data file MUST be rejected
            with self.assertRaisesRegex(ValueError, "incoherent symbol"):
                runner.validate_and_normalize_plan(
                    {
                        "missions": [
                            {
                                "id": "m-data",
                                "specialist": "tel99-dev",
                                "target_file": "data/store.json",
                                "dependencies": [],
                                "required_symbols": ["BudgetManager"],
                                "objective": "Create empty initial JSON store file.",
                            }
                        ]
                    },
                    project_root=root,
                    project_slug="coh-test",
                )

            # Unsupported extension MUST be rejected
            with self.assertRaisesRegex(ValueError, "unsupported file extension"):
                runner.validate_and_normalize_plan(
                    {
                        "missions": [
                            {
                                "id": "m-bin",
                                "specialist": "tel99-dev",
                                "target_file": "dropper.exe",
                                "dependencies": [],
                                "objective": "Create binary executable file.",
                            }
                        ]
                    },
                    project_root=root,
                    project_slug="ext-test",
                )

    # ------------------------------------------------------------------
    # Scenario 7: Goal/Scope Mismatch & Sealed Plan Revisions
    # ------------------------------------------------------------------
    def test_07_goal_mismatch_blocked_and_versioned_revision_preserves_unaffected_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "rev-proj"
            plan_v1 = {
                "summary": "V1 calc",
                "missions": [
                    {
                        "id": "m-core",
                        "specialist": "tel99-dev",
                        "target_file": "core.py",
                        "dependencies": [],
                        "required_symbols": ["add_num"],
                        "objective": "Implement add_num(a, b) rejecting bools.",
                    },
                    {
                        "id": "m-tests",
                        "specialist": "tel99-verifier",
                        "target_file": "tests/test_core.py",
                        "dependencies": ["m-core"],
                        "required_symbols": ["TestCore"],
                        "objective": "Write unittest for add_num.",
                    },
                ],
            }
            executed: list[str] = []

            def fake_exec(m: dict) -> dict:
                executed.append(m["id"])
                p = Path(m["workspace_root"]) / m["target_file"]
                if m["target_file"] == "core.py":
                    out = _write_and_hash(p, "def add_num(a, b):\n    if isinstance(a, bool) or isinstance(b, bool): raise ValueError('bool')\n    return a + b\n")
                else:
                    out = _write_and_hash(p, "import unittest\nfrom core import add_num\nclass TestCore(unittest.TestCase):\n    def test_add(self): self.assertEqual(add_num(1, 2), 3)\n")
                return {**out, "specialist_id": m["specialist"], "model": "stub", "target_file": m["target_file"]}

            d1 = runner.run_autonomous_project(
                goal_text="Create calc module with unittest",
                project_dir=proj,
                require_sandbox=False,
                plan_override=plan_v1,
                custom_executor=fake_exec,
            )
            self.assertTrue(d1["ok"])
            self.assertEqual(executed, ["m-core", "m-tests"])

            # Different goal without allow_plan_revision -> BLOCKED
            d_mismatch = runner.run_autonomous_project(
                goal_text="Completely different goal with extra README",
                project_dir=proj,
                require_sandbox=False,
                custom_executor=fake_exec,
            )
            self.assertFalse(d_mismatch["ok"])
            self.assertEqual(d_mismatch["reason"], "goal_or_scope_mismatch")

            # Versioned revision adding README preserves already-ACCEPTED m-core & m-tests!
            plan_v2 = {
                **plan_v1,
                "missions": [
                    *plan_v1["missions"],
                    {
                        "id": "m-doc",
                        "specialist": "tel99-documentation",
                        "target_file": "README.md",
                        "dependencies": ["m-tests"],
                        "objective": "Write concise README documentation >= 200 chars.",
                    },
                ],
            }

            def fake_exec_v2(m: dict) -> dict:
                if m["target_file"] == "README.md":
                    executed.append(m["id"])
                    p = Path(m["workspace_root"]) / "README.md"
                    out = _write_and_hash(p, "# Calc Demo\n\n" + ("Documentation complete et verifiable. " * 8) + "\n")
                    return {**out, "specialist_id": m["specialist"], "model": "stub", "target_file": "README.md"}
                return fake_exec(m)

            d2 = runner.run_autonomous_project(
                goal_text="Create calc module with unittest and README",
                project_dir=proj,
                require_sandbox=False,
                allow_plan_revision=True,
                plan_override=plan_v2,
                custom_executor=fake_exec_v2,
            )
            self.assertTrue(d2["ok"], d2)
            self.assertEqual(d2["plan_revision"], 2)
            self.assertIn("m-core", d2["revision_summary"]["preserved"])
            self.assertEqual(executed, ["m-core", "m-tests", "m-doc"])

    # ------------------------------------------------------------------
    # Scenarios 8-10: Zero False DELIVERED, HTTP E2E Probe & Bounded Global Replan
    # ------------------------------------------------------------------
    def test_08_09_false_delivered_blocked_on_bad_http_server_and_zero_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "bad-srv"
            plan = {
                "summary": "Broken server",
                "server_entry": "srv.py",
                "missions": [
                    {
                        "id": "m-srv",
                        "specialist": "tel99-dev",
                        "target_file": "srv.py",
                        "dependencies": [],
                        "required_symbols": ["make_server"],
                        "objective": "Implement HTTP server with make_server returning 500.",
                    },
                    {
                        "id": "m-test",
                        "specialist": "tel99-verifier",
                        "target_file": "tests/test_srv.py",
                        "dependencies": ["m-srv"],
                        "required_symbols": ["TestSrv"],
                        "objective": "Write trivial unit test.",
                    },
                ],
            }

            def broken_srv_exec(m: dict) -> dict:
                p = Path(m["workspace_root"]) / m["target_file"]
                if m["target_file"] == "srv.py":
                    code = (
                        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                        "class H(BaseHTTPRequestHandler):\n"
                        "    def do_GET(self):\n"
                        "        self.send_response(500); self.end_headers(); self.wfile.write(b'boom')\n"
                        "    def log_message(self, *a): pass\n"
                        "def make_server(root=None, host='127.0.0.1', port=0):\n"
                        "    return HTTPServer((host, port), H)\n"
                    )
                    out = _write_and_hash(p, code)
                else:
                    code = "import unittest\nclass TestSrv(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n"
                    out = _write_and_hash(p, code)
                return {**out, "specialist_id": m["specialist"], "model": "stub", "target_file": m["target_file"]}

            d = runner.run_autonomous_project(
                goal_text="Build local HTTP server with unittest",
                project_dir=proj,
                require_sandbox=False,
                max_replan_rounds=0,
                plan_override=plan,
                custom_executor=broken_srv_exec,
            )
            self.assertFalse(d["ok"])
            self.assertNotEqual(d["status"], "DELIVERED")
            self.assertFalse(d["post_build_verification"]["server_e2e_ok"])

    def test_10_bounded_global_replan_fixes_integration_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "replan-srv"
            plan = {
                "summary": "Server repaired in global replan round",
                "server_entry": "srv.py",
                "missions": [
                    {
                        "id": "m-srv",
                        "specialist": "tel99-dev",
                        "target_file": "srv.py",
                        "dependencies": [],
                        "required_symbols": ["make_server"],
                        "objective": "Implement loopback HTTP server serving / and 404.",
                    },
                    {
                        "id": "m-test",
                        "specialist": "tel99-verifier",
                        "target_file": "tests/test_srv.py",
                        "dependencies": ["m-srv"],
                        "required_symbols": ["TestSrv"],
                        "objective": "Write unit test for server module.",
                    },
                ],
            }
            srv_runs = {"n": 0}

            def replan_exec(m: dict) -> dict:
                p = Path(m["workspace_root"]) / m["target_file"]
                if m["target_file"] == "srv.py":
                    srv_runs["n"] += 1
                    if srv_runs["n"] == 1:
                        # First pass returns 200 for everything (fails negative 404 E2E check!)
                        code = (
                            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                            "class H(BaseHTTPRequestHandler):\n"
                            "    def do_GET(self):\n"
                            "        self.send_response(200); self.end_headers(); self.wfile.write(b'<html><body>ok</body></html>')\n"
                            "    def log_message(self, *a): pass\n"
                            "def make_server(root=None, host='127.0.0.1', port=0):\n"
                            "    return HTTPServer((host, port), H)\n"
                        )
                    else:
                        # Second pass (integration replan round 1) fixes 404 properly!
                        code = (
                            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                            "class H(BaseHTTPRequestHandler):\n"
                            "    def do_GET(self):\n"
                            "        if self.path == '/':\n"
                            "            self.send_response(200); self.end_headers(); self.wfile.write(b'<html><body>ok</body></html>')\n"
                            "        else:\n"
                            "            self.send_response(404); self.end_headers(); self.wfile.write(b'not found')\n"
                            "    def log_message(self, *a): pass\n"
                            "def make_server(root=None, host='127.0.0.1', port=0):\n"
                            "    return HTTPServer((host, port), H)\n"
                        )
                    out = _write_and_hash(p, code)
                else:
                    out = _write_and_hash(p, "import unittest\nimport srv\nclass TestSrv(unittest.TestCase):\n    def test_exists(self): self.assertTrue(callable(srv.make_server))\n")
                return {**out, "specialist_id": m["specialist"], "model": "stub", "target_file": m["target_file"]}

            d = runner.run_autonomous_project(
                goal_text="Build local HTTP server with unittest",
                project_dir=proj,
                require_sandbox=False,
                max_replan_rounds=2,
                plan_override=plan,
                custom_executor=replan_exec,
            )
            self.assertTrue(d["ok"], d)
            self.assertEqual(d["status"], "DELIVERED")
            self.assertEqual(d["replan_rounds_used"], 1)
            self.assertEqual(srv_runs["n"], 2)

    # ------------------------------------------------------------------
    # Scenarios 11-14: AST-Only Symbols, Bool Guard, Legit __main__, Path Hardening
    # ------------------------------------------------------------------
    def test_11_12_13_14_ast_symbols_bool_guard_main_preserve_and_path_hardening(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 11: Symbol in comment MUST NOT satisfy AST symbol requirement!
            (root / "comment_cheat.py").write_text("# def required_fn(): pass\nx = 1\n", encoding="utf-8")
            v = runner.verify_delivered_file(root, "comment_cheat.py", required_symbols=["required_fn"], require_sandbox=False)
            self.assertFalse(v["ok"])
            self.assertIn("missing required AST symbols", v["error"])

            # 12: Strict bool guard
            with self.assertRaises(ValueError):
                tools.require_int(True, name="count")
            with self.assertRaises(ValueError):
                tools.require_number(False, name="amount")

            # 13: Legitimate __main__ server/CLI block PRESERVED; trivial demo/truncated block stripped
            legit_srv = (
                "import argparse\n"
                "def run_server(port: int = 8080):\n"
                "    return port\n"
                "if __name__ == '__main__':\n"
                "    p = argparse.ArgumentParser()\n"
                "    run_server(8080)\n"
            )
            cleaned_legit = tools.strip_trailing_example_blocks(legit_srv)
            self.assertIn("if __name__ == '__main__':", cleaned_legit)
            self.assertIn("argparse.ArgumentParser()", cleaned_legit)

            demo_stub = (
                "def add(a, b):\n"
                "    return a + b\n"
                "if __name__ == '__main__':\n"
                "    print(add(1, 2))\n"
            )
            cleaned_demo = tools.strip_trailing_example_blocks(demo_stub)
            self.assertNotIn("print(add(1, 2))", cleaned_demo)

            # 14: Windows reserved device names + protected kit dirs blocked
            for bad in ("CON.py", "nul.json", "sub/PRN.txt", "COM1.py", "LPT9.md"):
                with self.assertRaises(ValueError, msg=f"Should reject Windows device name {bad}"):
                    tools.safe_subpath(root, bad)
            for protected in ("state/hack.py", "memory/poison.json", "artifacts/fake.json", "project.json"):
                with self.assertRaises(ValueError, msg=f"Should reject protected kit path {protected}"):
                    tools.safe_subpath(root, protected, blocked_top_dirs=runner.RESERVED_PROJECT_TOP_DIRS)

    # ------------------------------------------------------------------
    # Scenarios 15-16: Docker OS Sandbox Fail-Closed & Real Live Docker Proof
    # ------------------------------------------------------------------
    def test_15_docker_sandbox_fails_closed_when_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok_mod.py").write_text("def hello():\n    return 42\n", encoding="utf-8")
            with mock.patch.object(runner, "check_docker_sandbox_ready", return_value=(False, "local Docker is unavailable")):
                v = runner.verify_delivered_file(root, "ok_mod.py", require_sandbox=True)
                self.assertFalse(v["ok"])
                self.assertFalse(v["sandbox_used"])
                self.assertIn("sandbox_unavailable", v["error"])

    def test_16_live_docker_sandbox_isolation_and_http_e2e(self):
        ready, _ = runner.check_docker_sandbox_ready()
        if not ready:
            self.skipTest("Pinned Docker sandbox image not available in this CI runner")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 1) Verify real unittest + HTTP E2E works inside Docker with --network none
            (root / "srv.py").write_text(
                "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                "class H(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        if self.path == '/':\n"
                "            self.send_response(200); self.end_headers(); self.wfile.write(b'<html><body><link href=\"/app.css\">ok</body></html>')\n"
                "        elif self.path == '/app.css':\n"
                "            self.send_response(200); self.end_headers(); self.wfile.write(b'body{color:#111}')\n"
                "        else:\n"
                "            self.send_response(404); self.end_headers(); self.wfile.write(b'404')\n"
                "    def log_message(self, *a): pass\n"
                "def make_server(root=None, host='127.0.0.1', port=0):\n"
                "    return HTTPServer((host, port), H)\n",
                encoding="utf-8",
            )
            (root / "tests").mkdir()
            (root / "tests" / "test_sbx.py").write_text(
                "import socket, unittest\n"
                "class TestIsolation(unittest.TestCase):\n"
                "    def test_no_external_network_in_sandbox(self):\n"
                "        s = socket.socket(); s.settimeout(1.0)\n"
                "        with self.assertRaises(OSError):\n"
                "            s.connect(('1.1.1.1', 80))\n"
                "        s.close()\n",
                encoding="utf-8",
            )
            v = runner.verify_delivered_file(root, "tests/test_sbx.py", require_sandbox=True)
            self.assertTrue(v["ok"], v)
            self.assertTrue(v["sandbox_used"])
            post = runner._run_post_build_verification(
                root,
                {"server_entry": "srv.py", "contracts": [{"target_file": "srv.py"}, {"target_file": "tests/test_sbx.py"}]},
                require_sandbox=True,
            )
            self.assertTrue(post["tests_ok"], post)
            self.assertTrue(post["tests_sandbox_used"])
            self.assertTrue(post["server_e2e_ok"], post)
            self.assertTrue(post["server_probe"]["sandbox_used"])

    # ------------------------------------------------------------------
    # Scenarios 17-24: Secrets, Live Progress, Lock Collision, Budget Ledger,
    #                  Infra vs Model Budget, Memory Gate, Honest Attribution, >20 Batching
    # ------------------------------------------------------------------
    def test_17_secret_leak_blocked(self):
        fake_gsk = "gsk_" + ("A1b2C3d4E5f6G7h8I9j0" * 2)
        self.assertFalse(tools.detect_secret_leak(fake_gsk)["safe"])
        pol = tools.check_cloud_escalation_policy(confidential=False, allow_cloud=True, prompt_text=fake_gsk)
        self.assertFalse(pol["allowed"])

    def test_18_19_live_progress_without_delivery_report_and_lock_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "lock-proj"
            kit = runner.ensure_isolated_project_kit(proj)
            plan = runner.validate_and_normalize_plan(
                {
                    "missions": [
                        {
                            "id": "m1",
                            "specialist": "tel99-dev",
                            "target_file": "a.py",
                            "dependencies": [],
                            "objective": "Implement sample function a().",
                        }
                    ]
                },
                project_root=kit.root,
                project_slug=kit.profile["project"],
            )
            tools.write_json_atomic_locked(kit.artifacts / "project_plan.json", plan)

            # Live progress works BEFORE delivery_report.json exists
            prog = runner.get_project_progress(proj)
            self.assertFalse(prog["delivery_exists"])
            self.assertEqual(prog["missions_total"], 1)
            self.assertEqual(prog["runtime_statuses"]["m1"], "PENDING")

            # Holding project_runner.lock blocks concurrent runner with status=LOCKED
            with tools.file_lock(kit.state / "project_runner.lock", timeout_s=2.0):
                res = runner.run_autonomous_project(
                    goal_text="Implement sample function a()",
                    project_dir=proj,
                    require_sandbox=False,
                )
                self.assertFalse(res["ok"])
                self.assertEqual(res["status"], "LOCKED")
                self.assertEqual(res["reason"], "project_runner_already_active")

    def test_20_cloud_budget_ledger_atomic_concurrency_and_corrupted_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            lp = Path(tmp) / "budgets.json"
            ledger = provider_router.CloudBudgetLedger(
                lp, budgets={"groq": {"max_requests_per_day": 5, "max_tokens_per_day": 100_000}}
            )

            def _try_reserve(_i: int) -> bool:
                ok, _reason, _tok = ledger.reserve_budget("groq", estimated_tokens=500)
                return ok

            with ThreadPoolExecutor(max_workers=10) as pool:
                results = list(pool.map(_try_reserve, range(12)))
            self.assertEqual(sum(1 for r in results if r), 5, "Atomic reservation must allow exactly 5/12 concurrent callers")

            # Corrupted ledger JSON MUST fail closed (never silently reset to 0!)
            lp.write_text("{corrupted_json!!!", encoding="utf-8")
            ok_call, reason = ledger.can_call("groq", estimated_tokens=100)
            self.assertFalse(ok_call)
            self.assertIn("corrupted", reason)
            ok_res, r_res, tok = ledger.reserve_budget("groq", estimated_tokens=100)
            self.assertFalse(ok_res)
            self.assertIsNone(tok)
            self.assertIn("corrupted", r_res)

    def test_21_22_23_infra_budget_memory_gate_and_honest_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "infra-mem-proj"
            plan = {
                "summary": "Infra retry + memory gate test",
                "missions": [
                    {
                        "id": "m-core",
                        "specialist": "tel99-dev",
                        "target_file": "core.py",
                        "dependencies": [],
                        "required_symbols": ["ok_fn"],
                        "objective": "Implement ok_fn() returning True.",
                    },
                    {
                        "id": "m-test",
                        "specialist": "tel99-verifier",
                        "target_file": "tests/test_core.py",
                        "dependencies": ["m-core"],
                        "required_symbols": ["TestOk"],
                        "objective": "Write failing test on purpose to test memory gate.",
                    },
                ],
            }
            call_seq = {"n": 0}

            def fake_call_model(**kwargs):
                call_seq["n"] += 1
                # First call raises transient ProviderError (should use infra budget, NOT fail mission!)
                if call_seq["n"] == 1:
                    raise ProviderError("Ollama temporarily busy")
                if "core.py" in kwargs["prompt"]:
                    return "```python\ndef ok_fn():\n    return True\n```", "ollama", "gemma4", 0, {}
                # Test mission always returns failing test so delivery ends PARTIAL
                return "```python\nimport unittest\nclass TestOk(unittest.TestCase):\n    def test_fail(self): self.assertEqual(1, 2)\n```", "ollama", "gemma4", 0, {}

            with mock.patch.object(runner, "_call_model", side_effect=fake_call_model):
                d = runner.run_autonomous_project(
                    goal_text="Implement core.py with unittest",
                    project_dir=proj,
                    require_sandbox=False,
                    max_replan_rounds=0,
                    plan_override=plan,
                )
            # 21: m-core succeeded despite transient ProviderError on call #1!
            self.assertEqual(d["runtime_statuses"]["m-core"], "ACCEPTED")
            self.assertEqual(d["missions"]["m-core"]["infra_failures"], 1)
            # 22: Overall status is PARTIAL -> ZERO lessons promoted to kit.memory!
            self.assertEqual(d["status"], "PARTIAL")
            self.assertEqual(d["promoted_memory_lessons"], 0)
            mem = MemoryStore(proj / "memory")
            self.assertIsNone(mem.get(d["project"], "proc-m-core"))
            # 23: Honest attribution — tel99-security was NEVER called via LLM so MUST NOT be in agents_called!
            self.assertNotIn("tel99-security", d["agents_called"])
            self.assertIn("tel99-dev", d["agents_called"])
            self.assertIn("deterministic_security_gate", d["deterministic_verifiers_run"])

    def test_24_large_project_over_20_missions_runs_in_bounded_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "batch-22"
            missions = [
                {
                    "id": f"mod-{i:02d}",
                    "specialist": "tel99-dev",
                    "target_file": f"pkg/m{i:02d}.py",
                    "dependencies": [f"mod-{i-1:02d}"] if i > 1 else [],
                    "required_symbols": [f"fn_{i}"],
                    "objective": f"Implement function fn_{i}() returning {i}.",
                }
                for i in range(1, 22)
            ]
            missions.append({
                "id": "mod-tests",
                "specialist": "tel99-verifier",
                "target_file": "tests/test_pkg.py",
                "dependencies": ["mod-21"],
                "required_symbols": ["TestPkg"],
                "objective": "Write unit test verifying pkg.m21.fn_21().",
            })

            def batch_exec(m: dict) -> dict:
                p = Path(m["workspace_root"]) / m["target_file"]
                if m["target_file"].startswith("pkg/"):
                    idx = int(m["id"].split("-")[1])
                    out = _write_and_hash(p, f"def fn_{idx}():\n    return {idx}\n")
                else:
                    out = _write_and_hash(p, "import unittest\nfrom pkg.m21 import fn_21\nclass TestPkg(unittest.TestCase):\n    def test_21(self): self.assertEqual(fn_21(), 21)\n")
                return {**out, "specialist_id": m["specialist"], "model": "stub", "target_file": m["target_file"]}

            d = runner.run_autonomous_project(
                goal_text="Build 21 modular Python files with unittest suite",
                project_dir=proj,
                require_sandbox=False,
                plan_override={"summary": "22-file batch test", "missions": missions},
                custom_executor=batch_exec,
            )
            self.assertTrue(d["ok"], d)
            self.assertEqual(d["missions_accepted"], 22)
            self.assertEqual(d["missions_total"], 22)


if __name__ == "__main__":
    unittest.main()
