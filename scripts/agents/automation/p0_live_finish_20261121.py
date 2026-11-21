"""Bounded P0 live closure: replay A/B idempotently, qualify Qwen4 on C.

Use the existing Hermes relay and #124 supervisor only. No new supervisor,
no code-editing worker, no automatic merge, no paid model fallback. Runs on
the owner's Windows PC because the runtime and Hermes usage DB are local.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from autonomy_runtime import Runtime
from github_mission_source import default_fetcher, fetch_comments, github_source
from hermes_github_adapter import EVENT_BLOCK_RE, REPO

MANDATE_ID = 7024804657
MISSION_A = "HERMES-LIVE-20261121-A"
MISSION_B = "HERMES-LIVE-20261121-B"
MISSION_C = "HERMES-QWEN4-20261121-C"
MODEL = "qwen/qwen4-max:free"
STATE = Path(os.environ["LOCALAPPDATA"]) / "hermes-tel99" / "autonomous" / "recipe-20261121-AB"
ROOT = Path(__file__).resolve().parents[3]
ADAPTER = ROOT / "scripts" / "agents" / "automation" / "hermes_github_adapter.py"


def event_counts():
    counts = Counter()
    for comment in fetch_comments(REPO, 94):
        if not isinstance(comment, dict):
            continue
        match = EVENT_BLOCK_RE.search(comment.get("body") or "")
        if not match:
            continue
        try:
            event = json.loads(match.group(1))
        except ValueError:
            continue
        if event.get("mission_id") in {MISSION_A, MISSION_B, MISSION_C}:
            counts[(event["mission_id"], event.get("status"))] += 1
    return counts


def accepted(runtime, mission):
    return runtime.state(mission).get("status") == "ACCEPTED"


def check_cost(runtime, mission):
    result = (runtime.state(mission).get("result") or {})
    cost = result.get("provider_evidence") or {}
    if (result.get("model") != MODEL or cost.get("model") != MODEL
            or cost.get("billing_provider") != "nous"
            or cost.get("estimated_cost_usd") != 0.0
            or cost.get("actual_cost_usd") != 0.0
            or not result.get("session_id")):
        raise RuntimeError("QWEN_COST_OR_MODEL_NOT_VERIFIED; do not retry BLOCKED mission")
    return {"model": result["model"],
            "session_id": result["session_id"],
            "estimated_cost_usd": cost["estimated_cost_usd"],
            "actual_cost_usd": cost["actual_cost_usd"],
            "artifact_sha256": result["sha256"]}


def run_once(sha, exe):
    cmd = [sys.executable, "-B", str(ADAPTER), "run",
           "--state", str(STATE), "--issue", "94",
           "--mandate-issue", "67", "--mandate-comment", str(MANDATE_ID),
           "--mandate-sha256", sha, "--model", MODEL,
           "--cli-exe", exe, "--once", "--seconds", "570",
           "--max-tasks", "1"]
    return subprocess.run(cmd, check=False, cwd=ROOT).returncode


def main():
    if (STATE / "stop.request").exists():
        raise RuntimeError("STOP_REQUESTED: no replay or new worker")
    exe = shutil.which("hermes")
    if not exe:
        raise RuntimeError("Hermes CLI not found")
    mandate = default_fetcher(f"repos/{REPO}/issues/comments/{MANDATE_ID}")
    if (mandate.get("user") or {}).get("login") != "khalidd692":
        raise RuntimeError("Mandate not owner-authored")
    sha = hashlib.sha256((mandate.get("body") or "").encode("utf-8")).hexdigest()
    payload = github_source(REPO, 94, 67, MANDATE_ID, mandate_sha256=sha)
    by_id = {m["id"]: m for m in payload["missions"]}
    if not {MISSION_A, MISSION_B, MISSION_C}.issubset(by_id):
        raise RuntimeError("Missing authenticated or unexpired A/B/C approvals")

    runtime = Runtime(STATE)
    if not accepted(runtime, by_id[MISSION_A]) or not accepted(runtime, by_id[MISSION_B]):
        raise RuntimeError("Previous A/B state is not ACCEPTED: no execution")
    before = event_counts()
    for key in ((MISSION_A, "ACK"), (MISSION_A, "ACCEPTED"),
                (MISSION_B, "ACK"), (MISSION_B, "ACCEPTED")):
        if before[key] != 1:
            raise RuntimeError(f"Expected exactly one prior A/B event: {key}={before[key]}")

    print("A/B VERIFIED. Python-computed mandate SHA:", sha, flush=True)
    if not accepted(runtime, by_id[MISSION_C]):
        print("Qualifying Qwen on one new synthetic text mission C", flush=True)
        first = run_once(sha, exe)
        if first:
            raise RuntimeError(f"QWEN_RUN_BLOCKED exit={first}; preserve state; no retry")

    runtime = Runtime(STATE)
    if not accepted(runtime, by_id[MISSION_C]):
        raise RuntimeError("C did not reach ACCEPTED; preserve checkpoint")
    qwen = check_cost(runtime, by_id[MISSION_C])
    after_first = event_counts()
    for key in ((MISSION_A, "ACK"), (MISSION_A, "ACCEPTED"),
                (MISSION_B, "ACK"), (MISSION_B, "ACCEPTED"),
                (MISSION_C, "ACK"), (MISSION_C, "ACCEPTED")):
        if after_first[key] != 1:
            raise RuntimeError(f"Expected exactly one event after C: {key}={after_first[key]}")

    # Re-run on the same durable state to prove no new Hermes session nor POST.
    second = run_once(sha, exe)
    if second:
        raise RuntimeError(f"IDEMPOTENT_REPLAY_BLOCKED exit={second}")
    final_runtime = Runtime(STATE)
    if not all(accepted(final_runtime, by_id[mid]) for mid in
               (MISSION_A, MISSION_B, MISSION_C)):
        raise RuntimeError("One accepted state changed during replay")
    if check_cost(final_runtime, by_id[MISSION_C])["session_id"] != qwen["session_id"]:
        raise RuntimeError("Replay changed Qwen session ID")
    after_second = event_counts()
    if after_second != after_first:
        raise RuntimeError("Replay published an unexpected or duplicate GitHub event")

    receipt = {
        "status": "LIVE_SYNTHETIC_A_B_C_ACCEPTED",
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "mandate_sha256": sha,
        "missions": [MISSION_A, MISSION_B, MISSION_C],
        "zero_duplicate_post": True,
        "qwen": qwen,
        "note": "Synthetic text only, not 2 real code issues, not cloud PC-off."
    }
    file = STATE / "p0-live-qwen-receipt.json"
    file.write_text(json.dumps(receipt, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(receipt, indent=2, ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:400]},
                         ensure_ascii=True), flush=True)
        sys.exit(2)
