"""Goal-to-missions planner for TEL99: AST check, DAG order, measured model selection."""
from __future__ import annotations

import argparse
from graphlib import TopologicalSorter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation import (
    learning_loop,
    local_codegen,
    local_team,
    proposal_builder,
    provider_router,
)
from scripts.agents.automation.autonomy_runtime import fingerprint, seal, validate_contract
from scripts.agents.automation.env_doctor import DEFAULT_SANDBOX_IMAGE


def plan_from_goal(goal_spec: dict, *, state_root: Path | str | None = None,
                   verify_baseline: bool = False, inventory: dict | None = None,
                   source_loader=local_codegen._source,
                   behavior_runner=local_codegen._behavior) -> dict:
    """Decompose a high-level goal specification into validated, ordered missions.

    Produces a sealed local registry (missions + approvals) ready for Runtime,
    and when controller metadata is supplied, a validated read-only GitHub draft
    proposal via proposal_builder.
    """
    if not isinstance(goal_spec, dict):
        raise ValueError("goal specification must be a JSON object")
    goal = goal_spec.get("goal") or goal_spec.get("objective")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal specification requires a non-empty goal")
    base_sha = goal_spec.get("base_sha")
    if not isinstance(base_sha, str) or len(base_sha) != 40:
        raise ValueError("goal specification requires a 40-char pinned base_sha")
    tasks = goal_spec.get("tasks") or goal_spec.get("missions")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 10:
        raise ValueError("goal specification requires 1..10 tasks")

    measured = {}
    if state_root is not None:
        metrics = learning_loop.collect_campaign_metrics(state_root)
        measured = metrics.get("measured_quality", {})

    confidential = bool(goal_spec.get("confidential", True))
    allow_sub_cli = bool(goal_spec.get("allow_subscription_cli", False))
    route_decision = provider_router.select_executor(
        task_kind="code",
        difficulty=goal_spec.get("difficulty", "medium"),
        confidential=confidential,
        allow_subscription_cli=allow_sub_cli,
        measured_quality=measured,
        inventory=inventory,
    )
    chosen = route_decision.get("chosen")
    default_model = (chosen or {}).get("served_model") or "gemma4:e4b-tel99-8k"
    default_port = 11434 if (chosen or {}).get("provider", "ollama") == "ollama" else 11434

    by_id: dict[str, dict] = {}
    graph: dict[str, list[str]] = {}
    seen_paths: set[str] = set()
    baseline_checks: dict[str, dict] = {}

    for idx, item in enumerate(tasks, 1):
        if not isinstance(item, dict):
            raise ValueError("each task entry must be a JSON object")
        mid = item.get("id")
        path = item.get("path")
        func = item.get("function")
        test_code = item.get("test")
        objective = item.get("objective") or f"{goal.strip()} ({func})"
        if not isinstance(mid, str) or not mid:
            raise ValueError(f"task #{idx} requires an id")
        if mid in by_id:
            raise ValueError(f"duplicate task id: {mid}")
        if not isinstance(path, str) or path in seen_paths:
            raise ValueError(f"task {mid} must target a distinct Python file")
        seen_paths.add(path)

        model = item.get("model") or default_model
        port = item.get("port") or default_port
        mission = {
            "id": mid,
            "owner": "local",
            "project": goal_spec.get("project", "tel99"),
            "specialist": "tel99-dev",
            "priority": item.get("priority", f"P{min(idx, 9)}"),
            "dependencies": list(item.get("dependencies", [])),
            "objective": objective,
            "base_sha": base_sha,
            "path": path,
            "function": func,
            "test": test_code,
            "sandbox_image": item.get("sandbox_image", DEFAULT_SANDBOX_IMAGE),
            "model": model,
            "port": port,
            "team": local_team.TEAM.copy(),
            "max_attempts": item.get("max_attempts", 2),
        }
        validate_contract(mission, {mid: fingerprint(mission)})
        source = source_loader(mission)
        local_codegen._function(source, func)
        if verify_baseline:
            passed, line = behavior_runner(mission["sandbox_image"], source, test_code)
            if passed:
                raise ValueError(f"baseline test for {mid} already passes (expected baseline-red)")
            baseline_checks[mid] = {"baseline_red": True, "assertion_line": line}
        by_id[mid] = mission
        graph[mid] = list(mission["dependencies"])

    for mid, deps in graph.items():
        for dep in deps:
            if dep not in by_id or dep == mid:
                raise ValueError(f"unknown or self-referential dependency {dep!r} in {mid}")
    order = list(TopologicalSorter(graph).static_order())
    ordered_missions = [by_id[mid] for mid in order]

    plan = {
        "schema_version": 1,
        "goal": goal.strip(),
        "project": goal_spec.get("project", "tel99"),
        "base_sha": base_sha,
        "roles_pipeline": [
            local_team.COORDINATOR,
            local_team.TEAM[0],
            local_team.TEAM[1],
            local_team.SECURITY,
            local_team.TEAM[2],
        ],
        "model_selection": route_decision,
        "execution_order": order,
        "baseline_checks": baseline_checks,
        "local_registry": {
            "missions": ordered_missions,
            "approvals": seal(ordered_missions),
        },
        "github_proposal": None,
    }

    if goal_spec.get("controller_issue") and goal_spec.get("expires_at") and goal_spec.get("base_ref"):
        prop_spec = {
            "controller_issue": goal_spec["controller_issue"],
            "mandate_comment_id": goal_spec.get("mandate_comment_id", 0),
            "expires_at": goal_spec["expires_at"],
            "base_ref": goal_spec["base_ref"],
            "base_sha": base_sha,
            "missions": [
                {
                    **by_id[mid],
                    "issue": next(
                        t["issue"] for t in tasks if t.get("id") == mid and "issue" in t
                    ),
                }
                for mid in order
            ],
        }
        plan["github_proposal"] = proposal_builder.build_proposal(
            prop_spec,
            verify_baseline=False,  # already verified above if requested
            source_loader=source_loader,
            behavior_runner=behavior_runner,
        )
    return plan


def assess_and_decompose_mission(
    task: dict,
    *,
    model_id: str = "local/ollama-gemma4-e4b",
    max_safe_lines: int = 65,
    max_functions_per_subtask: int = 2,
) -> dict:
    """Detect oversized tasks for a local model and auto-decompose them into a dependent DAG."""
    if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task["id"].strip():
        raise ValueError("task must be a dict with non-empty 'id'")
    functions = [f for f in (task.get("functions") or []) if isinstance(f, str) and f.strip()]
    est_lines = int(task.get("estimated_lines") or (len(functions) * 25 if functions else 45))
    needs_split = len(functions) > max_functions_per_subtask or est_lines > max_safe_lines

    if not needs_split:
        return {
            "model_id": model_id,
            "needs_decomposition": False,
            "reason": "within safe single-pass local model budget",
            "recommended_profile": "patch" if est_lines <= 45 else "module",
            "subtasks": [{**task, "dependencies": list(task.get("dependencies") or [])}],
        }

    chunks: list[list[str]] = []
    if functions:
        for i in range(0, len(functions), max_functions_per_subtask):
            chunks.append(functions[i : i + max_functions_per_subtask])
    else:
        n_parts = max(2, (est_lines + max_safe_lines - 1) // max_safe_lines)
        chunks = [[f"part_{i + 1}"] for i in range(n_parts)]

    subtasks: list[dict] = []
    prev_id: str | None = None
    base_deps = list(task.get("dependencies") or [])
    for idx, group in enumerate(chunks, 1):
        sub_id = f"{task['id']}-part-{idx}"[:48]
        subtasks.append({
            "id": sub_id,
            "parent_id": task["id"],
            "path": task.get("path", ""),
            "functions": group,
            "estimated_lines": max(25, est_lines // len(chunks)),
            "dependencies": list(base_deps) if prev_id is None else [prev_id],
            "task_profile": "module",
            "objective": f"Part {idx}/{len(chunks)} of {task['id']} ({', '.join(group)}): {task.get('objective', '')}",
        })
        prev_id = sub_id

    return {
        "model_id": model_id,
        "needs_decomposition": True,
        "reason": f"estimated_lines={est_lines} or functions={len(functions)} exceeds safe local pass ({max_safe_lines} lines / {max_functions_per_subtask} functions)",
        "recommended_profile": "module",
        "subtasks": subtasks,
    }


def revise_plan_after_failure(
    subtasks: list[dict],
    *,
    failed_id: str,
    error_class: str,
    completed_ids: set[str] | list[str] = (),
) -> dict:
    """Revise an active plan after a failure while strictly preserving already-completed tasks."""
    done = set(completed_ids)
    if failed_id in done:
        raise ValueError(f"cannot revise already completed task {failed_id!r}")
    revised: list[dict] = []
    replacement_tail: str | None = None
    action = "keep"

    for row in subtasks:
        tid = row["id"]
        if tid in done:
            revised.append(dict(row))
            continue
        if tid == failed_id:
            if error_class in ("MODEL_ERROR", "VERIFICATION_ERROR", "ENVIRONMENT_ERROR"):
                split = assess_and_decompose_mission(
                    {**row, "estimated_lines": max(int(row.get("estimated_lines") or 70), 90)},
                    max_safe_lines=45,
                    max_functions_per_subtask=1,
                )
                parts = split["subtasks"]
                revised.extend(parts)
                replacement_tail = parts[-1]["id"]
                action = "split_failed_task"
            else:
                revised.append({**row, "retry_hint": f"address {error_class}"})
                action = "annotate_retry"
            continue
        updated = dict(row)
        if replacement_tail and failed_id in (updated.get("dependencies") or []):
            updated["dependencies"] = [
                replacement_tail if dep == failed_id else dep
                for dep in updated["dependencies"]
            ]
        revised.append(updated)

    return {
        "action": action,
        "failed_id": failed_id,
        "error_class": error_class,
        "preserved_completed": sorted(done),
        "subtasks": revised,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=None)
    parser.add_argument("--verify-baseline", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    plan = plan_from_goal(spec, state_root=args.state, verify_baseline=args.verify_baseline)
    rendered = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
