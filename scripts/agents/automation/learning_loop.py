"""Closed-loop learning across TEL99 campaigns: retrieve, capitalize, measure.

Connects verified outcomes (Docker passes, repair-after-feedback successes, and
terminal failures) back into project-isolated MemoryStore and router-ready
measured_quality.json without mutating approvals or historical ledgers.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.intelligence import catalog
from scripts.agents.intelligence.memory import COMMON_PROJECT, Entry, MemoryStore
from scripts.agents.protocol.store import FileStore

MAX_LESSON_CHARS = 280
MAX_LESSONS_BYTES = 1000
TERMINAL_STATUSES = {"ACCEPTED", "REJECTED", "BLOCKED", "AWAITING_HUMAN"}


def _clean_text(value: str, *, limit: int = MAX_LESSON_CHARS) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[:limit - 3].rstrip() + "..."
    return text


def _catalog_id(served_model: str | None) -> str:
    if not isinstance(served_model, str) or not served_model:
        return "unknown"
    for spec in catalog.MODEL_CATALOG:
        if spec.id == served_model or served_model in spec.served_ids:
            return spec.id
    return served_model


def retrieve_lessons(memory_root: Path | str, project: str, mission: dict,
                     *, limit: int = 3) -> list[str]:
    """Retrieve bounded, sanitized, project-isolated advisory notes before execution."""
    if not isinstance(project, str) or not project.strip() or not 1 <= limit <= 3:
        return []
    root = Path(memory_root)
    if not root.exists():
        return []
    store = MemoryStore(root)
    query_parts = [
        str(mission.get("path", "")),
        str(mission.get("function", "")),
        str(mission.get("objective", "")),
    ]
    query = " ".join(part for part in query_parts if part).strip()
    if not query:
        return []
    entries = store.search(
        project,
        query,
        limit=limit * 2,
        kinds=("fix", "error", "procedure", "fact"),
        include_superseded=False,
        include_common=(project != COMMON_PROJECT),
    )
    # Prioritize verified entries and capitalized fixes/errors over raw facts.
    kind_rank = {"fix": 0, "error": 1, "procedure": 2, "decision": 3, "fact": 4}
    entries.sort(key=lambda e: (not e.verified, kind_rank.get(e.kind, 9), e.id))
    notes: list[str] = []
    total_bytes = 0
    for entry in entries:
        badge = "verified" if entry.verified else "advisory"
        title = _clean_text(entry.title, limit=110)
        summary = _clean_text(entry.body, limit=150)
        line = _clean_text(f"[{entry.kind}|{badge}] {title}: {summary}", limit=MAX_LESSON_CHARS)
        encoded = len(line.encode("utf-8"))
        if total_bytes + encoded > MAX_LESSONS_BYTES:
            continue
        notes.append(line)
        total_bytes += encoded
        if len(notes) >= limit:
            break
    return notes


def retrieve_scoped_lessons(
    memory_root: Path | str,
    project: str,
    mission: dict,
    *,
    role: str | None = None,
    verified_only: bool = False,
    limit: int = 3,
) -> dict:
    """Retrieve deduplicated lessons segmented by scope (individual/project/collective/procedural)."""
    empty = {
        "lessons": [],
        "by_scope": {"individual": [], "project": [], "collective": [], "procedural": []},
        "total_bytes": 0,
        "verified_only": bool(verified_only),
    }
    if not isinstance(project, str) or not project.strip() or not 1 <= limit <= 6:
        return empty
    root = Path(memory_root)
    if not root.exists():
        return empty
    store = MemoryStore(root)
    query_parts = [
        str(mission.get("path", "")),
        str(mission.get("target_file", "")),
        str(mission.get("function", "")),
        str(mission.get("objective", "")),
    ]
    query = " ".join(part for part in query_parts if part).strip()
    if not query:
        return empty
    entries = store.search(
        project,
        query,
        limit=limit * 4,
        kinds=("fix", "error", "procedure", "fact"),
        include_superseded=False,
        include_common=(project != COMMON_PROJECT),
    )
    if verified_only:
        entries = [e for e in entries if e.verified]
    kind_rank = {"fix": 0, "procedure": 1, "error": 2, "decision": 3, "fact": 4}
    entries.sort(key=lambda e: (not e.verified, kind_rank.get(e.kind, 9), e.id))

    by_scope: dict[str, list[str]] = {"individual": [], "project": [], "collective": [], "procedural": []}
    seen_ids: set[str] = set()
    lessons: list[str] = []
    total_bytes = 0
    for entry in entries:
        if entry.id in seen_ids:
            continue
        seen_ids.add(entry.id)
        badge = "verified" if entry.verified else "advisory"
        title = _clean_text(entry.title, limit=110)
        summary = _clean_text(entry.body, limit=150)
        line = _clean_text(f"[{entry.kind}|{badge}] {title}: {summary}", limit=MAX_LESSON_CHARS)

        if entry.kind == "procedure":
            bucket = "procedural"
        elif role and entry.author == role:
            bucket = "individual"
        elif entry.project == COMMON_PROJECT:
            bucket = "collective"
        else:
            bucket = "project"
        by_scope[bucket].append(line)

        encoded = len(line.encode("utf-8"))
        if len(lessons) < limit and total_bytes + encoded <= MAX_LESSONS_BYTES:
            lessons.append(line)
            total_bytes += encoded

    return {
        "lessons": lessons,
        "by_scope": by_scope,
        "total_bytes": total_bytes,
        "verified_only": bool(verified_only),
    }


def _failed_checks(verification: dict | None) -> list[str]:
    if not isinstance(verification, dict):
        return []
    checks = verification.get("checks")
    if not isinstance(checks, list):
        return []
    return [
        c["name"] for c in checks
        if isinstance(c, dict) and c.get("ok") is False and isinstance(c.get("name"), str)
    ]


def record_outcome(memory_root: Path | str, mission: dict, state: dict) -> list[str]:
    """Capitalize repair successes ('fix') and terminal failures ('error') idempotently."""
    if not isinstance(mission, dict) or not isinstance(state, dict):
        return []
    mid = mission.get("id")
    project = mission.get("project")
    status = state.get("status")
    if not isinstance(mid, str) or not mid or not isinstance(project, str) or not project:
        return []

    store = MemoryStore(memory_root)
    recorded: list[str] = []
    verification = state.get("verification") if isinstance(state.get("verification"), dict) else {}
    result = state.get("result") if isinstance(state.get("result"), dict) else {}
    model = verification.get("model") or result.get("model") or mission.get("model") or "unknown"
    history = state.get("attempt_history") if isinstance(state.get("attempt_history"), list) else []
    path = str(mission.get("path") or mission.get("target_file") or "")
    func = str(mission.get("function") or mission.get("target_file") or mid)

    if status == "ACCEPTED" and history:
        eid = f"fix-{mid}"
        if store.get(project, eid) is None:
            fb_kinds = []
            for row in history:
                fb = row.get("feedback") if isinstance(row, dict) else None
                if isinstance(fb, dict) and isinstance(fb.get("kind"), str):
                    fb_kinds.append(fb["kind"])
            attempts = state.get("attempt") or (len(history) + 1)
            entry = Entry(
                id=eid,
                project=project,
                kind="fix",
                title=f"Repaired {func} in {path} after feedback",
                body=(
                    f"Mission {mid} passed independent verification on attempt {attempts} "
                    f"with {model} after {', '.join(fb_kinds) or 'retry feedback'}."
                ),
                tags=tuple(t for t in (path, func, model, "repaired") if t),
                source=f"kilo-local/{mid}",
                author=str(mission.get("specialist") or "tel99-dev"),
                verified=True,
                verified_by=str(verification.get("verifier") or "tel99-local-docker-code-v1"),
                confidence=0.95,
            )
            store.record(entry, actor="learning-loop")
            recorded.append(eid)
    elif status in ("REJECTED", "BLOCKED"):
        eid = f"error-{mid}"
        if store.get(project, eid) is None:
            failed = _failed_checks(verification)
            reason = _clean_text(state.get("reason") or "verification-failed", limit=140)
            entry = Entry(
                id=eid,
                project=project,
                kind="error",
                title=f"{status} on {func} ({path})",
                body=(
                    f"Mission {mid} ended {status} with {model}: {reason}. "
                    f"Failed checks: {', '.join(failed) or 'none'}."
                ),
                tags=tuple(t for t in (path, func, model, status.lower()) if t),
                source=f"kilo-local/{mid}",
                author=str(mission.get("specialist") or "tel99-dev"),
                verified=False,
                confidence=0.6,
            )
            store.record(entry, actor="learning-loop")
            recorded.append(eid)
    return recorded


def _campaign_roots(state_root: Path) -> list[Path]:
    roots: list[Path] = []
    if (state_root / "ledger" / "kilo-local").is_dir():
        roots.append(state_root)
    for child in sorted(state_root.glob("campaign-*")):
        if child.is_dir() and (child / "ledger" / "kilo-local").is_dir() and child not in roots:
            roots.append(child)
    return roots


def _read_checkpoint_rows(campaign_root: Path) -> list[dict]:
    store = FileStore(campaign_root / "ledger")
    rows = []
    for key in sorted(store.keys("kilo-local")):
        row = store.get(key)
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            rows.append(row)
    return rows


def collect_campaign_metrics(state_root: Path | str) -> dict:
    """Aggregate mission and model metrics across one or many campaign ledgers."""
    root = Path(state_root).resolve()
    roots = _campaign_roots(root)
    missions: list[dict] = []
    by_model: dict[str, dict] = {}
    pending_count = 0

    for camp in roots:
        config = FileStore(camp / "ledger").get("github-local-code/config") or {}
        controller_issue = config.get("issue") if isinstance(config, dict) else None
        for row in _read_checkpoint_rows(camp):
            status = row.get("status")
            verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
            result = row.get("result") if isinstance(row.get("result"), dict) else {}
            route_sel = ((row.get("model_route") or {}).get("selection")
                         if isinstance(row.get("model_route"), dict) else None)
            served_model = (
                verification.get("model")
                or result.get("model")
                or (route_sel.get("model") if isinstance(route_sel, dict) else None)
            )
            model_key = _catalog_id(served_model)
            history = row.get("attempt_history") if isinstance(row.get("attempt_history"), list) else []
            gen_s = verification.get("generation_seconds")
            if type(gen_s) not in (int, float):
                gen_s = result.get("generation_seconds")
            ver_s = verification.get("verification_seconds")
            failed = _failed_checks(verification)

            mission_summary = {
                "id": row["id"],
                "controller_issue": controller_issue,
                "status": status,
                "model_id": model_key,
                "served_model": served_model,
                "attempts": row.get("attempt") or (len(history) + 1),
                "repaired": bool(status == "ACCEPTED" and history),
                "generation_seconds": gen_s if type(gen_s) in (int, float) else None,
                "verification_seconds": ver_s if type(ver_s) in (int, float) else None,
                "failed_checks": failed,
            }
            missions.append(mission_summary)

            if status not in TERMINAL_STATUSES:
                pending_count += 1
                continue

            bucket = by_model.setdefault(model_key, {
                "served_model": served_model,
                "tasks": 0,
                "accepted": 0,
                "first_pass_accepted": 0,
                "repaired_accepted": 0,
                "failed": 0,
                "gen_seconds": [],
                "ver_seconds": [],
                "failed_checks": {},
            })
            bucket["tasks"] += 1
            if status == "ACCEPTED":
                bucket["accepted"] += 1
                if history:
                    bucket["repaired_accepted"] += 1
                else:
                    bucket["first_pass_accepted"] += 1
            else:
                bucket["failed"] += 1
            if type(gen_s) in (int, float) and 0 <= gen_s <= 600:
                bucket["gen_seconds"].append(float(gen_s))
            if type(ver_s) in (int, float) and 0 <= ver_s <= 600:
                bucket["ver_seconds"].append(float(ver_s))
            for check_name in failed:
                bucket["failed_checks"][check_name] = bucket["failed_checks"].get(check_name, 0) + 1

    measured: dict[str, dict] = {}
    for model_key, bucket in sorted(by_model.items()):
        tasks = bucket["tasks"]
        avg_gen = round(sum(bucket["gen_seconds"]) / len(bucket["gen_seconds"]), 3) if bucket["gen_seconds"] else 0.0
        avg_ver = round(sum(bucket["ver_seconds"]) / len(bucket["ver_seconds"]), 3) if bucket["ver_seconds"] else 0.0
        measured[model_key] = {
            "served_model": bucket["served_model"],
            "tasks": tasks,
            "accepted": bucket["accepted"],
            "first_pass_accepted": bucket["first_pass_accepted"],
            "repaired_accepted": bucket["repaired_accepted"],
            "failed": bucket["failed"],
            "success_rate": round(bucket["accepted"] / tasks, 4) if tasks else 0.0,
            "first_pass_rate": round(bucket["first_pass_accepted"] / tasks, 4) if tasks else 0.0,
            "avg_generation_seconds": avg_gen,
            "avg_verification_seconds": avg_ver,
            "avg_seconds": round(avg_gen + avg_ver, 3),
            "failed_checks": bucket["failed_checks"],
        }

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state_root": str(root),
        "campaigns": len(roots),
        "missions_total": len(missions),
        "pending": pending_count,
        "accepted": sum(1 for m in missions if m["status"] == "ACCEPTED"),
        "repaired": sum(1 for m in missions if m["repaired"]),
        "measured_quality": measured,
        "missions": missions,
    }


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    FileStore._retry_file_access(lambda: tmp.replace(path))


def sync_measured_quality(state_root: Path | str, output_path: Path | str | None = None) -> dict:
    """Recompute measured model quality across campaigns and persist router-compatible JSON."""
    root = Path(state_root).resolve()
    report = collect_campaign_metrics(root)
    learning_dir = root / "learning"
    quality_path = Path(output_path) if output_path is not None else (learning_dir / "measured_quality.json")
    _atomic_write_json(quality_path, report["measured_quality"])
    _atomic_write_json(learning_dir / "summary.json", report)
    memory_root = learning_dir / "memory"
    if memory_root.is_dir():
        promoted = promote_verified_procedures(memory_root, "tel99")
        report["promoted_procedures"] = promoted
    report["improvement_proposals"] = propose_skill_improvements(root, report=report)
    return report


def propose_skill_improvements(state_root: Path | str, project: str = "tel99",
                               *, report: dict | None = None) -> dict:
    """Generate testable Skill/prompt proposals from verified outcomes without touching guardrails."""
    root = Path(state_root).resolve()
    metrics = report if isinstance(report, dict) else collect_campaign_metrics(root)
    measured = metrics.get("measured_quality") or {}
    mem_root = root / "learning" / "memory"
    entries = MemoryStore(mem_root).all_entries(project, include_common=True) if mem_root.is_dir() else []

    errors = [e for e in entries if e.kind == "error"]
    fixes = [e for e in entries if e.kind == "fix" and e.verified]
    procedures = [e for e in entries if e.kind == "procedure" and e.verified]

    proposals: list[dict] = []
    for model_id, stats in sorted(measured.items()):
        failed_checks = stats.get("failed_checks") or {}
        if failed_checks.get("candidate-passes", 0) > 0:
            proposals.append({
                "id": f"skill-edge-cases-{model_id.replace('/', '-')}",
                "target": "local_team.analyze / tel99-autonomous-campaign",
                "evidence": f"{model_id}: candidate-passes failed {failed_checks['candidate-passes']} time(s)",
                "proposal": "Inject verified fix lessons and edge-case checklist before attempt 1; require independent Docker test pass.",
                "requires_independent_test": True,
            })
        if stats.get("repaired_accepted", 0) > 0:
            proposals.append({
                "id": f"promote-repair-{model_id.replace('/', '-')}",
                "target": "learned_procedures.md",
                "evidence": f"{model_id}: {stats['repaired_accepted']} repaired mission(s) accepted on retry",
                "proposal": "Keep verified repair pattern in project memory for retrieval on similar functions.",
                "requires_independent_test": True,
            })
    if not proposals and fixes:
        proposals.append({
            "id": "reuse-verified-fixes",
            "target": "learning/learned_procedures.md",
            "evidence": f"{len(fixes)} verified fix(es) and {len(procedures)} promoted procedure(s)",
            "proposal": "Continue retrieving up to 3 verified project lessons per mission without altering security guardrails.",
            "requires_independent_test": True,
        })

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "project": project,
        "learning_kind": "procedural_memory_and_proposals",
        "model_retraining": False,
        "security_guardrails_mutable": False,
        "counts": {
            "errors": len(errors),
            "verified_fixes": len(fixes),
            "promoted_procedures": len(procedures),
            "models_measured": len(measured),
        },
        "model_comparison": measured,
        "proposals": proposals,
    }
    _atomic_write_json(root / "learning" / "improvement_proposals.json", payload)
    return payload


def promote_verified_procedures(memory_root: Path | str, project: str,
                                *, min_verified_fixes: int = 1) -> list[str]:
    """Promote verified repair entries into reusable project procedures & Markdown guide."""
    mem_path = Path(memory_root)
    if not mem_path.exists():
        return []
    store = MemoryStore(mem_path)
    fixes = [
        entry for entry in store.all_entries(project, include_common=False)
        if entry.kind == "fix" and entry.verified and not entry.superseded_by
    ]
    if len(fixes) < min_verified_fixes:
        return []
    promoted: list[str] = []
    lines = [
        f"# Procédures apprises — {project}",
        "",
        "Procédures promues automatiquement à partir des réparations vérifiées par Docker.",
        "",
    ]
    for fix in sorted(fixes, key=lambda e: e.id):
        proc_id = f"proc-{fix.id}"
        if store.get(project, proc_id) is None:
            store.record(Entry(
                id=proc_id,
                project=project,
                kind="procedure",
                title=f"Procedure: {fix.title}",
                body=f"Reusable verified fix pattern from {fix.id}: {fix.body}",
                tags=tuple(sorted({*fix.tags, "procedure", "verified"})),
                source=fix.source,
                author="learning-loop",
                verified=True,
                verified_by=fix.verified_by or "tel99-local-docker-code-v1",
                confidence=max(0.9, fix.confidence),
            ), actor="learning-loop")
            promoted.append(proc_id)
        lines.append(f"- **{fix.title}** (`{fix.id}`): {fix.body}")
    guide = mem_path.parent / "learned_procedures.md"
    guide.parent.mkdir(parents=True, exist_ok=True)
    tmp = guide.with_suffix(".md.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    FileStore._retry_file_access(lambda: tmp.replace(guide))
    return promoted


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--export", type=Path, default=None)
    args = parser.parse_args(argv)
    report = sync_measured_quality(args.state, output_path=args.export)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
