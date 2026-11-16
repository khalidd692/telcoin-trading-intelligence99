#!/usr/bin/env python3
"""CLI for the TEL99 agent intelligence layer.

Reusable interface for any project: it wires the model router, the shared
memory and the controlled improvement loop behind a single command. It is
stdlib-only and offline by default (no model is actually called), so it can run
in CI and on a machine with no LLM available.

Commands:
    route      classify a task and choose a model (with a decision journal)
    remember   record a piece of knowledge in a project's memory
    recall     search a project's memory for a query
    improve    compare a candidate model against a baseline and record the verdict
    demo       run the end-to-end demonstration used as evidence

Examples:
    python -m scripts.agents.intelligence.cli route --kind code --files 6
    python -m scripts.agents.intelligence.cli remember --project tel99 \
        --kind fix --title "guard git -C" --body "..." --tag guard
    python -m scripts.agents.intelligence.cli recall --project tel99 --query "guard"
    python -m scripts.agents.intelligence.cli improve --baseline a --candidate b \
        --outcomes outcomes.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
SCRIPTS = HERE.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from intelligence import catalog, improvement, memory, router  # noqa: E402

DEFAULT_MEMORY_ROOT = HERE.parents[3] / "memory"
DEFAULT_MEASURED = HERE.parents[3] / "memory" / "measured_quality.json"


def _store(args) -> memory.MemoryStore:
    root = pathlib.Path(args.memory_root) if args.memory_root else DEFAULT_MEMORY_ROOT
    return memory.MemoryStore(root)


def cmd_route(args) -> int:
    task = router.TaskProfile(
        kind=args.kind,
        description=args.description or "",
        touches_files=args.files,
        needs_tools=not args.no_tools,
        confidential=args.confidential,
        estimated_tokens=args.tokens,
    )
    measured = {}
    if DEFAULT_MEASURED.is_file():
        measured = router.load_measured_quality(str(DEFAULT_MEASURED))
    journal: list[dict] = []
    decision = router.route(
        task,
        quota_remaining=args.quota,
        dry_run=args.dry_run,
        measured_quality=measured,
        journal=journal,
    )
    print(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False))
    if not decision.ok:
        print("router: no eligible model (see 'rejected' above)", file=sys.stderr)
        return 3
    return 0


def cmd_remember(args) -> int:
    store = _store(args)
    entry = memory.Entry(
        id=args.id or memory.slug(f"{args.kind}-{args.title}"),
        project=args.project,
        kind=args.kind,
        title=args.title,
        body=args.body,
        tags=tuple(args.tag or ()),
        source=args.source or "cli",
        commit=args.commit or "",
        author=args.author or "agent",
        confidence=args.confidence,
        verified=args.verified,
        verified_by=args.author if args.verified else "",
    )
    store.record(entry)
    print(f"recorded {entry.id} v{entry.version} in project {entry.project}")
    return 0


def cmd_recall(args) -> int:
    store = _store(args)
    results = store.search(
        args.project, args.query, limit=args.limit,
        kinds=tuple(args.kind) if args.kind else None,
    )
    if not results:
        print(f"no memory found for {args.query!r} in {args.project}")
        return 1
    for entry in results:
        flag = "verified" if entry.verified else "unverified"
        print(f"- [{entry.kind}/{flag}] {entry.title}")
        print(f"    {entry.body[:160]}")
    return 0


def cmd_improve(args) -> int:
    raw = json.loads(pathlib.Path(args.outcomes).read_text(encoding="utf-8"))
    outcomes = [improvement.Outcome(**row) for row in raw]
    comparison = improvement.compare(
        outcomes, baseline_id=args.baseline, candidate_id=args.candidate,
        min_delta=args.min_delta,
    )
    print(json.dumps(comparison.to_dict(), indent=2, ensure_ascii=False))
    if args.record:
        store = _store(args)
        entry_id = improvement.apply_verdict(
            comparison, store, args.project or "common"
        )
        print(f"recorded verdict as {entry_id}")
    if not args.measured_out:
        pass
    else:
        improvement.write_measured_quality(args.measured_out, outcomes)
        print(f"wrote measured quality to {args.measured_out}")
    return 0 if comparison.verdict != improvement.REJECT else 1


def cmd_demo(args) -> int:
    from intelligence import demo
    return demo.run(dry_run=args.dry_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--memory-root", default="",
                        help="memory root directory (default: <repo>/memory)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("route", help="choose a model for a task")
    p.add_argument("--kind", default="general",
                   choices=["code", "analysis", "review", "general"])
    p.add_argument("--description", default="")
    p.add_argument("--files", type=int, default=0)
    p.add_argument("--tokens", type=int, default=0)
    p.add_argument("--no-tools", action="store_true")
    p.add_argument("--confidential", action="store_true")
    p.add_argument("--quota", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("remember", help="record knowledge")
    p.add_argument("--project", required=True)
    p.add_argument("--kind", required=True, choices=list(memory.KINDS))
    p.add_argument("--title", required=True)
    p.add_argument("--body", default="")
    p.add_argument("--id", default="")
    p.add_argument("--tag", action="append")
    p.add_argument("--source", default="")
    p.add_argument("--commit", default="")
    p.add_argument("--author", default="")
    p.add_argument("--confidence", type=float, default=0.5)
    p.add_argument("--verified", action="store_true")
    p.set_defaults(func=cmd_remember)

    p = sub.add_parser("recall", help="search knowledge")
    p.add_argument("--project", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--kind", action="append", choices=list(memory.KINDS))
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("improve", help="compare a candidate against a baseline")
    p.add_argument("--baseline", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--outcomes", required=True)
    p.add_argument("--min-delta", type=float, default=0.0)
    p.add_argument("--record", action="store_true")
    p.add_argument("--project", default="")
    p.add_argument("--measured-out", default="")
    p.set_defaults(func=cmd_improve)

    p = sub.add_parser("demo", help="run the end-to-end demonstration")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
