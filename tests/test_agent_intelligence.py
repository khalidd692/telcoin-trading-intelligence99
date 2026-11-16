#!/usr/bin/env python3
"""Tests for the TEL99 agent intelligence layer.

Stdlib only, no network, no LLM: the layer is deterministic by design, so the
tests assert exact, reproducible behaviour. They cover the four capabilities the
mission asked for — model choice, memory retrieval, knowledge reuse, measured
improvement — plus the safety invariants (project isolation, no-spend,
fail-closed availability and quota).
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agents"))

from intelligence import catalog, improvement, memory, router  # noqa: E402
from intelligence import demo  # noqa: E402


class RouterTests(unittest.TestCase):
    def test_easy_task_is_classified_easy(self):
        level, _ = router.classify_difficulty(router.TaskProfile(kind="general"))
        self.assertEqual(level, router.EASY)

    def test_large_code_task_is_hard(self):
        task = router.TaskProfile(kind="code", touches_files=6,
                                  estimated_tokens=80_000)
        level, _ = router.classify_difficulty(task)
        self.assertEqual(level, router.HARD)

    def test_medium_task(self):
        level, _ = router.classify_difficulty(
            router.TaskProfile(kind="code", touches_files=1)
        )
        self.assertEqual(level, router.MEDIUM)

    def test_router_never_chooses_a_non_free_model(self):
        # A hard task wants a strong model; gpt-5.6 is strong but not free, so
        # the router must still refuse it.
        task = router.TaskProfile(kind="code", touches_files=6,
                                  estimated_tokens=90_000)
        decision = router.route(task, dry_run=True)
        self.assertNotEqual(decision.chosen.id if decision.chosen else None, "gpt-5.6")
        reasons = " ".join(r["reason"] for r in decision.rejected)
        self.assertIn("no-spend rule", reasons)

    def test_real_run_refuses_when_availability_is_unverified(self):
        # Every catalogue model is unverified in this repo, so a real run must
        # fail closed rather than invent availability.
        decision = router.route(router.TaskProfile(kind="code"),
                                quota_remaining=10, dry_run=False)
        self.assertFalse(decision.ok)

    def test_real_run_refuses_when_quota_is_unknown(self):
        decision = router.route(router.TaskProfile(kind="code"),
                                quota_remaining=None, dry_run=False)
        self.assertFalse(decision.ok)
        self.assertTrue(any("quota unknown" in r for r in decision.reasons))

    def test_real_run_refuses_when_quota_is_low(self):
        decision = router.route(router.TaskProfile(kind="code"),
                                quota_remaining=0, min_quota=1, dry_run=False)
        self.assertFalse(decision.ok)

    def test_dry_run_can_choose_and_flags_unverified(self):
        decision = router.route(router.TaskProfile(kind="code"), dry_run=True)
        self.assertTrue(decision.ok)
        self.assertTrue(decision.chosen.is_free)

    def test_measured_quality_overrides_prior(self):
        # Give the local model a measured rate that beats the cloud model.
        measured = {"local/qwen2.5-coder-7b": 0.99}
        decision = router.route(router.TaskProfile(kind="code"), dry_run=True,
                                measured_quality=measured)
        self.assertEqual(decision.chosen.id, "local/qwen2.5-coder-7b")

    def test_decision_journal_records_every_rejection(self):
        journal: list[dict] = []
        router.route(router.TaskProfile(kind="code"), dry_run=True, journal=journal)
        self.assertEqual(len(journal), 1)
        entry = journal[0]
        self.assertIn("chosen", entry)
        self.assertTrue(entry["rejected"])
        self.assertEqual(entry["difficulty"], router.MEDIUM)

    def test_fallbacks_are_ordered_after_the_choice(self):
        decision = router.route(router.TaskProfile(kind="general"), dry_run=True)
        self.assertTrue(decision.ok)
        self.assertNotIn(decision.chosen.id, [m.id for m in decision.fallbacks])

    def test_load_measured_quality_ignores_missing_file(self):
        self.assertEqual(router.load_measured_quality("/nonexistent/x.json"), {})


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = memory.MemoryStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _entry(self, project, entry_id, **kw):
        return memory.Entry(id=entry_id, project=project, kind=kw.get("kind", "fact"),
                            title=kw.get("title", entry_id),
                            body=kw.get("body", ""), tags=kw.get("tags", ()),
                            verified=kw.get("verified", False))

    def test_record_and_get(self):
        self.store.record(self._entry("tel99", "a", title="alpha"))
        got = self.store.get("tel99", "a")
        self.assertIsNotNone(got)
        self.assertEqual(got.title, "alpha")

    def test_re_recording_bumps_version_and_keeps_history(self):
        self.store.record(self._entry("tel99", "a", title="alpha"))
        self.store.record(self._entry("tel99", "a", title="alpha v2"))
        got = self.store.get("tel99", "a")
        self.assertEqual(got.version, 2)
        self.assertGreaterEqual(len(self.store.history("tel99")), 2)

    def test_projects_are_isolated(self):
        self.store.record(self._entry("tel99", "a", title="tel secret"))
        self.store.record(self._entry("other", "b", title="other secret"))
        tel = {e.id for e in self.store.all_entries("tel99")}
        other = {e.id for e in self.store.all_entries("other")}
        self.assertIn("a", tel)
        self.assertNotIn("b", tel)
        self.assertIn("b", other)
        self.assertNotIn("a", other)

    def test_common_pool_is_visible_to_every_project(self):
        self.store.record(self._entry(memory.COMMON_PROJECT, "c", title="shared rule"))
        self.assertIn("c", {e.id for e in self.store.all_entries("tel99")})

    def test_search_ranks_title_matches_first(self):
        self.store.record(self._entry("tel99", "a", title="guard git bypass"))
        self.store.record(self._entry("tel99", "b", title="unrelated note",
                                      body="nothing here"))
        results = self.store.search("tel99", "guard bypass")
        self.assertEqual(results[0].id, "a")

    def test_search_excludes_superseded_by_default(self):
        self.store.record(self._entry("tel99", "old", title="guard rule v1"))
        new = self._entry("tel99", "new", title="guard rule v2")
        self.store.supersede("tel99", "old", new)
        results = self.store.search("tel99", "guard rule")
        ids = [e.id for e in results]
        self.assertNotIn("old", ids)
        self.assertIn("new", ids)

    def test_supersede_keeps_the_old_entry_auditable(self):
        self.store.record(self._entry("tel99", "old", title="guard rule v1"))
        self.store.supersede("tel99", "old", self._entry("tel99", "new",
                                                         title="guard rule v2"))
        old = self.store.get("tel99", "old")
        self.assertEqual(old.superseded_by, "new")
        self.assertEqual(self.store.get("tel99", "new").supersedes, "old")

    def test_verify_marks_entry_verified(self):
        self.store.record(self._entry("tel99", "a", title="claim"))
        self.assertTrue(self.store.verify("tel99", "a", by="tel99-verifier"))
        self.assertTrue(self.store.get("tel99", "a").verified)

    def test_search_on_unknown_project_returns_empty(self):
        self.assertEqual(self.store.search("never-seen", "anything"), [])

    def test_invalid_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            self._entry("tel99", "a", kind="nonsense")


class _InMemoryBackend:
    """A minimal durable-backend double implementing the protocol contract."""

    backend = "kv"
    durable_across_container = True

    def __init__(self):
        self.data: dict = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value

    def keys(self, prefix=""):
        return [k for k in self.data if k.startswith(prefix)]

    def durable(self):
        return True


class DurableMemoryTests(unittest.TestCase):
    """The memory must be able to survive a container when given a backend."""

    def _entry(self, project, entry_id, **kw):
        return memory.Entry(id=entry_id, project=project,
                            kind=kw.get("kind", "fact"),
                            title=kw.get("title", entry_id),
                            body=kw.get("body", ""), tags=kw.get("tags", ()))

    def test_file_store_is_not_durable_and_backend_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(memory.MemoryStore(tmp).durable())
        self.assertTrue(memory.MemoryStore(backend=_InMemoryBackend()).durable())

    def test_second_store_reads_what_the_first_recorded(self):
        # Two separate MemoryStore instances sharing one durable backend stand
        # in for two independent runs: run B must see run A's entry.
        backend = _InMemoryBackend()
        run_a = memory.MemoryStore(backend=backend)
        run_a.record(self._entry("tel99", "fact-1", title="freshness rule"))
        run_b = memory.MemoryStore(backend=backend)
        got = run_b.get("tel99", "fact-1")
        self.assertIsNotNone(got)
        self.assertEqual(got.title, "freshness rule")
        self.assertEqual([e.id for e in run_b.search("tel99", "freshness")],
                         ["fact-1"])

    def test_backend_isolation_is_preserved(self):
        backend = _InMemoryBackend()
        store = memory.MemoryStore(backend=backend)
        store.record(self._entry("tel99", "secret", title="tel99 only"))
        store.record(self._entry("other", "private", title="other project"))
        tel = {e.id for e in store.all_entries("tel99")}
        other = {e.id for e in store.all_entries("other")}
        self.assertIn("secret", tel)
        self.assertNotIn("private", tel)
        self.assertNotIn("secret", other)

    def test_backend_keys_are_namespaced_under_memory(self):
        backend = _InMemoryBackend()
        store = memory.MemoryStore(backend=backend)
        store.record(self._entry("tel99", "x", title="x"))
        self.assertTrue(all(k.startswith("memory/") for k in backend.keys()))

    def test_file_root_still_works_after_backend_support(self):
        # Backward compatibility: file storage keeps its on-disk layout.
        with tempfile.TemporaryDirectory() as tmp:
            store = memory.MemoryStore(tmp)
            store.record(self._entry("tel99", "a", title="alpha"))
            self.assertTrue((pathlib.Path(tmp) / "projects" / "tel99.json").is_file())
            self.assertEqual(store.get("tel99", "a").title, "alpha")

    def test_store_without_root_or_backend_raises_on_write(self):
        store = memory.MemoryStore()
        self.assertFalse(store.durable())
        with self.assertRaises(ValueError):
            store.record(self._entry("tel99", "a", title="alpha"))


class KvBackedMemoryTests(unittest.TestCase):
    """MemoryStore over the real KvStore wire protocol (local KV server)."""

    def setUp(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        outer = self
        self.kv: dict = {}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, obj):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                key = urlparse(self.path).path.rsplit("/", 1)[-1]
                if key not in outer.kv:
                    return self._send(404, {"detail": "not found"})
                return self._send(200, {"value": outer.kv[key]})

            def do_PUT(self):
                key = urlparse(self.path).path.rsplit("/", 1)[-1]
                length = int(self.headers.get("Content-Length", 0))
                value = json.loads(self.rfile.read(length).decode() or "null")
                outer.kv[key] = value
                return self._send(201, {"key": key})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()

    def test_kv_backed_store_round_trips_over_http(self):
        from protocol.store import KvStore
        base = f"http://127.0.0.1:{self.port}"
        run_a = memory.MemoryStore(backend=KvStore(base, "tok", prefix="tel99-memory"))
        self.assertTrue(run_a.durable())
        run_a.record(memory.Entry(id="k1", project="tel99", kind="fact",
                                  title="kv durable", body=""))
        # A brand-new client (as a second run would create) reads it back.
        run_b = memory.MemoryStore(backend=KvStore(base, "tok", prefix="tel99-memory"))
        self.assertEqual(run_b.get("tel99", "k1").title, "kv durable")

    def test_kv_backend_is_namespaced(self):
        from protocol.store import KvStore
        base = f"http://127.0.0.1:{self.port}"
        store = memory.MemoryStore(backend=KvStore(base, "tok", prefix="tel99-memory"))
        store.record(memory.Entry(id="k1", project="tel99", kind="fact",
                                  title="x", body=""))
        self.assertTrue(all(k.startswith("tel99-memory.") for k in self.kv))


class ImprovementTests(unittest.TestCase):
    def _outcomes(self, model, mapping):
        return [improvement.Outcome(task_id=t, model_id=model, success=s)
                for t, s in mapping.items()]

    def test_keep_when_candidate_improves_without_regression(self):
        outcomes = (self._outcomes("base", {"t1": False, "t2": True})
                    + self._outcomes("cand", {"t1": True, "t2": True}))
        result = improvement.compare(outcomes, baseline_id="base",
                                     candidate_id="cand")
        self.assertEqual(result.verdict, improvement.KEEP)
        self.assertAlmostEqual(result.delta, 0.5)

    def test_reject_on_regression(self):
        outcomes = (self._outcomes("base", {"t1": True, "t2": False})
                    + self._outcomes("cand", {"t1": False, "t2": True}))
        result = improvement.compare(outcomes, baseline_id="base",
                                     candidate_id="cand")
        self.assertEqual(result.verdict, improvement.REJECT)
        self.assertTrue(any("regressed" in r for r in result.reasons))

    def test_only_shared_tasks_are_counted(self):
        outcomes = (self._outcomes("base", {"t1": True, "t2": True})
                    + self._outcomes("cand", {"t1": True}))
        result = improvement.compare(outcomes, baseline_id="base",
                                     candidate_id="cand")
        self.assertEqual(result.task_count, 1)

    def test_inconclusive_without_shared_tasks(self):
        outcomes = (self._outcomes("base", {"t1": True})
                    + self._outcomes("cand", {"t2": True}))
        result = improvement.compare(outcomes, baseline_id="base",
                                     candidate_id="cand")
        self.assertEqual(result.verdict, improvement.INCONCLUSIVE)

    def test_write_and_read_measured_quality(self):
        outcomes = self._outcomes("m1", {"t1": True, "t2": False})
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "measured.json"
            improvement.write_measured_quality(path, outcomes)
            loaded = router.load_measured_quality(str(path))
        self.assertEqual(loaded["m1"], 0.5)

    def test_apply_verdict_records_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = memory.MemoryStore(tmp)
            outcomes = (self._outcomes("base", {"t1": False})
                        + self._outcomes("cand", {"t1": True}))
            result = improvement.compare(outcomes, baseline_id="base",
                                         candidate_id="cand")
            entry_id = improvement.apply_verdict(result, store, "tel99")
            stored = store.get("tel99", entry_id)
        self.assertEqual(stored.kind, "procedure")
        self.assertTrue(stored.verified)


class DemoIntegrationTests(unittest.TestCase):
    """The end-to-end demonstration must really work, offline and repeatable."""

    def test_demo_runs_and_improves(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Seed the knowledge a previous session would have stored.
            store = memory.MemoryStore(tmp)
            store.record(memory.Entry(
                id="guard-git-value-options", project="tel99", kind="fix",
                title="Le garde-fou doit ignorer les options globales de git a valeur",
                body="git -C push, git -c commit, timeout/nice/xargs, find -delete",
                tags=("guard", "git", "security", "bypass"), verified=True,
                verified_by="tel99-verifier",
            ))
            with contextlib.redirect_stdout(io.StringIO()):
                code = demo.run(dry_run=False, memory_root=tmp)
        self.assertEqual(code, 0)

    def test_demo_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = memory.MemoryStore(tmp)
            store.record(memory.Entry(
                id="guard-git-value-options", project="tel99", kind="fix",
                title="guard git option push bypass",
                body="git -C push bypass", tags=("guard", "git"), verified=True,
            ))
            with contextlib.redirect_stdout(io.StringIO()):
                first = demo.run(dry_run=True, memory_root=tmp)
                second = demo.run(dry_run=True, memory_root=tmp)
        self.assertEqual(first, second)


class CatalogueTests(unittest.TestCase):
    def test_every_model_declares_its_evidence(self):
        for spec in catalog.MODEL_CATALOG:
            with self.subTest(model=spec.id):
                self.assertTrue(spec.evidence.strip())
                self.assertIn(spec.cost_tier, (catalog.COST_FREE,
                                               catalog.COST_UNKNOWN))

    def test_free_models_helper(self):
        self.assertTrue(all(m.is_free for m in catalog.free_models()))

    def test_by_id_finds_and_misses(self):
        self.assertIsNotNone(catalog.by_id("openhands/deepseek-v4.1-flash"))
        self.assertIsNone(catalog.by_id("does-not-exist"))


if __name__ == "__main__":
    unittest.main()
