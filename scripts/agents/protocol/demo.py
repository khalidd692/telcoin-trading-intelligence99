#!/usr/bin/env python3
"""End-to-end demonstration of the TEL99 agent integration bus.

It runs one real, distributed mission and proves, with artefacts on disk, that:

  1. **the protocol validates** — a mission envelope is built and passes
     :func:`protocol.validate`;
  2. **OpenHands is connected** — the local agent-server and the Cloud quota
     endpoints answer (live probes, read-only);
  3. **Hermes really executes a step** — the existing router/memory answer a
     sub-mission and the result is recorded on the bus;
  4. **a dead endpoint is refused, not faked** — a step assigned to Kilo (which
     is NOT connected) makes the bus go ``blocked`` and raise, instead of
     pretending the mission was delivered;
  5. **an interrupted mission resumes** — a mission is killed mid-way, then
     resumed at its next unfinished step;
  6. **loop control works** — a permanently failing step is retried up to the
     cap and then fails deterministically, never spinning forever;
  7. **a validated learning is recorded** — the mission outcome is written to
     the shared memory through the Hermes adapter.

Everything is real and offline except the read-only capability probes, which
touch only the local agent-server and the OpenHands Cloud status endpoints. No
order, no merge, no deployment, no paid model.
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve()
AGENTS_DIR = HERE.parents[1]
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from protocol import validate  # noqa: E402
from protocol.adapters import hermes, kilo, openhands  # noqa: E402
from protocol.bus import Bus  # noqa: E402
from protocol.envelope import Envelope  # noqa: E402


def _title(text: str) -> None:
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


def run(bus_root: str | None = None, *, probe: bool = True) -> int:
    root = pathlib.Path(bus_root) if bus_root else pathlib.Path("bus")
    bus = Bus(root)
    checks: dict[str, bool] = {}

    _title("STEP 0 — actor registry (who is really connected)")
    for actor_id, actor in bus.actors.items():
        flag = "CONNECTED" if actor["connected"] else "NOT CONNECTED"
        print(f"  {actor_id:<24} {actor['environment']:<9} {flag}")
    checks["kilo_declared_not_connected"] = not bus.is_connected("kilo-code-auto-free")

    _title("STEP 1 — build and validate a mission envelope")
    mission = Envelope.create(
        origin=openhands.actor(), kind="mission", state="queued",
        title="Distributed read-only audit", description="route then recall",
        steps=[
            {"id": "s1", "description": "route a model", "intent": "route a model",
             "assigned_to": "hermes-router"},
            {"id": "s2", "description": "recall memory", "intent": "recall memory",
             "assigned_to": "hermes-router"},
        ],
    )
    problems = validate(mission.to_dict())
    print(f"  envelope_id   : {mission.envelope_id}")
    print(f"  correlation_id: {mission.correlation_id}")
    print(f"  validation    : {'VALID' if not problems else problems}")
    checks["protocol_validates"] = not problems

    if probe:
        _title("STEP 2 — live capability probes (read-only)")
        for result in openhands.probe_all():
            print("  " + str(result))
        server = openhands.probe_agent_server()
        quota = openhands.probe_quota()
        checks["openhands_connected"] = bool(server["reachable"])
        print(f"  agent-server reachable: {server['reachable']} "
              f"(v{server.get('version')})")
        print(f"  quota remaining       : {quota.get('remaining')}")

    _title("STEP 3 — open a real mission on the bus and dispatch step 1")
    record = bus.open_mission(
        title="Distributed read-only audit",
        origin=bus.actors["openhands-cloud"],
        steps=[
            {"id": "s1", "description": "route a model", "intent": "route a model",
             "assigned_to": "hermes-router"},
            {"id": "s2", "description": "recall memory", "intent": "recall memory",
             "assigned_to": "hermes-router"},
        ],
        description="route then recall",
    )
    print(f"  mission {record.correlation_id} state={record.state}")
    envelope = bus.dispatch_step(record.correlation_id)
    print(f"  dispatched {envelope.envelope_id} -> {envelope.target.id}")

    _title("STEP 4 — Hermes executes the step (reusing the intelligence layer)")
    reply = hermes.handle(envelope, root=str(root / "memory"))
    print(f"  hermes reply state: {reply.state} | {reply.result['summary']}")
    record = bus.record_result(record.correlation_id, "s1",
                               status="success", envelope=reply)
    print(f"  mission state now: {record.state} "
          f"({len(record.completed_step_ids)}/{len(record.steps)} steps)")
    checks["hermes_executed"] = reply.state == "done"

    _title("STEP 5 — a step assigned to Kilo is REFUSED (not faked)")
    try:
        blocked = bus.open_mission(
            title="Validation by Kilo",
            origin=bus.actors["openhands-cloud"],
            steps=[{"id": "k1", "description": "independent validation",
                    "intent": "validate", "assigned_to": "kilo-code-auto-free"}],
        )
        bus.dispatch_step(blocked.correlation_id)
        checks["kilo_refused"] = False
        print("  UNEXPECTED: the bus dispatched to a non-connected actor")
    except RuntimeError as exc:
        loaded = bus.load_mission(blocked.correlation_id)
        print(f"  bus refused: {exc}")
        print(f"  mission state: {loaded.state}")
        print(f"  recorded error: {loaded.errors[-1]['code']}")
        checks["kilo_refused"] = (loaded.state == "blocked")

    _title("STEP 6 — resume an interrupted mission")
    interrupted = bus.open_mission(
        title="Interrupted mission",
        origin=bus.actors["openhands-cloud"],
        steps=[{"id": "r1", "description": "route a model",
                "intent": "route a model", "assigned_to": "hermes-router"}],
    )
    # Simulate a crash: mark running, never record a result.
    loaded = bus.load_mission(interrupted.correlation_id)
    loaded.state = "running"
    bus.save_mission(loaded)
    print(f"  after simulated crash: {bus.load_mission(interrupted.correlation_id).state}")
    resumed = bus.resume(interrupted.correlation_id)
    print(f"  after resume          : {resumed.state} "
          f"(next step {resumed.next_step_id})")
    checks["resume_works"] = (resumed.state == "queued"
                              and resumed.next_step_id == "r1")

    _title("STEP 7 — loop control: a failing step stops, never spins")
    flaky = bus.open_mission(
        title="Failing mission",
        origin=bus.actors["openhands-cloud"],
        steps=[{"id": "f1", "description": "always fails", "intent": "fail",
                "assigned_to": "hermes-router"}],
    )
    states = []
    for _ in range(5):  # try more times than the cap
        rec = bus.record_result(flaky.correlation_id, "f1", status="failure",
                                errors=[{"code": "demo.always_fails",
                                         "message": "forced failure",
                                         "retryable": True, "attempt": 1,
                                         "max_attempts": 3, "fatal": False}])
        states.append(rec.state)
        if rec.state == "failed":
            break
    final = bus.load_mission(flaky.correlation_id)
    print(f"  states observed: {states}")
    print(f"  attempts on f1 : {final.attempts['f1']} (cap is 3)")
    print(f"  final state    : {final.state}")
    checks["loop_control"] = (final.state == "failed" and final.attempts["f1"] == 3)

    _title("STEP 8 — record a validated learning in shared memory")
    learning = hermes.remember({
        "id": "bus-kilo-not-connected",
        "project": "tel99",
        "kind": "fact",
        "title": "Kilo n'est pas connecte dans ce depot",
        "body": ("Aucun composant Kilo n'existe dans le depot : le bus refuse "
                 "toute etape assignee a kilo-code-auto-free et marque la "
                 "mission 'blocked'. Un vrai runner Kilo devra lire "
                 "bus/inbox/kilo/*.json, ecrire bus/outbox/kilo/*.json et "
                 "passer KiloConformanceTests."),
        "tags": ["kilo", "integration", "not-connected"],
        "verified": True,
        "verified_by": "openhands",
        "confidence": 0.9,
    }, root=str(root / "memory"))
    print(f"  recorded learning {learning['id']} v{learning['version']}")
    recalled = hermes.recall("kilo not connected", root=str(root / "memory"))
    checks["learning_recorded"] = any(e["id"] == learning["id"] for e in recalled)

    _title("SUMMARY")
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all(checks.values())
    print()
    print(f"DEMONSTRATION {'OK' if all_ok else 'INCOMPLETE'}")
    print(f"  Kilo connection report: {kilo.connection_report()['reason']}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(run())
