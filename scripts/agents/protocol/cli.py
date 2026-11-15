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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
