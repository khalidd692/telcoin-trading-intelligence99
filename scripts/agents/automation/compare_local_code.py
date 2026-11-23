"""Compare two completed, separately pinned fixed-model Night Lab sessions."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sys

from scripts.agents.automation.autonomy_runtime import fingerprint, local_codegen, seal, validate_contract
from scripts.agents.automation import local_model_routing
from scripts.agents.intelligence import catalog, router
from scripts.agents.intelligence.improvement import INCONCLUSIVE, Outcome, compare
from scripts.agents.intelligence.memory import _write_new_private
from scripts.agents.night_lab_20261123 import STATE_VERSION, load_registry
from scripts.agents.project_kit import strict_json
from scripts.agents.protocol.handoff import verify_mission

from local_codex import Blocked

_SHA = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_TERMINAL = {"ACCEPTED", "REJECTED", "BLOCKED", "AWAITING_HUMAN"}
_REQUIRED_CHECKS = {"bounded-model-receipt", "approved-function-diff", "baseline-fails", "candidate-passes"}


@dataclass(frozen=True)
class Session:
    root: Path
    pin: str
    model: str
    checkout: str
    missions: list[dict]
    reports: dict
    status: dict
    proofs: dict
    snapshot: bytes


def _sha(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _read(root, relative, *, limit=1_000_000):
    path = root / relative
    if path.resolve() != path or not path.is_file():
        raise ValueError(f"missing or redirected evidence: {relative}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"evidence exceeds the size limit: {relative}")
    return raw


def _object(raw, label):
    value = strict_json(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _metric(value, label):
    if value is None:
        return None
    if type(value) not in (int, float) or not 0 <= value <= 1_000_000_000 or not math.isfinite(value):
        raise ValueError(f"invalid measured {label}")
    return value


def _load_session(root, pin):
    if not _SHA.fullmatch(pin):
        raise ValueError("an operator-pinned lowercase SHA-256 is required for each registry")
    read = lambda name: _object(_read(root, name), name)
    meta = read("campaign.json")
    proofs = read("PREUVES.json")
    snapshot = _read(root, "status.json")
    status = _object(snapshot, "status.json")
    raw_registry = _read(root, "registry.json", limit=512_000)
    if (type(meta.get("version")) is not int or meta["version"] != STATE_VERSION
            or meta.get("registry_sha256") != pin or proofs.get("registre_sha256") != pin
            or _sha(raw_registry) != pin):
        raise ValueError("campaign and evidence registry digest do not match the operator pin")
    # The Night Lab also validates every approval and the admitted dependency graph.
    _object(raw_registry, "registry.json")
    _, missions = load_registry(root / "registry.json", pin)
    if any(m.keys() - {"max_attempts"} != local_codegen.FIELDS for m in missions):
        raise ValueError("each registry must pin one fixed model without routing or fallback")
    model_ids = {m["model"] for m in missions}
    if len(model_ids) != 1:
        raise ValueError("each registry must pin one fixed model without routing or fallback")
    phase, exit_code = status.get("phase"), status.get("worker_exit")
    checkout = status.get("checkout_sha")
    pid = status.get("supervisor_pid")
    if (phase not in ("COMPLETE", "BLOCKED") or type(exit_code) is not int or exit_code not in (0, 2)
            or proofs.get("campagne") != phase or proofs.get("code_sortie_superviseur") != exit_code
            or type(pid) is not int or pid <= 0 or proofs.get("pid_superviseur") != pid
            or not isinstance(checkout, str) or not _COMMIT.fullmatch(checkout)
            or proofs.get("checkout_sha") != checkout or proofs.get("arret_force") is True):
        raise ValueError("a finished Night Lab session with an observed supervisor and clean exit is required")
    rows = strict_json(_read(root, "MISSIONS.json"))
    ids = {m["id"] for m in missions}
    if not isinstance(rows, list) or len(rows) != len(ids) or any(
        not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in rows
    ):
        raise ValueError("invalid mission report")
    reports = {row["id"]: row for row in rows}
    if (reports.keys() != ids or not isinstance(status.get("missions"), dict)
            or status["missions"].keys() != ids or not isinstance(proofs.get("preuves_missions"), dict)
            or proofs["preuves_missions"].keys() != ids):
        raise ValueError("mission reports do not match the pinned registry")
    return Session(root, pin, model_ids.pop(), checkout, missions, reports, status, proofs, snapshot)


def _case_key(mission):
    contract = {k: v for k, v in mission.items() if k not in {"id", "model", "port", "dependencies"}}
    contract["max_attempts"] = mission.get("max_attempts", 1)
    return fingerprint(contract)


def _paired_cases(baseline, candidate):
    key_by_id = [{m["id"]: _case_key(m) for m in missions} for missions in (baseline, candidate)]
    if key_by_id[0].keys() & key_by_id[1].keys():
        raise ValueError("comparison requires disjoint mission IDs")
    paired = [{_case_key(m): m for m in missions} for missions in (baseline, candidate)]
    if any(len(pairs) != len(ids) for pairs, ids in zip(paired, key_by_id)) or paired[0].keys() != paired[1].keys():
        raise ValueError("sessions must run the same pinned cases with identical tests and scope")
    for key, mission in paired[0].items():
        if {key_by_id[0][d] for d in mission["dependencies"]} != {
            key_by_id[1][d] for d in paired[1][key]["dependencies"]
        }:
            raise ValueError("sessions have different dependency graphs for the same pinned cases")
    return paired


def _worker_receipt(state, mission, attempt, verification):
    mid = mission["id"]
    name = mid if mission.get("max_attempts", 1) == 1 else f"{mid}.attempt-{attempt}"
    relative = f"{name}.worker.json"
    path = state / relative
    if not path.exists() or (path.is_file() and path.stat().st_size == 0):
        if verification is not None:
            raise ValueError(f"{mid}: missing worker receipt for verifier evidence")
        return None, None
    receipt = _object(_read(state, relative), relative)
    if receipt.get("status") == "BLOCKED" and verification is None:
        if "model" in receipt and receipt["model"] != mission["model"]:
            raise ValueError(f"{mid}: worker receipt model differs from the pinned model")
        return receipt, None
    artifact = receipt.get("artifact")
    if (receipt.get("model") != mission["model"] or receipt.get("provider") != local_codegen.PROVIDER
            or receipt.get("specialist_id") != mission["specialist"] or not isinstance(artifact, str)
            or not artifact.strip() or len(artifact.encode("utf-8")) > 16_000
            or receipt.get("sha256") != _sha(artifact)):
        raise ValueError(f"{mid}: invalid worker receipt model, specialist, provider or artifact digest")
    return receipt, artifact


def _verification(mission, verification, artifact, source, state, *, accepted):
    mid = mission["id"]
    if not isinstance(verification, dict) or not isinstance(artifact, str):
        raise ValueError(f"{mid}: missing verifier evidence or bound worker output")
    if (verification.get("verifier") != local_codegen.VERIFIER
            or verification.get("artifact_sha256") != _sha(artifact)
            or verification.get("model", mission["model"]) != mission["model"]
            or verification.get("test_sha256") != _sha(mission["test"])
            or any(verification.get(k) != mission[k] for k in ("base_sha", "path", "function", "sandbox_image"))):
        raise ValueError(f"{mid}: verifier evidence does not match pinned source, test or receipt")
    raw_checks = verification.get("checks")
    if not isinstance(raw_checks, list) or any(
        not isinstance(check, dict) or not isinstance(check.get("name"), str)
        or type(check.get("ok")) is not bool for check in raw_checks
    ):
        raise ValueError(f"{mid}: malformed Docker checks")
    checks = {check["name"]: check for check in raw_checks}
    if (len(checks) != len(raw_checks) or checks.keys() - _REQUIRED_CHECKS
            or checks.get("bounded-model-receipt", {}).get("ok") is not True
            or verification.get("ok") is not accepted):
        raise ValueError(f"{mid}: inconsistent Docker verdict")
    if not accepted:
        baseline, candidate = checks.get("baseline-fails", {}), checks.get("candidate-passes", {})
        return (checks.get("approved-function-diff", {}).get("ok") is False
                or (checks.get("approved-function-diff", {}).get("ok") is True
                    and baseline.get("ok") is True and type(baseline.get("exit_code")) is int
                    and baseline["exit_code"] == 1 and candidate.get("ok") is False
                    and type(candidate.get("exit_code")) is int and candidate["exit_code"] == 1))
    if (checks.keys() != _REQUIRED_CHECKS or not all(check["ok"] for check in checks.values())
            or any(type(checks[name].get("exit_code")) is not int or checks[name]["exit_code"] != expected
                   for name, expected in (("baseline-fails", 1), ("candidate-passes", 0)))):
        raise ValueError(f"{mid}: successful verdict lacks red base / green candidate Docker proof")
    output = Path("verified-code") / mid
    candidate = _read(state, output / mission["path"], limit=120_000)
    diff = _read(state, output / "change.diff", limit=256_000)
    if (verification.get("base_file_sha256") != _sha(source)
            or verification.get("candidate_sha256") != _sha(candidate)
            or verification.get("diff_sha256") != _sha(diff)
            or local_codegen.replace_function(source, mission["function"], artifact).encode("utf-8") != candidate):
        raise ValueError(f"{mid}: accepted source, candidate or diff has changed")
    return True


def _samples(record):
    before = _metric(record.get("host_memory_before_mib"), "host memory")
    after = _metric(record.get("host_memory_after_mib"), "host memory")
    return {"before": before, "after": after} if before is not None or after is not None else None


def _observe(session, task, source):
    mid = task["id"]
    state = session.root / "code-state"
    report = session.reports[mid]
    checkpoint, claim = _checkpoint_and_claim(state, mid)
    if (checkpoint.get("status") != report.get("status")
            or checkpoint.get("status") != session.status["missions"][mid]
            or any(report.get(k) != task[k] for k in ("path", "function", "dependencies"))
            or report.get("checkpoint") != {k: v for k, v in checkpoint.items() if k != "result"}
            or session.proofs["preuves_missions"][mid] != checkpoint.get("verification")):
        raise ValueError(f"{mid}: inconsistent mission campaign report")
    return _observe_checkpoint(state, task, source, checkpoint, claim)


def _checkpoint_and_claim(state, mid):
    checkpoint = _object(_read(state, f"ledger/kilo-local/{mid}.json"), "mission checkpoint")
    claim = _object(_read(state, f"ledger/kilo-claims/{mid}.json"), "mission claim")
    return checkpoint, claim


def _observe_checkpoint(state, task, source, checkpoint, claim):
    mid = task["id"]
    end, start = checkpoint.get("at"), claim.get("at")
    terminal = checkpoint.get("status")
    if (not isinstance(terminal, str) or terminal not in _TERMINAL
            or checkpoint.get("id") != mid or checkpoint.get("project") != task["project"]
            or claim.get("project") != task["project"]
            or checkpoint.get("contract_sha256") != fingerprint(task) or claim.get("contract_sha256") != fingerprint(task)
            or type(start) not in (int, float) or type(end) not in (int, float)
            or not 0 < start <= end or not 0 <= end - start <= 1_000_000):
        raise ValueError(f"{mid}: inconsistent or non-terminal mission checkpoint/claim")
    maximum = task.get("max_attempts", 1)
    history = checkpoint.get("attempt_history", [])
    attempt = checkpoint.get("attempt", 1 if maximum == 1 else 0)
    success = terminal == "ACCEPTED"
    if (type(attempt) is not int or not 0 <= attempt <= maximum or not isinstance(history, list)
            or not max(0, attempt - 1) <= len(history) <= attempt
            or any(not isinstance(row, dict) or type(row.get("number")) is not int or row["number"] != i
                   for i, row in enumerate(history, 1))
            or (success or terminal == "REJECTED") and (attempt == 0 or len(history) != attempt - 1)):
        raise ValueError(f"{mid}: inconsistent attempt count or history")
    observed = []
    for number in range(1, attempt + 1):
        final = number == attempt
        previous = history[number - 1] if number <= len(history) else {}
        verification = checkpoint.get("verification") if final else previous.get("verification")
        if final and previous and previous.get("verification") != verification:
            raise ValueError(f"{mid}: final attempt and history disagree")
        receipt, artifact = _worker_receipt(state, task, number, verification)
        if final and checkpoint.get("result") is not None and receipt != checkpoint["result"]:
            raise ValueError(f"{mid}: worker receipt differs from the terminal checkpoint")
        passed = final and success
        attributed = False
        if verification is not None:
            attributed = _verification(task, verification, artifact, source, state, accepted=passed)
        if final and terminal in {"ACCEPTED", "REJECTED"}:
            if verification is None or receipt is None:
                raise ValueError(f"{mid}: terminal verdict lacks independent evidence")
            expected = verify_mission(
                conversation_finished=True, roles={task["specialist"]: {"reported": True}},
                acceptance_checks=[{"id": "independent-code-contract",
                    "command": "isolated Docker baseline and candidate", "exit_code": 0 if passed else 1,
                    "reproducible": True, "output_digest": fingerprint(verification)}],
            )
            if checkpoint.get("verdict") != expected:
                raise ValueError(f"{mid}: terminal verdict differs from independent evidence")
        receipt = receipt or {}
        verification = verification or {}
        if any(key in verification and verification[key] != receipt.get(key)
               for key in ("generation_seconds", "host_memory_before_mib", "host_memory_after_mib")):
            raise ValueError(f"{mid}: verifier reference to generation measurement differs from the worker receipt")
        observed.append({
            "attempt": number, "accepted": passed,
            "attributed_model_outcome": attributed and (not final or terminal != "AWAITING_HUMAN"),
            "reason": checkpoint.get("reason") if final else previous.get("reason"),
            "failed_checks": [check["name"] for check in verification.get("checks", []) if not check["ok"]],
            "generation_seconds": _metric(receipt.get("generation_seconds"), "generation duration"),
            "verification_seconds": _metric(verification.get("verification_seconds"), "verification duration"),
            "generation_available_host_memory_mib": _samples(receipt),
        })
    return {
        "mission_id": mid, "status": terminal, "accepted": success, "reason": checkpoint.get("reason"),
        "observed_at": end, "claim_to_terminal_seconds": end - start, "attempts": observed,
    }


def _total(values):
    return sum(values) if values and all(v is not None for v in values) else None


def _summary(session, observations):
    first = sum(row["accepted"] and len(row["attempts"]) == 1 for row in observations)
    second = sum(row["accepted"] and len(row["attempts"]) == 2 for row in observations)
    attempts = [attempt for row in observations for attempt in row["attempts"]]
    second_started = sum(len(row["attempts"]) == 2 for row in observations)
    generation = _total([attempt["generation_seconds"] for attempt in attempts])
    verification = _total([attempt["verification_seconds"] for attempt in attempts])
    return {
        "model": session.model, "registry_sha256": session.pin, "checkout_sha": session.checkout,
        "first_attempt_successes": first, "second_attempt_successes": second,
        "first_attempt_success_rate": first / len(observations),
        "second_attempts": second_started, "second_attempt_success_rate": second / second_started if second_started else None,
        "failures": len(observations) - first - second,
        "claim_to_terminal_seconds": sum(row["claim_to_terminal_seconds"] for row in observations),
        "generation_seconds": generation, "verification_seconds": verification,
        "measured_work_seconds": _total([generation, verification]),
        "host_memory_peak_mib": None,
    }


def _confirm_session(session, rows):
    complete = all(row["accepted"] for row in rows)
    expected = ("COMPLETE", 0) if complete else ("BLOCKED", 2)
    if (session.status["phase"], session.status["worker_exit"]) != expected:
        raise ValueError("campaign exit does not match the observed mission outcomes")
    if _read(session.root, "status.json") != session.snapshot:
        raise ValueError("campaign status changed during verification")


def read_calibration(root, pin):
    """Read reusable model measurements from a pinned, finished Night Lab."""
    session = _load_session(Path(root).resolve(strict=True), pin)
    specs = [spec for spec in catalog.MODEL_CATALOG if session.model in spec.served_ids
             and spec.provider in {"ollama", "llama.cpp"}]
    if len(specs) != 1:
        raise ValueError("calibration model is not in the approved local catalogue")
    model = specs[0].id
    observations, samples = [], []
    for task in session.missions:
        binding = {"id": model, "model": task["model"], "port": task["port"]}
        local_model_routing.validate_candidates([binding])
        source = local_codegen._source(task)
        row = _observe(session, task, source)
        observations.append(row)
        attempts = row["attempts"]
        if not attempts or not attempts[-1]["attributed_model_outcome"]:
            continue
        function = local_codegen._function_source(source, local_codegen._function(source, task["function"]))
        profile = local_model_routing._task_profile(task, function)
        difficulty, _ = router.classify_difficulty(profile)
        samples.append({
            "at": row["observed_at"], "mission": task["id"], "project": task["project"],
            "base_sha": task["base_sha"], "scope": (task["path"], task["function"]),
            "binding": binding, "difficulty": difficulty, "accepted": row["accepted"],
            "seconds": attempts[-1]["generation_seconds"], "pin": pin,
        })
    _confirm_session(session, observations)
    return samples


def _check_holdout(missions, sources):
    held_out_scopes = {(task["path"], task["function"]) for task in missions}
    held_out_tests = {_sha(task["test"]) for task in missions}
    pins = set()
    for path, pin in sources:
        path = Path(path).resolve(strict=True)
        raw = _read(path.parent, path.name, limit=512_000)
        if not _SHA.fullmatch(pin) or _sha(raw) != pin or pin in pins:
            raise ValueError("Learning registry pin is invalid, changed or duplicated")
        registry = _object(raw, "learning registry")
        learning = registry.get("missions")
        if (not isinstance(learning, list) or not 1 <= len(learning) <= 20
                or any(not isinstance(task, dict) or task.get("owner") != "local"
                       for task in learning)):
            raise ValueError("Learning registry requires approved local code missions")
        approved = registry.get("approvals")
        if approved != seal(learning) or len(approved) != len(learning):
            raise ValueError("Learning registry approval set is invalid")
        for task in learning:
            validate_contract(task, approved)
            if ((task["path"], task["function"]) in held_out_scopes
                    or _sha(task["test"]) in held_out_tests):
                raise ValueError("held-out scopes overlap with learning functions or tests")
        pins.add(pin)
    return {"kind": "held-out", "excluded_registry_sha256": sorted(pins)}


def _paired_verdict(cases, baseline_model, candidate_model):
    outcomes = []
    for case in cases:
        for label, model in (("baseline", baseline_model), ("candidate", candidate_model)):
            row = case[label]
            outcomes.append(Outcome(case["case_sha256"], model, row["accepted"],
                                    seconds=row["claim_to_terminal_seconds"]))
    data = compare(outcomes, baseline_id=baseline_model, candidate_id=candidate_model).to_dict()
    for metrics in data["paired_metrics"].values():
        # Outcome currently requires an integer for tokens. Unobserved is not zero.
        metrics["tokens"] = None
    if any(not row["attempts"] or not all(attempt["attributed_model_outcome"] for attempt in row["attempts"])
           for case in cases for row in (case["baseline"], case["candidate"])):
        data["verdict"] = INCONCLUSIVE
        data["reasons"] = ["one or more attempts lack attributable, independent model evidence"]
    return data


def compare_sessions(baseline_path, baseline_pin, candidate_path, candidate_pin, *, learning_sources=()):
    baseline_root, candidate_root = (Path(p).resolve(strict=True) for p in (baseline_path, candidate_path))
    if baseline_root.is_relative_to(candidate_root) or candidate_root.is_relative_to(baseline_root):
        raise ValueError("comparison requires two separate, non-nested session directories")
    baseline = _load_session(baseline_root, baseline_pin)
    candidate = _load_session(candidate_root, candidate_pin)
    if baseline.model == candidate.model or baseline.checkout != candidate.checkout:
        raise ValueError("comparison requires distinct fixed models and the same checkout commit")
    left, right = _paired_cases(baseline.missions, candidate.missions)
    cohort = (_check_holdout(baseline.missions, learning_sources) if learning_sources
              else {"kind": "paired", "excluded_registry_sha256": []})
    observations = [[], []]
    cases = []
    for key, before in left.items():
        after = right[key]
        source = local_codegen._source(before)
        case = {"case_sha256": key, "path": before["path"], "function": before["function"],
                "base_sha": before["base_sha"], "test_sha256": _sha(before["test"])}
        for index, (session, task, label) in enumerate(
            ((baseline, before, "baseline"), (candidate, after, "candidate"))
        ):
            row = _observe(session, task, source)
            case[label] = row
            observations[index].append(row)
        cases.append(case)
    for session, rows in zip((baseline, candidate), observations):
        _confirm_session(session, rows)
    data = _paired_verdict(cases, baseline.model, candidate.model)
    return {
        "cohort": cohort, "comparison": data, "cases": cases,
        "baseline": _summary(baseline, observations[0]), "candidate": _summary(candidate, observations[1]),
        "measurement_notes": [
            "Paired seconds are claim-to-terminal elapsed time, including verification and any interruption.",
            "Generation and verification totals are null unless every included attempt measured them.",
            "Memory readings are available host RAM before and after a step, not model allocation or peak.",
            "Model identity is the pinned label supported by local worker evidence.",
        ],
    }


def compare_cohorts(pairs, *, learning_sources=()):
    """Combine separate bounded sessions without treating repeated functions as new cases."""
    if not 1 <= len(pairs) <= 4:
        raise ValueError("evaluation requires one to four session pairs")
    reports = [compare_sessions(*pair, learning_sources=learning_sources) for pair in pairs]
    if len(reports) == 1:
        return reports[0]
    identities = {(row["baseline"]["model"], row["candidate"]["model"], row["baseline"]["checkout_sha"])
                  for row in reports}
    if len(identities) != 1:
        raise ValueError("evaluation pairs must use the same two models and checkout commit")
    cases = [case for report in reports for case in report["cases"]]
    scopes = {(case["path"], case["function"]) for case in cases}
    tests = {case["test_sha256"] for case in cases}
    if len(scopes) != len(cases) or len(tests) != len(cases):
        raise ValueError("evaluation pairs reused a function or test")
    baseline, candidate, _ = identities.pop()
    return {
        "cohort": reports[0]["cohort"], "comparison": _paired_verdict(cases, baseline, candidate),
        "cases": cases,
        "pairs": [{key: row[key] for key in ("baseline", "candidate")} for row in reports],
        "measurement_notes": reports[0]["measurement_notes"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for side in ("baseline", "candidate"):
        parser.add_argument(f"--{side}", type=Path, required=True)
        parser.add_argument(f"--{side}-sha256", required=True)
    parser.add_argument("--learning-source", metavar=("REGISTRY", "SHA256"), nargs=2, action="append",
                        help="exclude the functions and tests in a pinned registry; repeat for every learning cohort")
    parser.add_argument("--pair", nargs=4, action="append",
                        metavar=("BASELINE_DIR", "BASELINE_SHA256", "CANDIDATE_DIR", "CANDIDATE_SHA256"),
                        help="add a distinct pair of approved, independently tested sessions")
    parser.add_argument("--output", type=Path, help="write a new local evaluation report")
    args = parser.parse_args(argv)
    try:
        pairs = [(args.baseline, args.baseline_sha256, args.candidate, args.candidate_sha256),
                 *(args.pair or ())]
        roots = [Path(pair[index]).resolve() for pair in pairs for index in (0, 2)]
        if args.output and any(args.output.resolve().is_relative_to(root) for root in roots):
            raise ValueError("write the evaluation report outside the evidence directories")
        data = compare_cohorts(pairs, learning_sources=args.learning_source or ())
        if args.output:
            _write_new_private(args.output, {
                "schema_version": 1, "kind": "tel99-paired-evaluation", "report": data,
            })
    except (Blocked, OSError, ValueError, KeyError, TypeError, SyntaxError, RecursionError) as exc:
        parser.exit(2, f"Comparison refused: {exc}\n")
    print(json.dumps(data, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
