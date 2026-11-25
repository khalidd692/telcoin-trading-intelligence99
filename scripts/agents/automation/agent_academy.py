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

# Calibration set (used to tune prompts/procedures) vs Held-out evaluation set (unseen during tuning)
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
]


def audit_12_roles_curriculum() -> dict[str, Any]:
    """Map all 12 official TEL99 roles to their competencies, skills, and evaluation focus."""
    specs = specialist_dispatch.list_specialists()
    curriculum = []
    for row in specs:
        curriculum.append({
            "role": row["role"],
            "name": row["name"],
            "active_default": row["active"],
            "skills": row["skills"],
            "preferred_tier": row["preferred_tier"],
            "eval_focus": row["acceptance_criteria"],
        })
    return {"total_roles": len(curriculum), "curriculum": curriculum}


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
) -> dict[str, Any]:
    """Run held-out exercises in 'baseline' (naive retry, 1024) or 'upgraded' (smart_repair + adaptive budget) mode."""
    exs = exercises or HELD_OUT_EVAL_EXERCISES
    results = []
    started = time.monotonic()

    for ex in exs:
        profile = "patch" if mode == "baseline" else ex.get("task_profile", "module")
        budget = ollama_native.compute_adaptive_budget(model, task_profile=profile, estimated_lines=45)
        provider = ollama_native.OllamaNativeProvider(
            model=model,
            timeout=budget["timeout"],
            max_tokens=budget["max_tokens"],
            keep_alive="120s",
            task_profile=profile,
        )
        prior_hashes: list[str] = []
        attempts_log: list[dict[str, Any]] = []
        last_code = ""
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
                        constraints=["Python 3.12 stdlib only", "No eval/exec", "Handle invalid types cleanly"],
                    )
                )
                user_prompt = ex["objective"]
                if attempt > 1 and mode == "baseline":
                    user_prompt += f"\nPrevious attempt failed: {last_ver.get('error')}"
            else:
                sys_prompt = "Return ONLY the complete corrected Python 3 stdlib function."
                user_prompt = smart_repair.build_smart_repair_prompt(
                    previous_code=last_code,
                    exact_error=str(last_ver.get("error") or ""),
                    passed_checks=last_ver.get("passed", []),
                    failed_checks=last_ver.get("failed", []),
                    contract_constraints=["Python 3.12 stdlib only", "Preserve exact signature"],
                    prior_attempts=attempts_log,
                )
            raw = provider.complete(system=sys_prompt, prompt=user_prompt)
            code = ollama_native.extract_code_block(raw)
            repeated = smart_repair.detect_repeated_attempt(code, prior_hashes)
            ver = _verify_python_exercise(code, ex["test_code"])
            fp = smart_repair.code_fingerprint(code)
            prior_hashes.append(fp)
            attempts_log.append({
                "attempt": attempt,
                "seconds": round(time.monotonic() - t0, 2),
                "ok": ver["ok"],
                "repeated": repeated,
                "code_sha256": fp,
                "error": ver.get("error"),
            })
            last_code = code
            last_ver = ver
            if ver["ok"]:
                break

        results.append({
            "id": ex["id"],
            "role": ex["role"],
            "ok": bool(last_ver["ok"]),
            "attempts": len(attempts_log),
            "repaired": bool(last_ver["ok"] and len(attempts_log) > 1),
            "attempts_log": attempts_log,
        })

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
        "duration_seconds": round(time.monotonic() - started, 2),
        "results": results,
    }
