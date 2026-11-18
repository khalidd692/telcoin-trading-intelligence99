#!/usr/bin/env python3
"""Native CLI for the TEL99 agent mission runner.

This is the *owner-facing* entry point: a single command of our own project
that runs a bounded mission, without opening Hermes Desktop, Kilo Agent Manager
or OpenHands Cloud.

Commands:
    run      run one bounded mission (fail-closed quota, deterministic verdict)
    recall   search the shared memory for a past mission/learning
    demo     run the offline, deterministic demonstration (evidence)

Examples:
    # offline, deterministic, no quota, no network -- the evidence command
    python -m scripts.agents.native.cli demo

    # a real run needs the quota and the provider env (never committed)
    TEL99_NATIVE_MODEL=openhands/deepseek-v4.1-flash \\
    TEL99_NATIVE_BASE_URL=http://localhost:1234/v1 \\
    python -m scripts.agents.native.cli run --mission-id demo-1 --mission "..."

Exit codes: 0 success, 2 refused precondition (fail-closed), 3 mission FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve()
_AGENTS_DIR = _HERE.parents[1]
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

from native import mission as mission_mod  # noqa: E402
from native import provider as provider_mod  # noqa: E402
from native import sandbox, task_app  # noqa: E402

REPO_ROOT = _HERE.parents[3]
DEFAULT_STATE = REPO_ROOT / ".tel99-native-state"
DEFAULT_MEMORY = REPO_ROOT / "memory"


def read_quota() -> int | None:
    """Read the free-conversation quota. ``None`` means unknown (fail-closed)."""
    import urllib.error
    import urllib.request

    key = os.environ.get("OPENHANDS_API_KEY", "")
    base = os.environ.get("OPENHANDS_CLOUD_API_URL",
                          "https://app.all-hands.dev").rstrip("/")
    if not key:
        return None
    req = urllib.request.Request(f"{base}/api/quota/status")
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001 - an unreadable quota is unknown, not zero
        return None
    remaining = body.get("remaining") if isinstance(body, dict) else None
    return int(remaining) if isinstance(remaining, int) else None


def _engine(args, provider) -> mission_mod.MissionEngine:
    store_root = pathlib.Path(args.state) if args.state else DEFAULT_STATE
    memory_root = pathlib.Path(args.memory) if args.memory else DEFAULT_MEMORY
    quota = args.quota
    if (quota is None and args.command == "run" and not args.dry_run
            and not getattr(provider, "requires_explicit_quota", False)):
        quota = read_quota()
    return mission_mod.MissionEngine(
        provider=provider,
        store_root=store_root,
        workspace_root=store_root / "artifacts",
        memory_root=memory_root,
        quota_remaining=quota,
        min_quota=args.min_quota,
        dry_run=args.dry_run,
    )


def cmd_run(args) -> int:
    artifacts = args.artifact or []
    prompt = args.mission
    sandbox_check = None
    max_repairs = args.max_repairs
    try:
        if args.profile == "tasks":
            if artifacts or args.sandbox_script is not None or args.expected_stdout is not None:
                raise mission_mod.MissionError("the task profile supplies its own artifacts and checks")
            artifacts = list(task_app.ARTIFACTS)
            prompt += "\n\n" + task_app.CONTRACT
            sandbox_check = task_app.TaskAppCheck(args.sandbox_image)
            if args.max_repairs is None:
                max_repairs = 2
        else:
            sandbox_args = (args.sandbox_image, args.sandbox_script, args.expected_stdout)
            if any(value is not None for value in sandbox_args):
                if None in sandbox_args or args.sandbox_script not in artifacts:
                    raise mission_mod.MissionError(
                        "sandbox requires a pinned image, a declared script artifact and expected stdout")
                sandbox_check = sandbox.ScriptCheck(*sandbox_args)
    except mission_mod.MissionError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    python_artifacts = [name for name in artifacts if name.endswith(".py")]
    checks = ([mission_mod.Check(name="syntax", command=[sys.executable, "-I", "-m",
                                                         "py_compile", *python_artifacts])]
              if python_artifacts else [])
    if sandbox_check:
        checks.append(sandbox_check)
    if args.profile == "tasks" and not args.dry_run:
        try:
            sandbox.require_local_image(args.sandbox_image)
        except mission_mod.MissionError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
    if args.dry_run:
        # A dry run plans and routes; it never calls a model, so it needs no
        # provider credentials. It spends nothing and writes nothing.
        provider = provider_mod.ScriptedProvider([], name="dry-run")
    else:
        try:
            provider = provider_mod.provider_from_env(synthetic_data=args.synthetic_data)
        except provider_mod.ProviderConfigError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
    engine = _engine(args, provider)
    spec = mission_mod.MissionSpec(
        mission_id=args.mission_id,
        prompt=prompt,
        project=args.project,
        max_repairs=max_repairs,
        artifacts=artifacts,
        checks=checks,
    )
    try:
        result = engine.run(spec)
    except mission_mod.MissionError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if result.reused and sandbox_check and not any(
            check.get("sandbox_fingerprint") == sandbox_check.fingerprint
            for check in result.checks):
        print("refused: cached mission did not run this sandbox check", file=sys.stderr)
        return 2
    report = result.to_dict()
    if not args.dry_run:
        report["artifact_directory"] = str(engine.artifact_directory(spec).resolve())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.dry_run:
        return 0
    return 0 if result.verdict == mission_mod.PASS else 3


def cmd_status(args) -> int:
    engine = _engine(args, provider_mod.ScriptedProvider([]))
    spec = mission_mod.MissionSpec(args.mission_id, "", project=args.project)
    try:
        record = engine.record_for(spec)
    except mission_mod.MissionError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if record is None:
        print("refused: no recorded mission", file=sys.stderr)
        return 2
    record["artifact_directory"] = str(engine.artifact_directory(spec).absolute())
    digests = record.get("artifact_digests", {})
    record["artifact_integrity"] = ("matched" if engine.artifacts_match(spec, digests)
                                    else "changed") if digests else "not_recorded"
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0


def cmd_verify_task_app(args) -> int:
    try:
        check = task_app.TaskAppCheck(args.sandbox_image)
    except mission_mod.MissionError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    result = check.verify_file(args.file)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 3


def cmd_recall(args) -> int:
    engine = _engine(args, provider_mod.ScriptedProvider([]))
    try:
        hits = engine.recall(args.query, limit=args.limit, project=args.project)
    except mission_mod.MissionError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(hits, indent=2, ensure_ascii=False))
    return 0


def cmd_memory_snapshot(args) -> int:
    store = mission_mod.memory.MemoryStore(args.memory or DEFAULT_MEMORY)
    restore = args.command == "restore-memory"
    try:
        operation = store.restore_project if restore else store.export_project
        operation(args.project, args.file)
    except FileExistsError:
        print("refused: destination already exists", file=sys.stderr)
        return 2
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"refused: memory snapshot failed ({type(exc).__name__})", file=sys.stderr)
        return 2
    print(json.dumps({"project": args.project,
                      "status": "restored" if restore else "exported"}))
    return 0


def cmd_demo(args) -> int:
    """Offline, deterministic evidence: a real Python artifact + real tests.

    No network, no LLM, no quota. The scripted provider emits a small Python
    module whose deterministic checks the kernel re-runs; a second mission shows
    the negative fixture (model claims PASS, a check fails => verdict FAIL).
    """
    root = pathlib.Path(tempfile.mkdtemp(prefix="tel99-native-demo-"))
    store, mem = root / "state", root / "memory"

    good = ("```mathutils.py\n"
            "def add(a, b):\n    return a + b\n\n"
            "def double(x):\n    return add(x, x)\n```")
    provider = provider_mod.ScriptedProvider([good], name="scripted-demo")
    engine = mission_mod.MissionEngine(
        provider=provider, store_root=store, workspace_root=store / "artifacts",
        memory_root=mem, quota_remaining=18, min_quota=12,
    )
    spec = mission_mod.MissionSpec(
        mission_id="demo-mathutils", prompt="Ecris mathutils.py avec add et double.",
        artifacts=["mathutils.py"],
        checks=[
            mission_mod.Check(name="compile", command=["python3", "-m", "py_compile",
                                                       "mathutils.py"]),
            mission_mod.Check(
                name="behaviour",
                command=["python3", "-c",
                         "import mathutils; assert mathutils.double(21) == 42; "
                         "print('ok')"],
                must_contain="ok"),
        ],
    )
    first = engine.run(spec)
    second = engine.run(spec)  # idempotent: must NOT call the provider again

    # Negative fixture: the model *claims* PASS but the behaviour is wrong, so
    # the deterministic check must still fail. The claim lives outside the
    # fenced artifact block, exactly like a real model's self-report.
    bad_artifact = ("```mathutils.py\n"
                    "def add(a, b):\n    return a + b\n\n"
                    "def double(x):\n    return x\n```")
    bad = bad_artifact + "\nVERDICT: PASS"
    provider2 = provider_mod.ScriptedProvider([bad], name="scripted-demo")
    engine2 = mission_mod.MissionEngine(
        provider=provider2, store_root=root / "state2",
        workspace_root=root / "state2" / "artifacts", memory_root=mem,
        quota_remaining=18, min_quota=12,
    )
    spec2 = mission_mod.MissionSpec(
        mission_id="demo-negative", prompt="Ecris mathutils.py (version fausse).",
        artifacts=["mathutils.py"],
        checks=[mission_mod.Check(
            name="behaviour",
            command=["python3", "-c",
                     "import mathutils; assert mathutils.double(21) == 42"],
            must_contain="")],
    )
    neg = engine2.run(spec2)

    # Cross-session recall: a brand-new store object must see the learning.
    fresh = mission_mod.memory.MemoryStore(mem)
    recalled = [e.id for e in fresh.search("tel99", "demo-mathutils")]

    report = {
        "artifact_source": good.split("\n", 1)[1].split("```")[0],
        "first": first.to_dict(),
        "second_is_reused": second.reused,
        "second_provider_calls": second.provider_calls,
        "negative_fixture_verdict": neg.verdict,
        "negative_fixture_model_claimed": "VERDICT: PASS" in bad,
        "negative_fixture_artifact": bad_artifact.split("\n", 1)[1].split("```")[0],
        "recalled_from_fresh_session": recalled,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = (first.verdict == mission_mod.PASS and second.reused
          and second.provider_calls == 0 and neg.verdict == mission_mod.FAIL
          and recalled)
    print(f"\nDEMO: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TEL99 native mission runner.")
    parser.add_argument("--state", default=None, help="state root (default .tel99-native-state)")
    parser.add_argument("--memory", default=None, help="memory root (default ./memory)")
    parser.add_argument("--quota", type=int, default=None,
                        help="override the free-conversation quota reading")
    parser.add_argument("--min-quota", type=int,
                        default=mission_mod.MIN_QUOTA_REQUIRED)
    parser.add_argument("--dry-run", action="store_true",
                        help="decide and route without calling the provider")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one bounded mission")
    run.add_argument("--mission-id", required=True)
    run.add_argument("--mission", required=True)
    run.add_argument("--artifact", action="append", default=[])
    run.add_argument("--profile", choices=("tasks",), help="built-in acceptance profile")
    run.add_argument("--max-repairs", type=int, help="bounded retries after failing checks")
    run.add_argument("--synthetic-data", action="store_true",
                     help="attest that Kilo Auto Free receives only synthetic, non-sensitive inputs")
    run.add_argument("--sandbox-image", help="locally installed Python image pinned by digest")
    run.add_argument("--sandbox-script", help="Python artifact to run in the sandbox")
    run.add_argument("--expected-stdout", help="expected output, excluding the final newline")
    run.add_argument("--project", default=mission_mod.DEFAULT_PROJECT)
    run.add_argument("--dry-run", dest="run_dry_run", action="store_true",
                     help="decide and route without calling the provider")
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="read a stored mission journal")
    status.add_argument("--mission-id", required=True)
    status.add_argument("--project", default=mission_mod.DEFAULT_PROJECT)
    status.set_defaults(func=cmd_status)

    verify = sub.add_parser("verify-task-app", help="replay task-app tests without a model")
    verify.add_argument("--file", type=pathlib.Path, required=True)
    verify.add_argument("--sandbox-image", required=True)
    verify.set_defaults(func=cmd_verify_task_app)

    recall = sub.add_parser("recall", help="search the shared memory")
    recall.add_argument("--query", required=True)
    recall.add_argument("--project", default=mission_mod.DEFAULT_PROJECT)
    recall.add_argument("--limit", type=int, default=5)
    recall.set_defaults(func=cmd_recall)

    for command, description in (
        ("export-memory", "write a private project snapshot to a new file"),
        ("restore-memory", "restore a project snapshot into an empty slot"),
    ):
        snapshot = sub.add_parser(command, help=description)
        snapshot.add_argument("--project", required=True)
        snapshot.add_argument("--file", required=True, type=pathlib.Path)
        snapshot.set_defaults(func=cmd_memory_snapshot)

    demo = sub.add_parser("demo", help="offline deterministic demonstration")
    demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    # --dry-run is accepted both globally and after `run`.
    args.dry_run = bool(getattr(args, "dry_run", False)
                        or getattr(args, "run_dry_run", False))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
