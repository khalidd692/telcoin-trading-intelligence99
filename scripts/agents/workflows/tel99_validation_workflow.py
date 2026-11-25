"""Native Antigravity `run_workflow` script for bounded TEL99 multi-specialist review.

Orchestrates up to 3 read-only TEL99 specialist subagents in parallel and routes
their findings through an independent `tel99-verifier` pass before returning a
single JSON verdict.

Usage with Antigravity `run_workflow`:
    ScriptPath=".../scripts/agents/workflows/tel99_validation_workflow.py"
    Args={"mission_id": "val-ide-20261124", "task": "...", "roles": ["security", "quant"]}
"""
import json

phase("Preparation")
mission_id = str(args.get("mission_id") or "tel99-workflow-check")
task = str(args.get("task") or "Audit TEL99 read-only invariants and integration status.")
requested_roles = [
    str(r) for r in (args.get("roles") or ["security", "quant"])
    if str(r) != "quality"
][:3]

SPECIALIST_HINTS = {
    "development": "tel99-dev: audit Python/JS implementation correctness and minimal diffs.",
    "quant": "tel99-analyst: audit data freshness, temporal leakage, and signal boundaries.",
    "security": "tel99-security: audit read-only guards, leases, secret scrubbing, and protected branches.",
    "cloud": "tel99-cloud: audit GitHub Actions workflows, schedules, and non-PC autonomy claims.",
    "market_data": "tel99-market-data: audit Kraken snapshots, timestamps, and staleness gates.",
    "monitoring": "tel99-monitoring: audit logs, alerts, and delivery verification.",
    "evaluation": "tel99-evaluation: audit prospective evaluation metrics and bias checks.",
    "release": "tel99-release: audit branch diff, test coverage, and publication gates.",
    "coordination": "tel99-coordination: audit task dependencies, lease conflicts, and DAG order.",
    "mobile": "tel99-mobile: audit mobile layout and usability without redesigning Smart View.",
    "documentation": "tel99-documentation: audit handovers, memory provenance, and archive integrity.",
}

READ_ONLY_RULE = (
    "CONTRAINTE LECTURE SEULE: ne modifie aucun fichier, ne fais aucun commit/push/merge, "
    "ne passe aucun ordre financier. Cite uniquement des chemins, symboles et sorties observés."
)

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "role": {"type": "string"},
        "verdict": {"type": "string", "enum": ["PROVEN", "UNPROVEN", "UNCERTAIN"]},
        "findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["role", "verdict", "findings"],
}

phase("Specialist Review (On-Demand)")
log(f"Starting bounded specialist fan-out for {mission_id}: {requested_roles}")
specialist_reports = await parallel(
    requested_roles,
    lambda r: agent(
        f"Role: {SPECIALIST_HINTS.get(r, r)}\nMission: {mission_id}\nTask: {task}\n{READ_ONLY_RULE}",
        schema=VERDICT_SCHEMA,
        role=f"TEL99 {r}",
        type_name="research",
        workspace="inherit",
    ),
)

phase("Independent Verification")
summary_json = json.dumps(specialist_reports, ensure_ascii=False)
verifier_report = await agent(
    f"You are tel99-verifier. Independently challenge and verify the specialist reports below "
    f"for mission {mission_id} on task: {task}\n{READ_ONLY_RULE}\nReports:\n{summary_json}",
    schema=VERDICT_SCHEMA,
    role="TEL99 Verifier",
    type_name="research",
    workspace="inherit",
)

result = {
    "mission_id": mission_id,
    "specialists_count": len(specialist_reports) + 1,
    "specialist_reports": specialist_reports,
    "verifier_report": verifier_report,
}
print(json.dumps(result, indent=2, ensure_ascii=False))
result
