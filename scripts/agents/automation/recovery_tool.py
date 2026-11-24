"""Safe operator inspection and STOP-marker recovery without touching CAS history."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.agents.automation.autonomy_runtime import LEGACY_STOP
from scripts.agents.automation.local_codex import exclusive
from scripts.agents.protocol.store import FileStore


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
    parser.add_argument("action", choices=("inspect", "clear-stop"))
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "clear-stop":
        report = clear_stops(args.state)
    else:
        report = inspect_state(args.state)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
