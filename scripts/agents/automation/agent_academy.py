"""Agent Academy: progressive reproducible evaluation suite for the 12 TEL99 roles.

Separates calibration exercises from held-out evaluation exercises to prevent
overfitting, and measures before/after success rates, repair rates, and latency.
No model weight training: evaluates prompts, Skills, decomposition, and routing.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

from scripts.agents import specialist_dispatch
from scripts.agents.automation import ollama_native, smart_repair

# Calibration set (used to tune prompts/procedures) — strictly separate from HELD_OUT_EVAL_EXERCISES
CALIBRATION_EXERCISES: list[dict[str, Any]] = [
    {
        "id": "cal-dev-clamp-int",
        "role": "development",
        "difficulty": "easy",
        "task_profile": "patch",
        "objective": (
            "Write a Python function `clamp_int(value, low, high)` that validates int (rejecting bool), "
            "validates low <= high, and returns value clamped to [low, high]."
        ),
        "test_code": (
            "assert clamp_int(5, 0, 10) == 5\n"
            "assert clamp_int(-3, 0, 10) == 0\n"
            "assert clamp_int(99, 0, 10) == 10\n"
            "try:\n    clamp_int(True, 0, 10); assert False\nexcept ValueError:\n    pass\n"
        ),
    },
    {
        "id": "cal-coord-dag-order",
        "role": "coordination",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `plan_ready_tasks(tasks, completed_ids)` where each task is a dict "
            "{'id': str, 'dependencies': list[str]}. Return sorted list of task ids not in completed_ids "
            "whose dependencies are all in completed_ids."
        ),
        "test_code": (
            "tasks = [{'id': 'b', 'dependencies': ['a']}, {'id': 'a', 'dependencies': []}, {'id': 'c', 'dependencies': ['a']}]\n"
            "assert plan_ready_tasks(tasks, set()) == ['a']\n"
            "assert plan_ready_tasks(tasks, {'a'}) == ['b', 'c']\n"
        ),
    },
]

# Held-out evaluation set (unseen during prompt/skill calibration to prevent overfitting)
HELD_OUT_EVAL_EXERCISES: list[dict[str, Any]] = [
    {
        "id": "eval-dev-budget-guard",
        "role": "development",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `enforce_budget(calls, max_calls, free_ram_mb, min_ram_mb=1400)` "
            "returning dict {'allow': bool, 'reason': str}. Reject non-int/bool calls or max_calls<=0 with ValueError; "
            "return allow=False reason='quota_exceeded' if calls>=max_calls; "
            "allow=False reason='low_ram' if free_ram_mb<min_ram_mb; else allow=True reason='ok'."
        ),
        "test_code": (
            "assert enforce_budget(0, 5, 3000) == {'allow': True, 'reason': 'ok'}\n"
            "assert enforce_budget(5, 5, 3000) == {'allow': False, 'reason': 'quota_exceeded'}\n"
            "assert enforce_budget(1, 5, 900) == {'allow': False, 'reason': 'low_ram'}\n"
            "try:\n    enforce_budget(True, 5, 3000); assert False\nexcept ValueError:\n    pass\n"
        ),
    },
    {
        "id": "eval-sec-path-guard",
        "role": "security",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `safe_subpath(root_dir, rel_path)` using pathlib.Path "
            "that resolves both paths and raises ValueError if rel_path is empty, absolute, contains '..', "
            "or resolves outside root_dir. Return resolved Path otherwise."
        ),
        "test_code": (
            "from pathlib import Path\nimport tempfile\n"
            "with tempfile.TemporaryDirectory() as d:\n"
            "    p = safe_subpath(d, 'sub/a.txt')\n"
            "    assert str(p).startswith(str(Path(d).resolve()))\n"
            "    for bad in ('', '../x', '/etc/passwd', 'a/../../b'):\n"
            "        try:\n            safe_subpath(d, bad); assert False\n        except ValueError:\n            pass\n"
        ),
    },
    {
        "id": "eval-eval-freshness",
        "role": "evaluation",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `classify_freshness(age_hours, *, stale_after=24.0, expired_after=168.0)` "
            "that returns 'fresh' if 0 <= age_hours < stale_after, 'stale' if stale_after <= age_hours < expired_after, "
            "'expired' if age_hours >= expired_after, and raises ValueError for None, bool, or negative age_hours."
        ),
        "test_code": (
            "assert classify_freshness(0) == 'fresh'\n"
            "assert classify_freshness(24.0) == 'stale'\n"
            "assert classify_freshness(200) == 'expired'\n"
            "for bad in (None, True, -1):\n"
            "    try:\n        classify_freshness(bad); assert False\n    except ValueError:\n        pass\n"
        ),
    },
    {
        "id": "eval-quant-no-leak-window",
        "role": "quant",
        "difficulty": "hard",
        "task_profile": "module",
        "objective": (
            "Write a Python function `rolling_causal_mean(values, window)` returning a list of floats of the same length "
            "where index i is the mean of values[max(0, i-window+1) : i+1] (strictly causal: NEVER uses future elements j > i), "
            "rounded to 4 decimals. Validate window is int (not bool) >= 1 and values is a non-empty list of int/float (not bool), else raise ValueError."
        ),
        "test_code": (
            "assert rolling_causal_mean([10, 20, 30, 40], 2) == [10.0, 15.0, 25.0, 35.0]\n"
            "assert rolling_causal_mean([1, 2, 3], 3) == [1.0, 1.5, 2.0]\n"
            "for bad in (([], 2), ([1, 2], 0), ([1, True], 2), ([1, 2], True)):\n"
            "    try:\n        rolling_causal_mean(*bad); assert False\n    except ValueError:\n        pass\n"
        ),
    },
    {
        "id": "eval-quality-verdict-gate",
        "role": "quality",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `aggregate_verdict(checks)` where checks is a non-empty list of dicts "
            "{'name': str, 'ok': bool, 'reproducible': bool}. Return dict {'accepted': bool, 'passed': int, 'failed': list[str]}: "
            "accepted is True ONLY if ALL checks have ok is True AND reproducible is True. Raise ValueError if checks is empty or malformed."
        ),
        "test_code": (
            "assert aggregate_verdict([{'name':'a','ok':True,'reproducible':True}]) == {'accepted': True, 'passed': 1, 'failed': []}\n"
            "r = aggregate_verdict([{'name':'a','ok':True,'reproducible':True},{'name':'b','ok':True,'reproducible':False}])\n"
            "assert r == {'accepted': False, 'passed': 1, 'failed': ['b']}\n"
            "try:\n    aggregate_verdict([]); assert False\nexcept ValueError:\n    pass\n"
        ),
    },
    {
        "id": "eval-coord-topo-ready",
        "role": "coordination",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `select_next_batch(tasks, completed, *, max_parallel=1)` where tasks is list of "
            "{'id': str, 'priority': int, 'dependencies': list[str]} and completed is set[str]. Return up to max_parallel task IDs "
            "not in completed whose dependencies are all in completed, sorted by (priority ascending, id ascending). Validate max_parallel >= 1."
        ),
        "test_code": (
            "ts = [{'id':'b','priority':1,'dependencies':['a']},{'id':'a','priority':2,'dependencies':[]},{'id':'c','priority':1,'dependencies':[]}]\n"
            "assert select_next_batch(ts, set(), max_parallel=1) == ['c']\n"
            "assert select_next_batch(ts, {'a','c'}, max_parallel=2) == ['b']\n"
            "try:\n    select_next_batch(ts, set(), max_parallel=0); assert False\nexcept ValueError:\n    pass\n"
        ),
    },
    {
        "id": "eval-cloud-workflow-guard",
        "role": "cloud",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `audit_workflow_permissions(workflow)` where workflow is a dict with optional 'permissions' dict "
            "and 'on' triggers. Return dict {'safe': bool, 'issues': list[str]}: flag issue 'write_all_forbidden' if permissions == 'write-all' "
            "or any value is 'write' for key 'contents' on pull_request_target; flag 'missing_timeout' if any job in workflow.get('jobs', {}) lacks positive int 'timeout-minutes'."
        ),
        "test_code": (
            "ok_wf = {'on': ['push'], 'permissions': {'contents': 'read'}, 'jobs': {'ci': {'timeout-minutes': 15}}}\n"
            "assert audit_workflow_permissions(ok_wf) == {'safe': True, 'issues': []}\n"
            "bad_wf = {'on': ['pull_request_target'], 'permissions': {'contents': 'write'}, 'jobs': {'ci': {}}}\n"
            "res = audit_workflow_permissions(bad_wf)\n"
            "assert res['safe'] is False and 'write_all_forbidden' in res['issues'] and 'missing_timeout' in res['issues']\n"
        ),
    },
    {
        "id": "eval-mobile-responsive-audit",
        "role": "mobile",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `audit_mobile_html(html_text)` returning dict {'ok': bool, 'missing': list[str], 'forbidden': list[str]}. "
            "Check required substrings: '<!doctype html>' (case-insensitive), 'viewport', '<html lang=\"fr\">'. "
            "Flag forbidden patterns (case-insensitive): '<script>' (inline script tag without src), 'javascript:'."
        ),
        "test_code": (
            "good = '<!doctype html><html lang=\"fr\"><head><meta name=\"viewport\" content=\"width=device-width\"></head><body></body></html>'\n"
            "assert audit_mobile_html(good) == {'ok': True, 'missing': [], 'forbidden': []}\n"
            "bad = '<html><body><script>alert(1)</script><a href=\"javascript:void(0)\">x</a></body></html>'\n"
            "r = audit_mobile_html(bad)\n"
            "assert r['ok'] is False and len(r['missing']) >= 2 and len(r['forbidden']) == 2\n"
        ),
    },
    {
        "id": "eval-doc-evidence-lint",
        "role": "documentation",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `lint_evidence_report(markdown_text)` returning dict {'ok': bool, 'issues': list[str]}. "
            "Require at least one heading starting with '# ', at least one status label from ('PROVEN', 'PARTIAL', 'BLOCKED', 'INCONCLUSIVE'), "
            "and reject ungrounded claims containing '100% garanti' or 'profit garanti' (case-insensitive) by adding 'ungrounded_claim' to issues."
        ),
        "test_code": (
            "assert lint_evidence_report('# Rapport\\nStatut: PROVEN\\nPreuve: log.txt')['ok'] is True\n"
            "r = lint_evidence_report('profit garanti sans test')\n"
            "assert r['ok'] is False and 'ungrounded_claim' in r['issues']\n"
        ),
    },
    {
        "id": "eval-market-candle-gaps",
        "role": "market_data",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `detect_candle_gaps(timestamps_s, interval_s)` where timestamps_s is a sorted list of ints "
            "and interval_s is positive int. Return dict {'gaps': list[tuple[int, int]], 'duplicates': int, 'non_monotonic': bool}. "
            "A gap exists when t[i] - t[i-1] > interval_s (append (t[i-1], t[i])); duplicate when t[i] == t[i-1]; non_monotonic if t[i] < t[i-1]. "
            "Raise ValueError if interval_s <= 0 or bool."
        ),
        "test_code": (
            "assert detect_candle_gaps([0, 60, 120, 240, 240], 60) == {'gaps': [(120, 240)], 'duplicates': 1, 'non_monotonic': False}\n"
            "assert detect_candle_gaps([120, 60], 60)['non_monotonic'] is True\n"
            "try:\n    detect_candle_gaps([0, 60], 0); assert False\nexcept ValueError:\n    pass\n"
        ),
    },
    {
        "id": "eval-monitor-alert-triage",
        "role": "monitoring",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `triage_alert(free_ram_mb, error_rate, consecutive_timeouts)` returning dict "
            "{'severity': str, 'action': str}. Rules: if free_ram_mb < 700 or consecutive_timeouts >= 3 -> severity='CRITICAL', action='pause_and_reclaim'; "
            "elif free_ram_mb < 1400 or error_rate >= 0.3 -> severity='WARN', action='throttle_profile'; "
            "else -> severity='OK', action='continue'. Raise ValueError for negative values or error_rate > 1.0."
        ),
        "test_code": (
            "assert triage_alert(3200, 0.05, 0) == {'severity': 'OK', 'action': 'continue'}\n"
            "assert triage_alert(1100, 0.1, 0) == {'severity': 'WARN', 'action': 'throttle_profile'}\n"
            "assert triage_alert(500, 0.1, 0) == {'severity': 'CRITICAL', 'action': 'pause_and_reclaim'}\n"
            "assert triage_alert(4000, 0.0, 3) == {'severity': 'CRITICAL', 'action': 'pause_and_reclaim'}\n"
            "try:\n    triage_alert(-1, 0.0, 0); assert False\nexcept ValueError:\n    pass\n"
        ),
    },
    {
        "id": "eval-release-gate-check",
        "role": "release",
        "difficulty": "medium",
        "task_profile": "module",
        "objective": (
            "Write a Python function `evaluate_release_readiness(ci_green, tests_passed, tests_total, *, target_branch, has_owner_approval=False)` "
            "returning dict {'ready': bool, 'blocked_reasons': list[str]}. Block if not ci_green ('ci_red'), if tests_total <= 0 or tests_passed < tests_total ('tests_incomplete'), "
            "or if target_branch.strip().lower() in ('main', 'master') and not has_owner_approval ('protected_branch_requires_owner_approval')."
        ),
        "test_code": (
            "assert evaluate_release_readiness(True, 10, 10, target_branch='agents/feat') == {'ready': True, 'blocked_reasons': []}\n"
            "r = evaluate_release_readiness(True, 10, 10, target_branch='main', has_owner_approval=False)\n"
            "assert r['ready'] is False and 'protected_branch_requires_owner_approval' in r['blocked_reasons']\n"
            "r2 = evaluate_release_readiness(False, 8, 10, target_branch='agents/feat')\n"
            "assert 'ci_red' in r2['blocked_reasons'] and 'tests_incomplete' in r2['blocked_reasons']\n"
        ),
    },
    {
        "id": "eval-dev-l4-state-machine",
        "role": "development",
        "difficulty": "hard",
        "task_profile": "module",
        "objective": (
            "Write a Python class `MissionCheckpointMachine` with methods `transition(mission_id, next_status)` and `status(mission_id)`. "
            "Allowed transitions: None->'PREPARING', 'PREPARING'->'ACK', 'ACK'->'RUNNING', 'RUNNING'->('WORKER_EXITED','BLOCKED','ACK'), "
            "'WORKER_EXITED'->('ACCEPTED','REJECTED','ACK'). 'ACCEPTED' is immutable terminal (any transition from 'ACCEPTED' MUST raise ValueError). "
            "Invalid transitions raise ValueError. Keep a list `history(mission_id)` of recorded statuses."
        ),
        "test_code": (
            "m = MissionCheckpointMachine()\n"
            "for s in ('PREPARING', 'ACK', 'RUNNING', 'WORKER_EXITED', 'ACCEPTED'):\n"
            "    m.transition('m1', s)\n"
            "assert m.status('m1') == 'ACCEPTED' and len(m.history('m1')) == 5\n"
            "try:\n    m.transition('m1', 'ACK'); assert False\nexcept ValueError:\n    pass\n"
            "try:\n    m.transition('m2', 'ACCEPTED'); assert False\nexcept ValueError:\n    pass\n"
        ),
    },
]


def audit_12_roles_curriculum() -> dict[str, Any]:
    """Map all 12 official TEL99 roles to their competencies, skills, tracks, and evaluation focus."""
    specs = specialist_dispatch.list_specialists()
    held_out_roles = {ex["role"] for ex in HELD_OUT_EVAL_EXERCISES}
    calibration_roles = {ex["role"] for ex in CALIBRATION_EXERCISES}
    curriculum = []
    for row in specs:
        role = row["role"]
        curriculum.append({
            "role": role,
            "name": row["name"],
            "active_default": row["active"],
            "specialty": row.get("specialty", "code"),
            "skills": row["skills"],
            "preferred_tier": row["preferred_tier"],
            "memory_scope": row.get("memory_scope", "project+role"),
            "eval_focus": row["acceptance_criteria"],
            "levels": ("L1_basics", "L2_repair_and_guardrails", "L3_multi_file_coordination"),
            "has_calibration_exercise": role in calibration_roles,
            "has_held_out_exercise": role in held_out_roles,
        })
    return {
        "total_roles": len(curriculum),
        "calibration_count": len(CALIBRATION_EXERCISES),
        "held_out_count": len(HELD_OUT_EVAL_EXERCISES),
        "curriculum": curriculum,
    }


def evaluate_improvement_gate(
    before_report: dict[str, Any],
    after_report: dict[str, Any],
    *,
    min_delta: float = 0.0,
) -> dict[str, Any]:
    """Decide PROMOTE / KEEP_BASELINE / ROLLBACK strictly from held-out before/after metrics."""
    b_rate = float(before_report.get("success_rate") or 0.0)
    a_rate = float(after_report.get("success_rate") or 0.0)
    b_fp = int(before_report.get("first_pass") or 0)
    a_fp = int(after_report.get("first_pass") or 0)
    delta_rate = round(a_rate - b_rate, 4)

    b_by_id = {r["id"]: bool(r.get("ok")) for r in (before_report.get("results") or []) if isinstance(r, dict) and "id" in r}
    a_by_id = {r["id"]: bool(r.get("ok")) for r in (after_report.get("results") or []) if isinstance(r, dict) and "id" in r}
    regressions = sorted(ex_id for ex_id, ok in b_by_id.items() if ok and not a_by_id.get(ex_id, False))
    improvements = sorted(ex_id for ex_id, ok in a_by_id.items() if ok and not b_by_id.get(ex_id, False))

    if regressions and delta_rate <= 0.0:
        decision = "ROLLBACK"
        reason = f"Held-out regression detected on {', '.join(regressions)} (delta={delta_rate:+.4f})."
    elif delta_rate > min_delta or (delta_rate >= min_delta and a_fp > b_fp and not regressions):
        decision = "PROMOTE"
        reason = f"Held-out gain verified: rate {b_rate:.2%} -> {a_rate:.2%}, first_pass {b_fp} -> {a_fp}."
    elif delta_rate < 0.0:
        decision = "ROLLBACK"
        reason = f"Held-out success rate decreased ({b_rate:.2%} -> {a_rate:.2%})."
    else:
        decision = "KEEP_BASELINE"
        reason = f"No net held-out improvement (rate={a_rate:.2%}, first_pass={a_fp})."

    return {
        "decision": decision,
        "reason": reason,
        "before_success_rate": b_rate,
        "after_success_rate": a_rate,
        "delta_success_rate": delta_rate,
        "before_first_pass": b_fp,
        "after_first_pass": a_fp,
        "improvements": improvements,
        "regressions": regressions,
    }


def snapshot_agent_profile_version(
    store_dir: Path | str,
    *,
    version_id: str,
    profile_data: dict[str, Any],
    metrics: dict[str, Any] | None = None,
) -> Path:
    """Persist a versioned, rollback-capable agent prompt/skill/routing configuration snapshot."""
    if not version_id or "/" in version_id or "\\" in version_id or ".." in version_id:
        raise ValueError("invalid version_id")
    root = Path(store_dir)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "version_id": version_id,
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "security_guardrails_mutable": False,
        "profile_data": profile_data,
        "metrics": metrics or {},
    }
    dest = root / f"profile_{version_id}.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(dest)
    active = root / "active_profile.json"
    tmp_active = active.with_suffix(".json.tmp")
    tmp_active.write_text(json.dumps({"active_version": version_id, "snapshot_file": dest.name}, indent=2) + "\n", encoding="utf-8")
    tmp_active.replace(active)
    return dest


def rollback_agent_profile_version(store_dir: Path | str, *, target_version: str) -> dict[str, Any]:
    """Restore active_profile.json to a previously saved version snapshot without deleting history."""
    root = Path(store_dir)
    dest = root / f"profile_{target_version}.json"
    if not dest.is_file():
        raise FileNotFoundError(f"Profile version snapshot not found: {target_version}")
    data = json.loads(dest.read_text(encoding="utf-8"))
    active = root / "active_profile.json"
    tmp_active = active.with_suffix(".json.tmp")
    tmp_active.write_text(
        json.dumps({"active_version": target_version, "snapshot_file": dest.name, "rolled_back": True}, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_active.replace(active)
    return data


def _verify_python_exercise(code: str, test_code: str) -> dict[str, Any]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"ok": False, "error": f"SyntaxError line {exc.lineno}: {exc.msg}", "passed": [], "failed": ["syntax"]}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "__import__"}:
            return {"ok": False, "error": f"Forbidden call {node.func.id}", "passed": ["syntax"], "failed": ["security"]}
    ns: dict[str, Any] = {}
    try:
        exec(compile(code, "<candidate>", "exec"), ns)
        exec(compile(test_code, "<held-out-test>", "exec"), ns)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "passed": ["syntax", "security"], "failed": ["behavior"]}
    return {"ok": True, "error": None, "passed": ["syntax", "security", "behavior"], "failed": []}


def evaluate_model_on_held_out(
    *,
    model: str,
    mode: str = "upgraded",
    max_attempts: int = 2,
    exercises: list[dict[str, Any]] | None = None,
    memory_root: Path | str | None = None,
    skills_root: Path | str | None = None,
    artifacts_dir: Path | str | None = None,
    progress_file: Path | str | None = None,
) -> dict[str, Any]:
    """Run held-out exercises in 'baseline' (naive retry, 1024) or 'upgraded' (Context Engine + RAG + Skills + Smart Repair)."""
    from scripts.agents.automation import context_engine, metacognition

    exs = exercises or HELD_OUT_EVAL_EXERCISES
    results = []
    started = time.monotonic()
    traj_rec = metacognition.TrajectoryRecorder(artifacts_dir) if artifacts_dir else None
    flib = metacognition.FailureLibrary(artifacts_dir, memory_root=memory_root) if artifacts_dir else None
    cal_observations: list[dict[str, Any]] = []

    for ex in exs:
        profile = "patch" if mode == "baseline" else ex.get("task_profile", "module")
        budget = ollama_native.compute_adaptive_budget(model, task_profile=profile, estimated_lines=50)
        provider = ollama_native.OllamaNativeProvider(
            model=model,
            timeout=budget["timeout"],
            max_tokens=budget["max_tokens"],
            keep_alive="120s",
            task_profile=profile,
            num_ctx=budget["num_ctx"],
            num_thread=budget["num_thread"],
        )
        # Retrieve verified memory + relevant skills in upgraded mode
        mem_lessons: list[str] = []
        skills_used: list[str] = []
        if mode != "baseline":
            if memory_root is not None:
                hits = context_engine.HybridMemoryIndex(memory_root).search(
                    "tel99-academy", f"{ex['role']} {ex['objective']}", limit=3, verified_only=True, role=ex["role"]
                )
                mem_lessons = [f"{h['title']}: {h['body']}" for h in hits]
            if skills_root is not None:
                sk = context_engine.select_relevant_skills(skills_root, f"{ex['role']} {ex['objective']}", limit=2)
                skills_used = [s["name"] for s in sk]

        conf_est = metacognition.estimate_task_confidence(
            estimated_lines=50,
            prior_role_success_rate=0.75,
            has_verified_memory=bool(mem_lessons),
        )
        prior_hashes: list[str] = []
        attempts_log: list[dict[str, Any]] = []
        last_code = ""
        prev_code = ""
        last_ver: dict[str, Any] = {"ok": False, "error": "not run", "passed": [], "failed": []}

        for attempt in range(1, max_attempts + 1):
            t0 = time.monotonic()
            if attempt == 1 or mode == "baseline":
                sys_prompt = (
                    "Return ONLY clean Python 3 stdlib code implementing the requested function."
                    if mode == "baseline"
                    else smart_repair.build_structured_reasoning_prompt(
                        role=ex["role"],
                        objective=ex["objective"],
                        constraints=[
                            "Python 3.12 stdlib only",
                            "No eval/exec/__import__",
                            "Validate bool separately from int where required",
                            "Return ONLY valid Python code inside one block",
                        ],
                    )
                )
                user_prompt = ex["objective"]
                if mode != "baseline" and mem_lessons:
                    user_prompt += "\n\nVerified memory lessons:\n- " + "\n- ".join(mem_lessons)
                if attempt > 1 and mode == "baseline":
                    user_prompt += f"\nPrevious attempt failed: {last_ver.get('error')}"
            else:
                sys_prompt = "Return ONLY the complete corrected Python 3 stdlib code."
                diff = smart_repair.compute_bounded_diff(prev_code, last_code) if prev_code else ""
                user_prompt = smart_repair.build_smart_repair_prompt(
                    previous_code=last_code,
                    exact_error=str(last_ver.get("error") or ""),
                    passed_checks=last_ver.get("passed", []),
                    failed_checks=last_ver.get("failed", []),
                    contract_constraints=["Python 3.12 stdlib only", "Preserve exact signature"],
                    prior_attempts=attempts_log,
                    memory_lessons=mem_lessons,
                    previous_diff=diff,
                )
            try:
                raw = provider.complete(system=sys_prompt, prompt=user_prompt)
                code = ollama_native.extract_code_block(raw)
                repeated = smart_repair.detect_repeated_attempt(code, prior_hashes)
                ver = _verify_python_exercise(code, ex["test_code"])
                fp = smart_repair.code_fingerprint(code)
            except ollama_native.ProviderError as exc:
                code, repeated, fp = "", False, ""
                ver = {"ok": False, "error": f"ProviderError: {exc}", "passed": [], "failed": ["infra"]}
            prior_hashes.append(fp)
            attempts_log.append({
                "attempt": attempt,
                "seconds": round(time.monotonic() - t0, 2),
                "ok": ver["ok"],
                "repeated": repeated,
                "code_sha256": fp,
                "error": ver.get("error"),
            })
            prev_code = last_code
            last_code = code
            last_ver = ver
            if ver["ok"]:
                break

        cal_observations.append({"confidence": conf_est["calibrated_confidence"], "success": bool(last_ver["ok"])})
        repaired = bool(last_ver["ok"] and len(attempts_log) > 1)
        if traj_rec is not None:
            traj_rec.record(
                project="tel99-academy",
                mission_id=f"{mode}-{ex['id']}",
                objective=ex["objective"][:400],
                model=model,
                role=ex["role"],
                tools_used=[{"tool": "ollama_native", "mode": mode}],
                decisions=[f"skills={','.join(skills_used)}", f"mem={len(mem_lessons)}"],
                errors=[str(a["error"]) for a in attempts_log if a.get("error")],
                repairs=attempts_log[1:],
                tests=[{"ok": bool(last_ver["ok"])}],
                artifacts=[],
                verdict="SUCCESS" if last_ver["ok"] else "FAILURE",
                duration_seconds=round(sum(a["seconds"] for a in attempts_log), 2),
            )
        if flib is not None and any(a.get("error") for a in attempts_log):
            first_err = next((str(a["error"]) for a in attempts_log if a.get("error")), "error")
            flib.record_failure(
                project="tel99-academy",
                mission_id=f"{mode}-{ex['id']}",
                category="ENGINE_ERROR" if "ProviderError" in first_err else "VERIFICATION_ERROR",
                context_summary=f"Academy {mode} {ex['role']} {ex['id']}",
                cause=first_err[:240],
                cause_confirmed=bool(last_ver["ok"]),
                evidence=f"attempts={len(attempts_log)} ok={bool(last_ver['ok'])}",
                attempts=attempts_log,
                validated_solution=("Repaired via smart_repair" if repaired else ""),
                preventive_measure="Validate types (reject bool for int), bounds, and exact signatures",
                model=model,
                role=ex["role"],
            )

        results.append({
            "id": ex["id"],
            "role": ex["role"],
            "difficulty": ex.get("difficulty", "medium"),
            "ok": bool(last_ver["ok"]),
            "attempts": len(attempts_log),
            "repaired": repaired,
            "lessons_used": len(mem_lessons),
            "skills_used": skills_used,
            "confidence": conf_est["calibrated_confidence"],
            "attempts_log": attempts_log,
        })
        if progress_file is not None:
            pf = Path(progress_file)
            pf.parent.mkdir(parents=True, exist_ok=True)
            tmp = pf.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"mode": mode, "model": model, "completed": len(results), "total": len(exs), "results": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(pf)

    passed_count = sum(1 for r in results if r["ok"])
    repaired_count = sum(1 for r in results if r["repaired"])
    return {
        "schema_version": 1,
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model": model,
        "mode": mode,
        "total": len(results),
        "passed": passed_count,
        "success_rate": round(passed_count / max(1, len(results)), 4),
        "first_pass": sum(1 for r in results if r["ok"] and r["attempts"] == 1),
        "repaired": repaired_count,
        "calibration": metacognition.compute_calibration_metrics(cal_observations),
        "duration_seconds": round(time.monotonic() - started, 2),
        "results": results,
    }
