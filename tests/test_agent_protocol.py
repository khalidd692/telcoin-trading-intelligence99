#!/usr/bin/env python3
"""Tests for the TEL99 agent interchange protocol and integration bus.

Stdlib only, offline (the network probes are skipped unless explicitly enabled).
They cover the four mission requirements — a common versioned protocol, the
integration layer, the real cloud capabilities, and an end-to-end distributed
mission — plus the safety invariants: fail-closed routing to a dead endpoint,
loop control, deterministic error handling and resume.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from protocol import Envelope, Actor, validate  # noqa: E402
from protocol import bus as bus_mod  # noqa: E402
from protocol.adapters import hermes, kilo, openhands  # noqa: E402
from protocol.bus import Bus, MissionRecord  # noqa: E402


def _mission(**kw):
    return Envelope.create(
        origin=Actor("openhands", "tester", connected=True), kind="mission",
        title=kw.pop("title", "test mission"), **kw,
    )


class EnvelopeTests(unittest.TestCase):
    def test_create_mission_is_valid(self):
        env = _mission()
        self.assertEqual(validate(env.to_dict()), [])

    def test_protocol_block_is_versioned(self):
        data = _mission().to_dict()
        self.assertEqual(data["protocol"]["name"], "tel99-agent-interchange")
        self.assertEqual(data["protocol"]["version"], 1)

    def test_roundtrip_preserves_identity(self):
        env = _mission()
        again = Envelope.from_json(env.to_json())
        self.assertEqual(again.envelope_id, env.envelope_id)
        self.assertEqual(again.correlation_id, env.correlation_id)
        self.assertEqual(again.mission["title"], env.mission["title"])

    def test_unknown_protocol_version_is_rejected(self):
        data = _mission().to_dict()
        data["protocol"]["version"] = 99
        problems = validate(data)
        self.assertTrue(any("unsupported protocol version" in p for p in problems))

    def test_missing_required_field_is_rejected(self):
        data = _mission().to_dict()
        del data["state"]
        self.assertTrue(any("missing required field 'state'" in p
                            for p in validate(data)))

    def test_bad_kind_is_rejected(self):
        data = _mission().to_dict()
        data["kind"] = "nonsense"
        self.assertTrue(any("kind" in p for p in validate(data)))

    def test_terminal_mission_requires_result(self):
        env = _mission()
        env.state = "done"
        self.assertTrue(any("must carry a result" in p
                            for p in validate(env.to_dict())))

    def test_bad_envelope_id_pattern_is_rejected(self):
        data = _mission().to_dict()
        data["envelope_id"] = "no"      # too short
        self.assertTrue(any("id pattern" in p for p in validate(data)))

    def test_error_entry_needs_code_and_message(self):
        env = _mission()
        env.errors = [{"code": "x"}]     # missing message
        self.assertTrue(any("errors[0]" in p for p in validate(env.to_dict())))

    def test_learning_entry_needs_id_and_text(self):
        env = _mission()
        env.learnings = [{"id": "l1"}]   # missing text
        self.assertTrue(any("learnings[0]" in p for p in validate(env.to_dict())))

    def test_priority_bounds(self):
        env = _mission()
        env.priority = 42
        self.assertTrue(any("priority" in p for p in validate(env.to_dict())))

    def test_validate_rejects_non_object(self):
        self.assertEqual(validate(["not", "an", "object"]),
                         ["envelope is not a JSON object"])

    def test_is_terminal(self):
        from protocol import is_terminal
        self.assertTrue(is_terminal("done"))
        self.assertTrue(is_terminal("failed"))
        self.assertFalse(is_terminal("running"))


class ActorTests(unittest.TestCase):
    def test_openhands_is_connected(self):
        self.assertTrue(openhands.actor().connected)

    def test_hermes_is_connected_in_process(self):
        self.assertTrue(hermes.actor().connected)

    def test_kilo_is_declared_not_connected(self):
        self.assertFalse(kilo.actor().connected)
        self.assertFalse(kilo.is_connected())
        self.assertIn("no Kilo component", kilo.connection_report()["reason"])


class BusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bus = Bus(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _steps(self, assign="hermes-router"):
        return [{"id": "s1", "description": "do a thing", "intent": "route",
                 "assigned_to": assign}]

    def test_registry_lists_three_environments(self):
        envs = {a["environment"] for a in self.bus.actors.values()}
        self.assertEqual(envs, {"openhands", "hermes", "kilo"})

    def test_connected_actors_excludes_kilo(self):
        connected = self.bus.connected_actors()
        self.assertIn("openhands-cloud", connected)
        self.assertIn("hermes-router", connected)
        self.assertNotIn("kilo-code-auto-free", connected)

    def test_open_mission_persists_and_is_queued(self):
        record = self.bus.open_mission(title="m", origin=self.bus.actors["openhands-cloud"],
                                       steps=self._steps())
        self.assertEqual(record.state, "queued")
        loaded = self.bus.load_mission(record.correlation_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.title, "m")

    def test_dispatch_to_connected_actor_creates_sub_mission(self):
        record = self.bus.open_mission(title="m", origin=self.bus.actors["openhands-cloud"],
                                       steps=self._steps())
        env = self.bus.dispatch_step(record.correlation_id)
        self.assertEqual(env.kind, "sub_mission")
        self.assertEqual(env.target.id, "hermes-router")
        self.assertEqual(env.correlation_id, record.correlation_id)

    def test_dispatch_to_dead_endpoint_is_refused(self):
        record = self.bus.open_mission(title="m", origin=self.bus.actors["openhands-cloud"],
                                       steps=self._steps(assign="kilo-code-auto-free"))
        with self.assertRaises(RuntimeError):
            self.bus.dispatch_step(record.correlation_id)
        loaded = self.bus.load_mission(record.correlation_id)
        self.assertEqual(loaded.state, "blocked")
        self.assertEqual(loaded.errors[-1]["code"], "bus.actor_not_connected")

    def test_success_completes_the_mission(self):
        record = self.bus.open_mission(title="m", origin=self.bus.actors["openhands-cloud"],
                                       steps=self._steps())
        self.bus.dispatch_step(record.correlation_id)
        done = self.bus.record_result(record.correlation_id, "s1", status="success")
        self.assertEqual(done.state, "done")
        self.assertEqual(done.result["status"], "success")

    def test_failure_retries_then_fails_deterministically(self):
        record = self.bus.open_mission(title="m", origin=self.bus.actors["openhands-cloud"],
                                       steps=self._steps())
        for _ in range(bus_mod.MAX_ATTEMPTS_PER_STEP):
            rec = self.bus.record_result(
                record.correlation_id, "s1", status="failure",
                errors=[{"code": "e", "message": "boom", "retryable": True,
                         "attempt": 1, "max_attempts": 3, "fatal": False}])
        self.assertEqual(rec.state, "failed")
        self.assertEqual(rec.attempts["s1"], bus_mod.MAX_ATTEMPTS_PER_STEP)

    def test_fatal_error_fails_immediately(self):
        record = self.bus.open_mission(title="m", origin=self.bus.actors["openhands-cloud"],
                                       steps=self._steps())
        rec = self.bus.record_result(
            record.correlation_id, "s1", status="failure",
            errors=[{"code": "e", "message": "fatal", "retryable": False,
                     "attempt": 1, "max_attempts": 3, "fatal": True}])
        self.assertEqual(rec.state, "failed")

    def test_step_cap_prevents_runaway(self):
        steps = [{"id": f"s{i}", "description": "x", "intent": "route",
                  "assigned_to": "hermes-router"}
                 for i in range(bus_mod.MAX_STEPS_PER_MISSION + 5)]
        record = self.bus.open_mission(title="big", origin=self.bus.actors["openhands-cloud"],
                                       steps=steps)
        # Complete exactly the cap, then the next dispatch must fail.
        for i in range(bus_mod.MAX_STEPS_PER_MISSION):
            self.bus.record_result(record.correlation_id, f"s{i}", status="success")
        rec = self.bus.record_result(record.correlation_id, f"s{bus_mod.MAX_STEPS_PER_MISSION}",
                                     status="success")
        self.assertEqual(rec.state, "failed")
        self.assertEqual(rec.errors[-1]["code"], "bus.step_cap")

    def test_resume_returns_to_next_unfinished_step(self):
        record = self.bus.open_mission(title="m", origin=self.bus.actors["openhands-cloud"],
                                       steps=self._steps())
        loaded = self.bus.load_mission(record.correlation_id)
        loaded.state = "running"          # simulate a crash
        self.bus.save_mission(loaded)
        resumed = self.bus.resume(record.correlation_id)
        self.assertEqual(resumed.state, "queued")
        self.assertEqual(resumed.next_step_id, "s1")

    def test_resume_is_a_noop_on_terminal_mission(self):
        record = self.bus.open_mission(title="m", origin=self.bus.actors["openhands-cloud"],
                                       steps=self._steps())
        self.bus.record_result(record.correlation_id, "s1", status="success")
        again = self.bus.resume(record.correlation_id)
        self.assertEqual(again.state, "done")

    def test_envelope_persisted_and_readable(self):
        record = self.bus.open_mission(title="m", origin=self.bus.actors["openhands-cloud"],
                                       steps=self._steps())
        env = self.bus.dispatch_step(record.correlation_id)
        again = self.bus.read_envelope(env.envelope_id)
        self.assertIsNotNone(again)
        self.assertEqual(again.mission["id"], env.mission["id"])

    def test_unknown_mission_raises(self):
        with self.assertRaises(KeyError):
            self.bus.dispatch_step("msn-does-not-exist-00000000")


class HermesAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_route_returns_a_decision(self):
        decision = hermes.route("code", touches_files=1)
        self.assertIn(decision["difficulty"], ("easy", "medium", "hard"))
        self.assertIn("chosen", decision)

    def test_remember_then_recall_roundtrip(self):
        hermes.remember({"id": "learn-1", "project": "tel99", "kind": "fact",
                         "title": "une lecon verifiee", "body": "corps",
                         "tags": ["test"], "verified": True},
                        root=self.tmp.name)
        hits = hermes.recall("lecon verifiee", project="tel99", root=self.tmp.name)
        self.assertTrue(any(h["id"] == "learn-1" for h in hits))

    def test_handle_routes_a_mission_envelope(self):
        env = Envelope.create(origin=Actor("openhands", "t", connected=True),
                              kind="sub_mission", title="route a model",
                              description="route a model")
        reply = hermes.handle(env, root=self.tmp.name)
        self.assertEqual(reply.state, "done")
        self.assertIn("routed to", reply.result["summary"])

    def test_handle_refuses_unsupported_intent(self):
        env = Envelope.create(origin=Actor("openhands", "t", connected=True),
                              kind="sub_mission", title="x",
                              description="do something hermes cannot")
        reply = hermes.handle(env, root=self.tmp.name)
        self.assertEqual(reply.state, "failed")
        self.assertEqual(reply.errors[0]["code"], "hermes.unsupported_intent")


class KiloAdapterTests(unittest.TestCase):
    def test_enqueue_writes_to_the_file_bus(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Envelope.create(origin=Actor("openhands", "t", connected=True),
                                  kind="sub_mission", title="validate")
            path = kilo.enqueue(env, inbox=pathlib.Path(tmp) / "kilo")
            self.assertTrue(path.is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(validate(data), [])

    def test_collect_reads_what_a_kilo_runner_left(self):
        with tempfile.TemporaryDirectory() as tmp:
            outbox = pathlib.Path(tmp) / "kilo"
            outbox.mkdir(parents=True)
            reply = Envelope.create(origin=kilo.actor(), kind="result",
                                    state="done",
                                    result={"status": "success", "summary": "ok"})
            (outbox / "r.json").write_text(reply.to_json(), encoding="utf-8")
            collected = kilo.collect(outbox=outbox)
            self.assertEqual(len(collected), 1)
            self.assertEqual(collected[0]["origin"]["environment"], "kilo")

    def test_conformance_accepts_a_valid_kilo_reply(self):
        reply = Envelope.create(origin=kilo.actor(), kind="result", state="done",
                                result={"status": "success"})
        self.assertEqual(kilo.conformance_checks(reply.to_dict()), [])

    def test_conformance_rejects_a_non_kilo_envelope(self):
        env = Envelope.create(origin=Actor("openhands", "t", connected=True),
                              kind="result", state="done",
                              result={"status": "success"})
        problems = kilo.conformance_checks(env.to_dict())
        self.assertTrue(any("origin.environment" in p for p in problems))


class OpenHandsAdapterTests(unittest.TestCase):
    """Live probes. Skipped unless TEL99_LIVE_PROBES=1 to keep CI offline."""

    def setUp(self):
        import os
        if os.environ.get("TEL99_LIVE_PROBES") != "1":
            self.skipTest("set TEL99_LIVE_PROBES=1 to run live probes")

    def test_agent_server_reachable(self):
        self.assertTrue(openhands.probe_agent_server()["reachable"])

    def test_conversation_route_is_live(self):
        self.assertTrue(openhands.probe_conversation_creation()["endpoint_live"])

    def test_quota_readable(self):
        probe = openhands.probe_quota()
        self.assertTrue(probe["reachable"])
        self.assertIsInstance(probe["remaining"], int)


class EndToEndTests(unittest.TestCase):
    def test_full_demo_passes_offline(self):
        from protocol import demo
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                code = demo.run(bus_root=tmp, probe=False)
        self.assertEqual(code, 0)

    def test_demo_is_deterministic(self):
        from protocol import demo
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                first = demo.run(bus_root=tmp, probe=False)
                second = demo.run(bus_root=tmp, probe=False)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
