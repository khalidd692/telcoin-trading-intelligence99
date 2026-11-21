"""Check portable direct-argv input files from a foreign project directory."""

import argparse
import codecs
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
BASE_REVISION = "011a23f0fd75ffa11e97818ca4935486ccbe36e1"
BASE_SHA256 = "0829597264d4d74988c6e392384e7229b3a83711c45d17489212174b4f50a4c5"
COMPARISON_SHA256 = "5ee7f8222e039670d1b37fe07c46da4cd5a4aa2e2442b5e0304b1ba1c2e72550"
LIMIT = 65536

CONTRACT = {
    "budget": 5, "obligations": ["mise en page", "égalité des totaux"], "mandatory": ["visa"],
    "checks": [
        {"id": "épreuve PDF", "cost": 3, "covers": ["mise en page"]},
        {"id": "relecture", "cost": 1, "covers": ["égalité des totaux"]},
        {"id": "visa", "cost": 1, "covers": []},
        {"id": "banc complet", "cost": 5, "covers": ["mise en page", "égalité des totaux"]},
    ],
}
RESUME = {
    "contract": dict(CONTRACT, budget=2),
    "passed": ["épreuve PDF"],
    "unavailable": ["banc complet"],
}
PLANNED = {
    "status": "planned", "cost": 5, "all_relevant_cost": 10,
    "checks": ["relecture", "visa", "épreuve PDF"],
}
REPLANNED = {
    "status": "planned", "cost": 2, "all_relevant_cost": 2,
    "checks": ["relecture", "visa"], "reused": ["épreuve PDF"],
}


def pinned_file(name, digest):
    path = HERE / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f"Frozen dependency changed: {name}")
    return path


def fixtures(cwd, outside):
    folder = cwd / "fichiers d’entrée"
    folder.mkdir()
    plan = folder / "révision d’étape.json"
    resume = outside / "état des preuves.json"
    boundary = folder / "frontière 64 Kio.json"
    big = folder / "plus de 64 Kio.json"
    broken = folder / "document incomplet.json"
    bad_encoding = folder / "document illisible.json"
    payload = json.dumps(CONTRACT, ensure_ascii=False).encode("utf-8")
    at_limit = payload.ljust(LIMIT, b" ")
    above_limit = at_limit + b" "
    malformed = b'{"contract":'
    plan.write_bytes(payload)
    resume.write_bytes(codecs.BOM_UTF8 + json.dumps(RESUME, ensure_ascii=False).encode("utf-8"))
    boundary.write_bytes(at_limit)
    big.write_bytes(above_limit)
    broken.write_bytes(malformed)
    bad_encoding.write_bytes(b'{"budget": 1, "bad": "\x80"}')

    def file(path, *, relative=True, prefix=(), suffix=()):
        location = str(path.relative_to(cwd) if relative else path)
        return [*prefix, "--input", location, *suffix]

    # Feed unrelated stdin in file mode to verify that the named file is authoritative.
    ignored_stdin = b'{"not the requested file": true}'
    return {
        "file-basic-relative-utf8": (file(plan), ignored_stdin, PLANNED),
        "file-resume-absolute-utf8-bom": (
            file(resume, relative=False, suffix=("--replan",)), ignored_stdin, REPLANNED),
        "file-exactly-64-kib": (file(boundary), ignored_stdin, PLANNED),
        "file-over-64-kib": (file(big), ignored_stdin, "64 KiB"),
        "file-missing": (file(folder / "absent.json"), ignored_stdin, ""),
        "file-directory": (file(folder), ignored_stdin, ""),
        "file-malformed-replan": (file(broken, prefix=("--replan",)), ignored_stdin, ""),
        "file-invalid-utf8": (file(bad_encoding), ignored_stdin, ""),
        "stdin-previous-plan": ([], payload, PLANNED),
        "stdin-previous-replan": (["--replan"], resume.read_bytes(), REPLANNED),
        "stdin-exactly-64-kib": ([], at_limit, PLANNED),
        "stdin-over-64-kib": ([], above_limit, "64 KiB"),
        "stdin-malformed": ([], malformed, ""),
    }


def run_case(script, cwd, case):
    arguments, stdin, expected = case
    try:
        result = subprocess.run(
            [sys.executable, "-IB", str(script), *arguments],
            cwd=cwd, input=stdin, capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, {"error": type(exc).__name__}
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    try:
        actual = json.loads(stdout)
    except ValueError:
        actual = stdout
    if isinstance(expected, dict):
        success = result.returncode == 0 and not stderr and actual == expected
    else:
        reason = actual.get("reason") if isinstance(actual, dict) else None
        success = (result.returncode == 2 and not stderr and isinstance(actual, dict)
                   and actual.get("status") == "invalid" and isinstance(reason, str)
                   and bool(reason.strip()) and expected in reason)
    return success, {"exit_code": result.returncode, "result": actual, "stderr": stderr}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--candidate", type=Path)
    choice.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--candidate-revision")
    args = parser.parse_args()
    if args.candidate and not args.candidate_revision:
        parser.error("--candidate requires --candidate-revision")
    base = pinned_file("base_plan_checks.py", BASE_SHA256)
    comparator = runpy.run_path(str(pinned_file("base_improvement.py", COMPARISON_SHA256)))
    scripts = {"baseline": base}
    if args.candidate:
        scripts["candidate"] = args.candidate.resolve()
    outcomes = []
    findings = {}
    scores = {arm: {"file": 0, "stdin": 0} for arm in scripts}

    with tempfile.TemporaryDirectory() as temporary:
        outside = Path(temporary)
        cwd = outside / "autre projet"
        cwd.mkdir()
        cases = fixtures(cwd, outside)
        for name, case in cases.items():
            channel = name.partition("-")[0]
            findings[name] = {}
            for arm, script in scripts.items():
                success, details = run_case(script, cwd, case)
                findings[name][arm] = {"success": success, **details}
                scores[arm][channel] += int(success)
                outcomes.append(comparator["Outcome"](name, arm, success))
    report = {
        "baseline_revision": BASE_REVISION,
        "candidate_revision": args.candidate_revision,
        "platform": sys.platform,
        "method": "Native subprocess argv without a shell. PR #133 retains stdin via native transport.",
        "scores": scores,
        "file_cases": sum(name.startswith("file-") for name in cases),
        "stdin_cases": sum(name.startswith("stdin-") for name in cases),
        "findings": findings,
    }
    if args.candidate:
        report["candidate_planner_sha256"] = hashlib.sha256(scripts["candidate"].read_bytes()).hexdigest()
        verdict = comparator["compare"](outcomes, baseline_id="baseline", candidate_id="candidate")
        report["comparison"] = verdict.to_dict()
    # Keep the case evidence independent of the random working directory.
    print(json.dumps(report, indent=2, ensure_ascii=True).replace(str(outside), "<fixture>"))
    return int(bool(args.candidate) and (verdict.verdict != "keep" or sum(scores["candidate"].values()) != len(cases)))


if __name__ == "__main__":
    raise SystemExit(main())
