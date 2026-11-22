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
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def test_measured_quality_ignores_untrusted_rates(self):
        with tempfile.TemporaryDirectory() as root:
            path = pathlib.Path(root) / "rates.json"
            path.write_text('{"nan":{"success_rate":NaN},"bool":{"success_rate":true},'
                            '"too-high":{"success_rate":1.2},"valid":{"success_rate":0.75}}',
                            encoding="utf-8")
            self.assertEqual(router.load_measured_quality(str(path)), {"valid": 0.75})

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

    def test_unreadable_memory_is_preserved_on_record(self):
        path = self.store._path("tel99")
        path.parent.mkdir(parents=True)
        original = b'{"project":"tel99","entries":'
        path.write_bytes(original)
        with self.assertRaises(ValueError):
            self.store.record(self._entry("tel99", "new"))
        self.assertEqual(path.read_bytes(), original)

    def test_projects_are_isolated(self):
        self.store.record(self._entry("tel99", "a", title="tel secret"))
        self.store.record(self._entry("other", "b", title="other secret"))
        tel = {e.id for e in self.store.all_entries("tel99")}
        other = {e.id for e in self.store.all_entries("other")}
        self.assertIn("a", tel)
        self.assertNotIn("b", tel)
        self.assertIn("b", other)
        self.assertNotIn("a", other)

    def test_colliding_legacy_filenames_cannot_read_or_overwrite_another_project(self):
        self.store.record(self._entry("project-a", "original"))
        with self.assertRaises(ValueError):
            self.store.search("project a", "original")
        with self.assertRaises(ValueError):
            self.store.record(self._entry("project a", "foreign"))
        self.assertEqual([entry.id for entry in self.store.all_entries("project-a")], ["original"])

    def test_store_refuses_foreign_entries_in_a_project_document(self):
        self.store.record(self._entry("project-a", "original"))
        document = self.store._path("project-a")
        data = json.loads(document.read_text(encoding="utf-8"))
        data["entries"].append(self._entry("project-b", "foreign").to_dict())
        document.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.search("project-a", "foreign")

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

    def test_supersede_cannot_copy_an_entry_from_another_project(self):
        self.store.record(self._entry("tel99", "old"))
        new = self._entry("other", "new")
        with self.assertRaises(ValueError):
            self.store.supersede("tel99", "old", new)
        self.assertEqual(new.project, "other")
        self.assertEqual(self.store.get("tel99", "old").superseded_by, "")
        self.assertIsNone(self.store.get("tel99", "new"))

    def test_supersede_commits_both_links_and_history_in_one_write(self):
        self.store.record(self._entry("tel99", "old"))
        new = self._entry("tel99", "new")
        with patch.object(self.store, "_save", wraps=self.store._save) as save:
            self.store.supersede("tel99", "old", new)
        save.assert_called_once()
        persisted = memory.MemoryStore(self.tmp.name)
        self.assertEqual(persisted.get("tel99", "old").superseded_by, "new")
        self.assertEqual(persisted.get("tel99", "new").supersedes, "old")
        self.assertEqual([event["action"] for event in persisted.history("tel99")],
                         ["record", "record", "supersede"])

    def test_supersede_rejects_a_missing_or_self_referencing_predecessor(self):
        self.store.record(self._entry("tel99", "current"))
        for old_id in ("missing", "current"):
            with self.subTest(old_id=old_id), self.assertRaises(ValueError):
                self.store.supersede("tel99", old_id, self._entry("tel99", "current"))
        self.assertEqual(self.store.get("tel99", "current").version, 1)

    def test_verify_marks_entry_verified(self):
        self.store.record(self._entry("tel99", "a", title="claim"))
        self.assertTrue(self.store.verify("tel99", "a", by="tel99-verifier"))
        self.assertTrue(self.store.get("tel99", "a").verified)

    def test_concurrent_writers_preserve_records_and_history(self):
        with ThreadPoolExecutor(max_workers=4) as threads:
            entries = [self._entry("atlas-lab", f"fact-{i}") for i in range(24)]
            list(threads.map(self.store.record, entries))
        self.assertEqual(len(self.store.all_entries("atlas-lab")), 24)
        self.assertEqual(len(self.store.history("atlas-lab")), 24)

    def test_proposal_author_cannot_verify_own_entry(self):
        entry = self._entry("atlas-lab", "proposal")
        entry.author = "author"
        self.store.record(entry)
        with self.assertRaisesRegex(ValueError, "distinct reviewer"):
            self.store.verify("atlas-lab", "proposal", by="author")
        self.assertFalse(self.store.get("atlas-lab", "proposal").verified)

    def test_search_on_unknown_project_returns_empty(self):
        self.assertEqual(self.store.search("never-seen", "anything"), [])

    def test_invalid_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            self._entry("tel99", "a", kind="nonsense")


class ImprovementTests(unittest.TestCase):
    def _outcomes(self, model, mapping):
        return [improvement.Outcome(task_id=t, model_id=model, success=s)
                for t, s in mapping.items()]

    def test_keep_when_candidate_improves_without_regression(self):
        cases = {f"task-{i}": i >= 6 for i in range(10)}
        outcomes = (self._outcomes("base", cases)
                    + self._outcomes("cand", dict.fromkeys(cases, True)))
        result = improvement.compare(outcomes, baseline_id="base", candidate_id="cand")
        self.assertEqual(result.verdict, improvement.KEEP)
        self.assertAlmostEqual(result.delta, 0.6)

    def test_paired_cost_improvement_requires_known_non_regressing_outcomes(self):
        rows = [improvement.Outcome(f"case-{i}", model, True, tokens=cost * 100,
                                    seconds=float(cost), cost_units=cost, provider_calls=cost)
                for i in range(10) for model, cost in (("base", 3), ("candidate", 2))]
        report = improvement.compare(rows, baseline_id="base", candidate_id="candidate")
        self.assertEqual(report.verdict, improvement.KEEP)
        self.assertEqual(report.to_dict()["paired_metrics"]["candidate"]["cost_units"], 20)
        self.assertEqual(report.to_dict()["paired_metrics"]["base"]["provider_calls"], 30)
        rows[1].cost_units = None
        report = improvement.compare(rows, baseline_id="base", candidate_id="candidate")
        self.assertEqual(report.verdict, improvement.REJECT)
        self.assertIsNone(report.to_dict()["paired_metrics"]["candidate"]["cost_units"])

    def test_rejects_false_boolean_and_nonfinite_observation(self):
        for success, seconds in (("false", 1.0), (True, float("nan"))):
            with self.assertRaises(ValueError):
                improvement.Outcome("case", "candidate", success, seconds=seconds)

    def test_pinned_report_is_recomputed_and_forged_verdict_is_refused(self):
        observations = [improvement.Outcome("fixture", mid, True, cost_units=1)
                        for mid in ("baseline", "candidate")]
        comparison = improvement.compare(observations, baseline_id="baseline", candidate_id="candidate")
        with tempfile.TemporaryDirectory() as directory:
            report = pathlib.Path(directory) / "report.json"
            improvement.write_evaluation_report(report, comparison, observations)
            original = report.read_bytes()
            digest = hashlib.sha256(original).hexdigest()
            self.assertEqual(improvement.review_evaluation(report, digest).verdict, improvement.REJECT)
            forged = json.loads(original)
            forged["evaluation"]["verdict"] = "keep"
            report.write_text(json.dumps(forged), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash"):
                improvement.review_evaluation(report, digest)
            with self.assertRaisesRegex(ValueError, "does not match"):
                improvement.review_evaluation(report, hashlib.sha256(report.read_bytes()).hexdigest())

    def test_one_green_pair_is_inconclusive(self):
        outcomes = (self._outcomes("base", {"t1": False})
                    + self._outcomes("cand", {"t1": True}))
        result = improvement.compare(outcomes, baseline_id="base", candidate_id="cand")
        self.assertEqual(result.verdict, improvement.INCONCLUSIVE)

    def test_candidate_cannot_drop_baseline_tasks_to_win(self):
        shared = {f"task-{i}": False for i in range(10)}
        outcomes = (self._outcomes("base", {**shared, "withheld": False})
                    + self._outcomes("cand", dict.fromkeys(shared, True)))
        result = improvement.compare(outcomes, baseline_id="base", candidate_id="cand")
        self.assertEqual(result.verdict, improvement.INCONCLUSIVE)

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

    def test_keep_is_recorded_as_a_proposal_without_self_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = memory.MemoryStore(tmp)
            cases = {f"task-{i}": False for i in range(10)}
            outcomes = (self._outcomes("base", cases)
                        + self._outcomes("cand", dict.fromkeys(cases, True)))
            result = improvement.compare(outcomes, baseline_id="base", candidate_id="cand")
            self.assertEqual(result.verdict, improvement.KEEP)
            entry_id = improvement.apply_verdict(result, store, "tel99")
            stored = store.get("tel99", entry_id)
        self.assertEqual(stored.kind, "procedure")
        self.assertFalse(stored.verified)
        self.assertEqual(stored.verified_by, "")
        self.assertIn("proposed", stored.tags)


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
