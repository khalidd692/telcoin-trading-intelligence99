#!/usr/bin/env python3
"""CLI for the TEL99 agent integration bus.

Reusable, offline entry point to run and inspect a distributed mission across
the three environments.

Commands:
    actors     show the actor registry and which transports are really connected
    capabilities  probe the real cloud/agent-server capabilities (read-only)
    mission    open a mission on the bus
    dispatch   dispatch the next step to its assigned actor
    resume     resume an interrupted mission
    status     show a mission's state, steps, errors and result
    demo       run the end-to-end demonstration (a real distributed mission)
    next-task  select the highest admissible backlog task (no human relaying)
    handoff    record a handoff event and print the next admissible task
    receive    idempotently receive a message (one action per request id)
    verify     compute the real verdict of a mission from evidence

Examples:
    python -m scripts.agents.protocol.cli actors
    python -m scripts.agents.protocol.cli capabilities
    python -m scripts.agents.protocol.cli demo
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
AGENTS_DIR = HERE.parents[1]            # scripts/agents
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from protocol import validate  # noqa: E402
from protocol.bus import Bus  # noqa: E402


def cmd_actors(args) -> int:
    bus = Bus(args.bus_root)
    for actor_id, actor in bus.actors.items():
        flag = "CONNECTED" if actor.get("connected") else "NOT CONNECTED"
        caps = ",".join(actor.get("capabilities", []))
        print(f"- {actor_id:<24} [{actor['environment']:<9}] {flag:<14} {caps}")
    print(f"\nconnected: {bus.connected_actors()}")
    print(f"storage: {bus.storage_report()}")
    return 0


def cmd_ledger(args) -> int:
    from automation import bus_bridge

    bus = Bus(args.bus_root)
    print(json.dumps(bus_bridge.ledger(bus), indent=2, ensure_ascii=False))
    return 0


def cmd_capabilities(args) -> int:
    from protocol.adapters import openhands

    probes = openhands.probe_all()
    for probe in probes:
        print(json.dumps(probe, ensure_ascii=False))
    ok = sum(1 for p in probes if p.get("reachable") or p.get("endpoint_live"))
    print(f"\n{ok}/{len(probes)} capability probe(s) live")
    return 0


def cmd_mission(args) -> int:
    bus = Bus(args.bus_root)
    steps = json.loads(args.steps) if args.steps else [
        {"id": "s1", "description": "route a model", "intent": "route a model",
         "assigned_to": args.assign or "hermes-router"},
    ]
    record = bus.open_mission(
        title=args.title, origin=bus.actors["openhands-cloud"], steps=steps,
        description=args.description,
    )
    print(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_dispatch(args) -> int:
    bus = Bus(args.bus_root)
    envelope = bus.dispatch_step(args.correlation_id)
    print(envelope.to_json())
    return 0


def cmd_resume(args) -> int:
    bus = Bus(args.bus_root)
    record = bus.resume(args.correlation_id)
    print(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_status(args) -> int:
    bus = Bus(args.bus_root)
    record = bus.load_mission(args.correlation_id)
    if record is None:
        print(f"unknown mission {args.correlation_id}", file=sys.stderr)
        return 1
    print(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_validate(args) -> int:
    problems = validate(json.loads(pathlib.Path(args.file).read_text(encoding="utf-8")))
    if problems:
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 2
    print("envelope is valid")
    return 0


def cmd_demo(args) -> int:
    from protocol import demo
    return demo.run(bus_root=args.bus_root)


def cmd_next_task(args) -> int:
    from protocol import handoff

    backlog = handoff.load_backlog(args.backlog)
    ledger = handoff.HandoffLedger()
    report = ledger.report(backlog, owner=args.owner or None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["next_task"] else 3


def cmd_handoff(args) -> int:
    from protocol import handoff

    backlog = handoff.load_backlog(args.backlog)
    ledger = handoff.HandoffLedger()
    ledger.record_handoff(task_id=args.task, owner=args.owner, status=args.status,
                          sha=args.sha, tests=args.tests, proof=args.proof,
                          next_task=args.next_task, block_reason=args.block_reason)
    nxt = ledger.next_task(backlog, owner=args.owner)
    print(json.dumps({"recorded": args.task, "status": args.status,
                      "next_task": nxt.get("id") if nxt else None}, indent=2))
    return 0


def cmd_receive(args) -> int:
    from protocol import handoff

    inbox = handoff.Inbox(args.receiver)
    message = json.loads(pathlib.Path(args.message).read_text(encoding="utf-8"))
    out = inbox.receive(message)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_verify(args) -> int:
    from protocol import handoff

    payload = json.loads(pathlib.Path(args.file).read_text(encoding="utf-8"))
    verdict = handoff.verify_mission(
        conversation_finished=bool(payload.get("conversation_finished")),
        roles=payload.get("roles", {}),
        acceptance_checks=payload.get("acceptance_checks", []),
    )
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    return 0 if verdict["validated"] else 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bus-root", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("actors", help="show the actor registry")
    p.set_defaults(func=cmd_actors)

    p = sub.add_parser("ledger", help="show the mission ledger")
    p.set_defaults(func=cmd_ledger)

    p = sub.add_parser("capabilities", help="probe real capabilities")
    p.set_defaults(func=cmd_capabilities)

    p = sub.add_parser("mission", help="open a mission")
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--steps", default="")
    p.add_argument("--assign", default="")
    p.set_defaults(func=cmd_mission)

    p = sub.add_parser("dispatch", help="dispatch the next step")
    p.add_argument("--correlation-id", required=True)
    p.set_defaults(func=cmd_dispatch)

    p = sub.add_parser("resume", help="resume a mission")
    p.add_argument("--correlation-id", required=True)
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("status", help="show a mission")
    p.add_argument("--correlation-id", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("validate", help="validate an envelope file")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("demo", help="run the end-to-end demonstration")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("next-task", help="select the highest admissible task")
    p.add_argument("--backlog", required=True)
    p.add_argument("--owner", default="")
    p.set_defaults(func=cmd_next_task)

    p = sub.add_parser("handoff", help="record a handoff and pick the next task")
    p.add_argument("--backlog", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--sha", default="")
    p.add_argument("--tests", default="")
    p.add_argument("--proof", default="")
    p.add_argument("--next-task", dest="next_task", default="")
    p.add_argument("--block-reason", dest="block_reason", default="")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("receive", help="idempotently receive a message")
    p.add_argument("--receiver", required=True)
    p.add_argument("--message", required=True)
    p.set_defaults(func=cmd_receive)

    p = sub.add_parser("verify", help="compute the real verdict of a mission")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
