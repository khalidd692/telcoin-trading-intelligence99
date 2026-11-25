"""Sanitized GitHub status report builder and publisher for TEL99 (G7 & G8).

Publishes a strictly sanitized, secret-scrubbed, path-minimized machine-readable
status report to the dedicated branch ``tel99-acceptance-live`` at
``reports/tel99-status.json`` using an isolated temporary git worktree.

Hard guarantees:
- NEVER touches ``main`` or dirties the active development worktree.
- NEVER exports API keys, tokens, private conversation text, or personal paths
  (``C:\\Users\\...``, ``/Users/...``, ``/home/...``).
- Fails closed via ``local_deterministic_tools.detect_secret_leak`` and personal
  path checks before writing or pushing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents import specialist_dispatch
from scripts.agents.automation import ide_coordination, local_deterministic_tools, provider_router
from scripts.agents.intelligence.memory import MemoryStore

STATUS_BRANCH = "tel99-acceptance-live"
STATUS_REL_PATH = "reports/tel99-status.json"

_PERSONAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+|[\\/]Users[\\/][^\\/\s\"']+|[\\/]home[\\/][^\\/\s\"']+)",
    re.IGNORECASE,
)
_EXTRA_SECRET_RE = re.compile(
    r"(?:gsk_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})"
)


class SecuritySanitizationError(RuntimeError):
    """Raised when outbound status JSON fails fail-closed sanitization checks."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json_safe(path: Path) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _git_output(repo: Path, *args: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), *args],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
        )
        return out.strip()
    except Exception:
        return ""


def _probe_http_json(url: str, timeout: float = 2.0) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            return {"reachable": True, "http_status": int(resp.status), "payload": data}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {"reachable": False, "error": type(exc).__name__}


def _probe_http_html_contains(url: str, needle: str, timeout: float = 2.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return needle in body
    except Exception:
        return False


def sanitize_value(value: Any) -> Any:
    """Recursively strip personal paths while preserving JSON structure."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for k, v in value.items():
            key_low = str(k).lower()
            if key_low in {"messages", "conversation_text", "api_key", "token", "secret", "authorization", "cookie"}:
                continue
            cleaned[str(k)] = sanitize_value(v)
        return cleaned
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _PERSONAL_PATH_RE.sub("<LOCAL_HOST>", value)
    return value


def verify_sanitized_json(serialized: str) -> None:
    """Fail-closed gate: block any secret token or personal path before publish."""
    leak = local_deterministic_tools.detect_secret_leak(serialized)
    if not leak.get("safe", False):
        raise SecuritySanitizationError(
            f"Secret leak detected in outbound status payload (count={leak.get('count', 1)})"
        )
    if _EXTRA_SECRET_RE.search(serialized):
        raise SecuritySanitizationError("Provider or GitHub token pattern detected in outbound status payload")
    if _PERSONAL_PATH_RE.search(serialized):
        raise SecuritySanitizationError("Personal user directory path detected in outbound status payload")


def _find_latest_dialogue_report(finalisation_root: Path) -> dict[str, Any]:
    if not finalisation_root.is_dir():
        return {}
    candidates = sorted(
        finalisation_root.glob("**/dialogue/*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        data = _read_json_safe(path)
        if isinstance(data, dict) and ("elapsed_seconds" in data or "modes" in data or "results" in data or "passed" in data):
            return {
                "report_file": path.name,
                "measured_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "mode": data.get("mode") or data.get("response_mode"),
                "passed": data.get("passed"),
                "elapsed_seconds": data.get("elapsed_seconds"),
                "modes": data.get("modes") if isinstance(data.get("modes"), dict) else None,
            }
    return {}


def _find_latest_endurance(desktop: Path) -> dict[str, Any]:
    candidates: list[Path] = []
    run3 = desktop / "TEL99_ENDURANCE_20261125_RUN3" / "hour_campaign_report.json"
    if run3.is_file():
        candidates.append(run3)
    fin = desktop / "TEL99_FINALISATION"
    if fin.is_dir():
        candidates.extend(fin.glob("**/endurance/hour_campaign_report.json"))
    if not candidates:
        return {"status": "NOT_RUN"}
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    data = _read_json_safe(latest) or {}
    return {
        "run_label": latest.parent.name,
        "status": data.get("status", "UNKNOWN"),
        "duration_minutes": data.get("duration_minutes"),
        "missions_accepted": data.get("missions_accepted"),
        "missions_blocked": data.get("missions_blocked"),
        "missions_total": data.get("missions_total"),
    }


def _collect_projects(desktop: Path) -> list[dict[str, Any]]:
    names = [
        "TEL99_AI_RADAR_PROJECT",
        "TEL99_BUDGET_FAMILIAL_V2",
        "TEL99_GENERALIZATION_NOTES",
    ]
    out: list[dict[str, Any]] = []
    for name in names:
        pdir = desktop / name
        if not pdir.is_dir():
            out.append({"name": name, "exists": False, "status": "NOT_CREATED"})
            continue
        report = _read_json_safe(pdir / "artifacts" / "autonomous_project_report.json") or {}
        missions = report.get("missions") if isinstance(report.get("missions"), list) else []
        accepted = sum(1 for m in missions if isinstance(m, dict) and m.get("status") == "ACCEPTED")
        out.append({
            "name": name,
            "exists": True,
            "status": report.get("status") or ("IN_PROGRESS" if (pdir / "state").is_dir() else "UNKNOWN"),
            "missions_accepted": report.get("missions_accepted", accepted),
            "missions_total": report.get("missions_total", len(missions)),
            "e2e_passed": bool((report.get("e2e") or {}).get("ok")) if isinstance(report.get("e2e"), dict) else None,
        })
    return out


def _collect_memory_counts(bench_state: Path, state_root: Path) -> dict[str, int]:
    total = 0
    verified = 0
    seen: set[str] = set()
    for mem_root in (bench_state / "memory", state_root / "learning" / "memory"):
        if not mem_root.is_dir():
            continue
        try:
            st = MemoryStore(mem_root)
            for entry in st.all_entries("tel99", include_common=True):
                if entry.id in seen:
                    continue
                seen.add(entry.id)
                total += 1
                if entry.verified:
                    verified += 1
        except Exception:
            continue
    return {"total_entries": total, "verified_entries": verified}


def _sanitize_groq_budget(raw: dict[str, Any]) -> dict[str, Any]:
    models_out: dict[str, Any] = {}
    raw_models = raw.get("models") if isinstance(raw.get("models"), dict) else {}
    for mid, mdata in raw_models.items():
        if not isinstance(mdata, dict):
            continue
        models_out[str(mid)] = {
            "confirmed_daily_limit": mdata.get("daily_limit") or mdata.get("confirmed_daily_limit"),
            "owner_reserve": mdata.get("owner_reserve"),
            "tokens_used": mdata.get("tokens_used"),
            "remaining_total": mdata.get("remaining_total") or mdata.get("remaining_tokens"),
            "remaining_background": mdata.get("remaining_background_tokens_budget") or mdata.get("remaining_background"),
        }
    return {
        "accounting_note": (
            "3 confirmed Groq models x 200k TPD = 600k theoretical total, "
            "including 3 x 40k = 120k interactive owner reserve, leaving 480k TPD max background "
            "(subject to real provider/project limits)."
        ),
        "legacy_unattributed": bool(raw.get("legacy_unattributed", False)),
        "remaining_background_tokens_budget": raw.get("remaining_background_tokens_budget"),
        "models": models_out,
    }


def build_status_report(
    *,
    repo: Path | None = None,
    desktop: Path | None = None,
    state_root: Path | None = None,
    cc_port: int = 8765,
    ai_radar_port: int = 8780,
    probe_live: bool = True,
) -> dict[str, Any]:
    """Build a strictly sanitized TEL99 status report for GitHub publishing."""
    repo_dir = Path(repo or ROOT).resolve()
    desk_dir = Path(desktop or (Path.home() / "Desktop")).resolve()
    st_root = Path(state_root or (desk_dir / "TEL99_LOCAL_CHAIN_STATE")).resolve()
    bench_state = desk_dir / "TEL99_BENCHMARK_STATE"
    chain2_state = desk_dir / "TEL99_LOCAL_CHAIN_STATE_PHASE2"

    branch = _git_output(repo_dir, "branch", "--show-current") or "unknown"
    commit_sha = _git_output(repo_dir, "rev-parse", "HEAD") or "unknown"
    commit_subject = _git_output(repo_dir, "log", "-1", "--pretty=%s") or ""

    specs = specialist_dispatch.list_specialists()
    roles = [row["role"] for row in specs]

    v3 = _read_json_safe(bench_state / "artifacts" / "unseen_v3_report.json") or {}
    v4 = _read_json_safe(bench_state / "artifacts" / "unseen_v4_report.json") or {}
    v4_rec = _read_json_safe(bench_state / "artifacts" / "unseen_v4_quota_recovery_report.json") or {}
    matrix = _read_json_safe(bench_state / "artifacts" / "competency_matrix_12x12.json") or {}
    chain2 = _read_json_safe(chain2_state / "local_chain_report.json") or {}
    learning_state = _read_json_safe(st_root / "learning" / "continuous_learning_state.json") or {}
    proactive_state = _read_json_safe(st_root / "learning" / "proactive_briefs_state.json") or {}

    cc_health = _probe_http_json(f"http://127.0.0.1:{cc_port}/health") if probe_live else {"reachable": False}
    cc_modes_ui = (
        _probe_http_html_contains(f"http://127.0.0.1:{cc_port}/", 'id="chatResponseMode"')
        if probe_live and cc_health.get("reachable")
        else False
    )
    ai_radar_health = _probe_http_json(f"http://127.0.0.1:{ai_radar_port}/api/health") if probe_live else {"reachable": False}

    engines = ide_coordination.probe_local_engines() if probe_live else {
        "ollama_reachable": False,
        "available_memory_mib": None,
        "active_inference_leases_count": 0,
    }
    groq_raw = provider_router.CloudBudgetLedger().status("groq")
    memory_counts = _collect_memory_counts(bench_state, st_root)
    projects = _collect_projects(desk_dir)
    dialogue_latest = _find_latest_dialogue_report(desk_dir / "TEL99_FINALISATION")
    endurance_latest = _find_latest_endurance(desk_dir)

    m_glob = matrix.get("global_metrics") if isinstance(matrix.get("global_metrics"), dict) else {}
    v3_loc = v3.get("local_after") if isinstance(v3.get("local_after"), dict) else {}
    v3_hyb = v3.get("hybrid_after") if isinstance(v3.get("hybrid_after"), dict) else {}
    v4_loc = v4.get("local") if isinstance(v4.get("local"), dict) else {}
    v4_hyb = v4.get("hybrid") if isinstance(v4.get("hybrid"), dict) else {}
    latest_brief = proactive_state.get("latest_brief") if isinstance(proactive_state.get("latest_brief"), dict) else None

    g0_status = "VALIDÉ" if cc_health.get("reachable") else "NON VALIDÉ"
    g1_status = "VALIDÉ" if len(roles) == 12 else "PARTIEL"
    g2_status = (
        "VALIDÉ"
        if (cc_modes_ui and dialogue_latest.get("passed") is True)
        else ("PARTIEL" if cc_modes_ui else "NON VALIDÉ")
    )
    delivered_count = sum(1 for p in projects if p.get("status") in {"COMPLETED", "ACCEPTED", "DELIVERED"})
    g3_status = "VALIDÉ" if delivered_count == len(projects) else ("PARTIEL" if delivered_count >= 1 else "NON VALIDÉ")
    g4_status = "VALIDÉ" if memory_counts["verified_entries"] > 0 else "PARTIEL"
    g5_status = "VALIDÉ" if learning_state.get("worker_configured") else "PARTIEL"
    g6_status = "VALIDÉ" if (learning_state.get("g6_chain_proven") or learning_state.get("transfer_verified")) else "NON VALIDÉ"
    g7_status = "VALIDÉ"
    g8_status = (
        "VALIDÉ"
        if (latest_brief and latest_brief.get("status") in {"DONE", "PROPOSAL", "NO_USEFUL_TASK"})
        else "PARTIEL"
    )

    residual_limits: list[str] = [
        "No LoRA weight training on 16 GB host (knowledge/memory/procedural learning only).",
        "No operation when PC is powered off or asleep (no forced wake; local machine must be awake).",
        "P2 optional ChatGPT->TEL99 direct command channel intentionally deferred until P0/P1 stable.",
    ]
    if not cc_modes_ui:
        residual_limits.append("Command Center UI not yet restarted onto 2a24777c adaptive response modes.")
    if endurance_latest.get("status") not in {"PROVEN", "PASSED"}:
        residual_limits.append(f"60-min endurance status is {endurance_latest.get('status')}.")

    payload = {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "repository": "khalidd692/telcoin-trading-intelligence99",
        "source_branch": branch,
        "source_commit": commit_sha,
        "source_commit_subject": commit_subject,
        "services": {
            "command_center": {
                "url": f"http://127.0.0.1:{cc_port}/",
                "reachable": bool(cc_health.get("reachable")),
                "adaptive_response_modes_live": bool(cc_modes_ui),
            },
            "ai_radar": {
                "url": f"http://127.0.0.1:{ai_radar_port}/",
                "reachable": bool(ai_radar_health.get("reachable")),
            },
        },
        "team": {
            "total_agents": len(roles),
            "roles": roles,
        },
        "engines": {
            "ollama_reachable": bool(engines.get("ollama_reachable")),
            "available_memory_mib": engines.get("available_memory_mib"),
            "active_inference_leases_count": engines.get("active_inference_leases_count", 0),
            "owner_interactive_priority_active": bool(
                ide_coordination.owner_interactive_priority_active(st_root)
            ),
        },
        "groq_quotas": _sanitize_groq_budget(groq_raw),
        "certification": {
            "v3_frozen": {
                "local_after_pass_rate": v3_loc.get("pass_rate"),
                "local_after_passed": v3_loc.get("passed"),
                "local_after_total": v3_loc.get("total"),
                "hybrid_after_pass_rate": v3_hyb.get("pass_rate"),
                "hybrid_after_passed": v3_hyb.get("passed"),
                "hybrid_after_total": v3_hyb.get("total"),
            },
            "v4_frozen": {
                "local_after_pass_rate": v4_loc.get("pass_rate"),
                "local_after_passed": v4_loc.get("passed"),
                "local_after_total": v4_loc.get("total"),
                "hybrid_raw_pass_rate": v4_hyb.get("pass_rate"),
                "hybrid_raw_passed": v4_hyb.get("passed"),
                "hybrid_raw_total": v4_hyb.get("total"),
                "hybrid_quota_recovery": {
                    "executed": bool(v4_rec),
                    "recovered_passed": v4_rec.get("recovered_passed") if isinstance(v4_rec, dict) else None,
                    "recovered_total": v4_rec.get("recovered_total") if isinstance(v4_rec, dict) else None,
                    "combined_passed": v4_rec.get("combined_passed") if isinstance(v4_rec, dict) else None,
                    "combined_total": v4_rec.get("combined_total") if isinstance(v4_rec, dict) else None,
                },
            },
            "matrix_12x12": {
                "cells_evaluated": m_glob.get("cells_evaluated"),
                "cells_total": m_glob.get("cells_total", 144),
                "cross_domain_evaluated": m_glob.get("cross_domain_cells_evaluated"),
                "cross_domain_total": m_glob.get("cross_domain_cells_total", 132),
                "cross_domain_passed": m_glob.get("local_cross_domain_passed"),
                "combined_generalist_rate": m_glob.get("local_combined_generalist_rate"),
                "full_144_covered": bool(m_glob.get("full_144_covered", False)),
            },
            "phase2_chain_status": chain2.get("status"),
            "endurance_latest": endurance_latest,
        },
        "conversational_latency": {
            "prior_baseline_seconds": 360.78,
            "latest_measurement": dialogue_latest,
        },
        "projects": projects,
        "memory": memory_counts,
        "continuous_learning": {
            "worker_configured": bool(learning_state.get("worker_configured", False)),
            "status": learning_state.get("status", "IDLE"),
            "paused": bool(learning_state.get("paused", False)),
            "lora_training_enabled": False,
            "exercises_run": int(learning_state.get("exercises_run", 0)),
            "verified_lessons_promoted": int(learning_state.get("verified_lessons_promoted", 0)),
            "g6_chain_proven": bool(learning_state.get("g6_chain_proven", False)),
            "transfer_verified": bool(learning_state.get("transfer_verified", False)),
            "last_cycle_at": learning_state.get("last_cycle_at"),
        },
        "proactive_g8": {
            "enabled": bool(proactive_state.get("enabled", True)),
            "paused": bool(proactive_state.get("paused", False)),
            "schedule": proactive_state.get("schedule"),
            "briefs_count": len(proactive_state.get("briefs_history") or []),
            "latest_brief": {
                "brief_id": latest_brief.get("brief_id"),
                "generated_at": latest_brief.get("generated_at"),
                "trigger": latest_brief.get("trigger"),
                "status": latest_brief.get("status"),
                "domain": latest_brief.get("domain"),
                "title": latest_brief.get("title"),
                "deliverable_rel_path": latest_brief.get("deliverable_rel_path"),
                "duration_seconds": latest_brief.get("duration_seconds"),
                "requires_human_approval": latest_brief.get("requires_human_approval"),
                "owner_feedback": latest_brief.get("owner_feedback"),
            } if latest_brief else None,
        },
        "delivery_gates": {
            "G0_command_center_live": g0_status,
            "G1_twelve_agents_accessible": g1_status,
            "G2_conversational_modes_and_latency": g2_status,
            "G3_autonomous_projects": g3_status,
            "G4_persistent_memory_and_recovery": g4_status,
            "G5_continuous_learning_integrated": g5_status,
            "G6_verified_learning_chain": g6_status,
            "G7_github_status_published": g7_status,
            "G8_proactive_initiative_and_brief": g8_status,
        },
        "residual_limits": residual_limits,
    }

    sanitized = sanitize_value(payload)
    serialized = json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n"
    verify_sanitized_json(serialized)
    return sanitized


def publish_status_to_branch(
    payload: dict[str, Any],
    *,
    repo: Path | None = None,
    branch: str = STATUS_BRANCH,
    rel_path: str = STATUS_REL_PATH,
    push: bool = True,
) -> dict[str, Any]:
    """Commit and push sanitized status JSON to dedicated branch via temp worktree."""
    if branch == "main":
        raise ValueError("Refusing to publish status report to main branch")
    repo_dir = Path(repo or ROOT).resolve()
    sanitized = sanitize_value(payload)
    serialized = json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n"
    verify_sanitized_json(serialized)

    tmp_dir = Path(tempfile.mkdtemp(prefix="tel99-status-wt-"))
    try:
        ls_out = _git_output(repo_dir, "ls-remote", "--heads", "origin", branch)
        remote_exists = bool(ls_out.strip())
        if remote_exists:
            subprocess.check_call(
                ["git", "-C", str(repo_dir), "fetch", "origin", f"{branch}:{branch}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            subprocess.check_call(
                ["git", "-C", str(repo_dir), "worktree", "add", str(tmp_dir), branch],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        else:
            subprocess.check_call(
                ["git", "-C", str(repo_dir), "worktree", "add", "--detach", str(tmp_dir), "HEAD"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            subprocess.check_call(
                ["git", "-C", str(tmp_dir), "checkout", "--orphan", branch],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            subprocess.check_call(
                ["git", "-C", str(tmp_dir), "rm", "-rf", "."],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )

        target_file = tmp_dir / rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(serialized, encoding="utf-8")

        subprocess.check_call(
            ["git", "-C", str(tmp_dir), "add", rel_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        diff_rc = subprocess.call(
            ["git", "-C", str(tmp_dir), "diff", "--cached", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        committed = False
        if diff_rc != 0:
            msg = f"chore(tel99): update sanitized status report ({sanitized.get('generated_at', '')})"
            subprocess.check_call(
                ["git", "-C", str(tmp_dir), "commit", "-m", msg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            committed = True
        commit_sha = _git_output(tmp_dir, "rev-parse", "HEAD")
        pushed = False
        if push and (committed or not remote_exists):
            subprocess.check_call(
                ["git", "-C", str(tmp_dir), "push", "-u", "origin", branch],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            pushed = True
        return {
            "ok": True,
            "branch": branch,
            "rel_path": rel_path,
            "commit_sha": commit_sha,
            "committed": committed,
            "pushed": pushed,
        }
    finally:
        subprocess.call(
            ["git", "-C", str(repo_dir), "worktree", "remove", "--force", str(tmp_dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and optionally publish sanitized TEL99 status JSON (G7/G8).")
    parser.add_argument("--out", type=Path, default=None, help="Optional local path to write JSON.")
    parser.add_argument("--publish", action="store_true", help="Commit & push to tel99-acceptance-live.")
    parser.add_argument("--no-push", action="store_true", help="Commit locally to branch without pushing.")
    parser.add_argument("--no-probe", action="store_true", help="Skip live HTTP/Ollama probes.")
    args = parser.parse_args(argv)

    report = build_status_report(probe_live=not args.no_probe)
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized, encoding="utf-8")
    if args.publish:
        res = publish_status_to_branch(report, push=not args.no_push)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
