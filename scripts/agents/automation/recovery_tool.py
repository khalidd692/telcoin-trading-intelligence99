"""Safe operator inspection and STOP-marker recovery without touching CAS history."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation.autonomy_runtime import LEGACY_STOP, classify_failure
from scripts.agents.automation.local_codex import exclusive
from scripts.agents.protocol.store import FileStore
import time


INFRA_RECOVERABLE_CATEGORIES = frozenset({"PROVIDER_ERROR", "ENVIRONMENT_ERROR"})
MAX_INFRA_RECOVERIES = 2


def requeue_infra_failed_mission(
    campaign_dir: Path | str,
    mission_id: str,
    *,
    reason: str = "infra_ram_or_provider_recovery",
    max_infra_recoveries: int = MAX_INFRA_RECOVERIES,
) -> dict:
    """Safely resume a mission blocked/rejected ONLY by an infrastructure/provider error.

    Invariants:
    - NEVER replays an ACCEPTED mission.
    - NEVER deletes or resets any historical ledger entry; archives previous failure into
      `infra_recovery_history` via CAS.
    - Refuses to requeue genuine MODEL_ERROR / VERIFICATION_ERROR / CONTRACT_ERROR failures.
    """
    cdir = Path(campaign_dir).resolve()
    ledger_dir = cdir / "ledger"
    if not ledger_dir.is_dir():
        return {"ok": False, "mission_id": mission_id, "reason": "ledger directory not found"}

    with exclusive(cdir / "runtime.lock"):
        store = FileStore(ledger_dir)
        key = f"kilo-local/{mission_id}"
        old = store.read(key, default=None)
        if not isinstance(old, dict):
            return {"ok": False, "mission_id": mission_id, "reason": "mission checkpoint not found"}
        status = old.get("status")
        if status == "ACCEPTED":
            return {"ok": False, "mission_id": mission_id, "status": status, "reason": "refused: mission already ACCEPTED"}
        if status not in ("BLOCKED", "REJECTED", "AWAITING_HUMAN"):
            return {"ok": False, "mission_id": mission_id, "status": status, "reason": "mission not in failed terminal state"}

        prior_count = int(old.get("infra_recovery_count") or 0)
        if prior_count >= max_infra_recoveries:
            return {
                "ok": False,
                "mission_id": mission_id,
                "status": status,
                "reason": f"infra recovery budget exhausted ({prior_count}/{max_infra_recoveries})",
            }

        # Inspect both checkpoint reason and nested verification/result error
        res_err = ""
        if isinstance(old.get("result"), dict):
            ver = old["result"].get("verification")
            if isinstance(ver, dict):
                res_err = str(ver.get("error") or "")
        ver_err = str((old.get("verification") or {}).get("error") or "") if isinstance(old.get("verification"), dict) else ""
        combined_err = " ".join(x for x in (str(old.get("error") or ""), res_err, ver_err) if x)
        category = classify_failure(str(old.get("reason") or ""), combined_err)
        if category not in INFRA_RECOVERABLE_CATEGORIES:
            return {
                "ok": False,
                "mission_id": mission_id,
                "status": status,
                "failure_category": category,
                "reason": f"refused: failure classified as {category} (not infrastructure error)",
            }

        history = list(old.get("infra_recovery_history") or [])
        history.append({
            "recovered_at": time.time(),
            "previous_status": status,
            "previous_reason": old.get("reason"),
            "previous_error": combined_err[:240],
            "failure_category": category,
            "recovery_reason": reason,
        })
        updated = {
            **old,
            "status": "ACK",
            "execution_status": "NOT_STARTED",
            "at": time.time(),
            "reason": f"requeued after {category}: {reason}",
            "infra_recovery_count": prior_count + 1,
            "infra_recovery_history": history,
        }
        updated.pop("result", None)
        updated.pop("verification", None)
        if not store.put_cas(key, updated, old):
            return {"ok": False, "mission_id": mission_id, "reason": "CAS conflict during requeue"}
        return {
            "ok": True,
            "mission_id": mission_id,
            "previous_status": status,
            "new_status": "ACK",
            "failure_category": category,
            "infra_recovery_count": prior_count + 1,
        }


def inspect_state(state_root: Path | str) -> dict:
    """Inspect STOP markers, blocked/interrupted checkpoints, and pending outbox items."""
    root = Path(state_root).resolve()
    parent_stop = (root / "stop.request").exists()
    global_stop = LEGACY_STOP.exists()
    campaign_stops: list[str] = []
    blocked_missions: list[dict] = []
    awaiting_human: list[dict] = []
    crashed_running: list[dict] = []
    pending_outbox: list[dict] = []

    if root.is_dir():
        for camp_dir in sorted(root.glob("campaign-*")):
            if not camp_dir.is_dir():
                continue
            issue = camp_dir.name
            if (camp_dir / "stop.request").exists():
                campaign_stops.append(issue)
            ledger_dir = camp_dir / "ledger"
            if not ledger_dir.is_dir():
                continue
            store = FileStore(ledger_dir)
            for key in sorted(store.keys("kilo-local")):
                row = store.get(key)
                if not isinstance(row, dict):
                    continue
                status = row.get("status")
                entry = {
                    "campaign": issue,
                    "mission_id": row.get("id"),
                    "status": status,
                    "reason": row.get("reason"),
                    "attempt": row.get("attempt"),
                }
                if status == "AWAITING_HUMAN":
                    awaiting_human.append(entry)
                elif status in ("BLOCKED", "REJECTED"):
                    blocked_missions.append(entry)
                elif status == "RUNNING":
                    crashed_running.append(entry)
            for key in sorted(store.keys("kilo-github/outbox")):
                row = store.get(key)
                if isinstance(row, dict) and not row.get("url"):
                    pending_outbox.append({
                        "campaign": issue,
                        "key": key,
                        "not_sent": bool(row.get("not_sent")),
                    })

    actions: list[str] = []
    if global_stop:
        actions.append(f"Remove global stop marker after audit: {LEGACY_STOP}")
    if parent_stop or campaign_stops:
        actions.append("Run recovery_tool clear-stop --state <dir> after verifying no active lock.")
    if crashed_running:
        actions.append("A RUNNING checkpoint exists; starting Runtime will safely move it to AWAITING_HUMAN without replay.")
    if awaiting_human or blocked_missions:
        actions.append("Blocked/AWAITING_HUMAN checkpoints are preserved; use -IsolateBlocked so healthy controllers continue.")

    return {
        "schema_version": 1,
        "state_root": str(root),
        "global_stop": global_stop,
        "parent_stop": parent_stop,
        "campaign_stops": campaign_stops,
        "blocked_missions": blocked_missions,
        "awaiting_human": awaiting_human,
        "crashed_running": crashed_running,
        "pending_outbox": pending_outbox,
        "needs_attention": bool(
            global_stop or parent_stop or campaign_stops or blocked_missions
            or awaiting_human or crashed_running or pending_outbox
        ),
        "recommended_actions": actions,
    }


def clear_stops(state_root: Path | str) -> dict:
    """Safely clear local stop.request markers when no supervisor holds the session lock."""
    root = Path(state_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cleared: list[str] = []
    with exclusive(root / "multi-session.lock"):
        parent_stop = root / "stop.request"
        if parent_stop.exists():
            parent_stop.unlink()
            cleared.append(str(parent_stop))
        for camp_dir in sorted(root.glob("campaign-*")):
            if not camp_dir.is_dir():
                continue
            camp_stop = camp_dir / "stop.request"
            if camp_stop.exists():
                with exclusive(camp_dir / "runtime.lock"):
                    camp_stop.unlink()
                    cleared.append(str(camp_stop))
    return {
        "schema_version": 1,
        "state_root": str(root),
        "cleared": cleared,
        "global_stop_still_present": LEGACY_STOP.exists(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "clear-stop", "requeue-infra"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--mission-id", default="")
    parser.add_argument("--reason", default="infra_ram_or_provider_recovery")
    args = parser.parse_args(argv)
    if args.action == "clear-stop":
        report = clear_stops(args.state)
    elif args.action == "requeue-infra":
        if not args.mission_id:
            raise SystemExit("--mission-id is required for requeue-infra")
        report = requeue_infra_failed_mission(args.state, args.mission_id, reason=args.reason)
    else:
        report = inspect_state(args.state)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
