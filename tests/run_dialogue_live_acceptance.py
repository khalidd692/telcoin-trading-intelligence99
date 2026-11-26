"""Opt-in real confidential conversation regression; never changes production conversations."""
from pathlib import Path
import argparse
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.agents.automation import command_center_service as cc, local_deterministic_tools as dt

QUESTION = ("Je dispose d'un ordinateur Windows avec 16 Go de RAM, aucun GPU dédié et aucun budget supplémentaire. "
            "Je souhaite créer une entreprise dont une grande partie du travail serait réalisée par des agents IA. "
            "Propose-moi trois activités commerciales réalistes, compare leur rentabilité potentielle, leurs difficultés et leurs risques. "
            "Choisis la plus pertinente et explique précisément comment ton équipe pourrait la développer avec mes ressources actuelles. "
            "Distingue ce que vous savez réellement faire de ce qui nécessite encore des capacités supplémentaires.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("fast", "auto", "deep"), default="deep")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / "dialogue_report.json"
    if dest.exists():
        raise SystemExit("Existing report: choose a new output directory")
    svc = cc.CommandCenterService(args.out / "isolated_state")
    conv = svc.create_conversation(title="Regression dialogue confidentielle", role="coordination", team_mode=True,
                                   confidential=True, hybrid=False)
    # Reproduce an unrelated prior conversation without calling any model.
    def seed(cur):
        cur["messages"] = [
            {"id":"old-u","role":"user","content":"Parlons d'abord d'un Data Pipeline fictif."},
            {"id":"old-a","role":"assistant","content":"Le domaine du Data Pipeline reste à déterminer."},
        ]
        return cur
    dt.locked_json_update(svc._conv_path(conv["id"]), seed)
    job = svc.submit_chat_message(conv_id=conv["id"], message=QUESTION, response_mode=args.mode)
    expected_delegates = cc.plan_dialogue_delegation(QUESTION, mode=args.mode, team_mode=True)
    deadline = time.monotonic() + 1800
    while True:
        job = svc.get_job(job["job_id"])
        if job["status"] in ("DONE", "ERROR", "CANCELLED"):
            break
        if time.monotonic() > deadline:
            svc.cancel_job(job["job_id"])
            break
        time.sleep(2)
    msg = job.get("assistant_message") or {}
    coverage = msg.get("coverage_check") or {}
    report = {
        "status": "STRUCTURAL_PASS" if job["status"] == "DONE" and
            coverage.get("requested_sections", 0) >= 10 and not coverage.get("missing_sections") and
            msg.get("cloud_calls") == 0 and len(msg.get("delegated_specialists") or []) == expected_delegates
            else "NOT_VALIDATED",
        "semantic_review_required": True,
        "response_mode": args.mode,
        "expected_delegates": expected_delegates,
        "question": QUESTION,
        "job_status": job["status"],
        "error": job.get("error"),
        "coverage": coverage,
        "answer": msg.get("content"),
        "model": msg.get("model_used"),
        "cloud_calls": msg.get("cloud_calls"),
        "duration_seconds": msg.get("duration_seconds"),
        "specialists": msg.get("delegated_specialists"),
    }
    dt.write_json_atomic_locked(dest, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "STRUCTURAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
