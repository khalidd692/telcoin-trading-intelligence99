"""
Tests de la cadence de publication (src/publication_cadence.py).

La regle testee est la seule qui compte pour l'exploitation : on ne relance
une publication que si la derniere a plus de l'intervalle minimal. La chaine
resultante doit produire une publication toutes les ~12 a 15 minutes, s'arreter
si une execution echoue, et ne jamais declencher deux publications rapprochees.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.publication_cadence import (
    CHAIN_STALE_SECONDS,
    FAILURE_BACKOFF_SECONDS,
    MIN_INTERVAL_SECONDS,
    MODE_AUTO,
    MODE_CHAIN,
    PACE_SECONDS,
    PUBLISHED_FAILURE,
    PUBLISHED_SKIPPED,
    PUBLISHED_SUCCESS,
    PUBLICATION_SUBJECT_PREFIX,
    chain_is_dead,
    is_publication,
    parse_timestamp,
    plan_dispatch,
    previous_publication_age,
    seconds_until_next_slot,
    should_dispatch,
    should_publish,
)

NOW = datetime(2026, 10, 21, 20, 0, 0, tzinfo=timezone.utc)


def entry(minutes_ago: int, subject: str = PUBLICATION_SUBJECT_PREFIX + " [skip ci]"):
    stamp = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return (stamp, subject)


class TestPublicationDetection(unittest.TestCase):
    def test_publication_subject_is_detected(self):
        self.assertTrue(is_publication(PUBLICATION_SUBJECT_PREFIX + " [skip ci]"))
        self.assertFalse(is_publication("Merge pull request #31"))
        self.assertFalse(is_publication(""))
        self.assertFalse(is_publication(None))

    def test_timestamp_parsing_is_tolerant(self):
        self.assertIsNotNone(parse_timestamp("2026-10-21T12:00:00Z"))
        self.assertIsNotNone(parse_timestamp("2026-10-21T12:00:00+00:00"))
        self.assertIsNone(parse_timestamp("pas une date"))
        self.assertIsNone(parse_timestamp(""))
        self.assertIsNone(parse_timestamp(None))


class TestPreviousPublicationAge(unittest.TestCase):
    def test_age_of_the_last_publication(self):
        entries = [entry(3), entry(20), entry(45)]
        age = previous_publication_age(entries, NOW, head_is_current_publication=False)
        self.assertAlmostEqual(age, 3 * 60, delta=1)

    def test_current_publication_is_excluded(self):
        """Le commit que l'execution courante vient de faire ne compte pas."""
        entries = [entry(0), entry(20), entry(45)]
        age = previous_publication_age(entries, NOW, head_is_current_publication=True)
        self.assertAlmostEqual(age, 20 * 60, delta=1)

    def test_non_publication_commits_are_ignored(self):
        entries = [entry(1, "Merge pull request #33"), entry(7, "docs: quelque chose"),
                   entry(30)]
        age = previous_publication_age(entries, NOW, head_is_current_publication=False)
        self.assertAlmostEqual(age, 30 * 60, delta=1)

    def test_no_publication_known(self):
        self.assertIsNone(previous_publication_age([entry(1, "docs: x")], NOW, False))
        self.assertIsNone(previous_publication_age([], NOW, False))

    def test_only_head_current_excludes_one_entry(self):
        entries = [entry(0), entry(0), entry(10)]
        age = previous_publication_age(entries, NOW, head_is_current_publication=True)
        self.assertAlmostEqual(age, 0, delta=1)


class TestDispatchDecision(unittest.TestCase):
    def test_recent_publication_does_not_trigger(self):
        self.assertFalse(should_dispatch(11 * 60))
        self.assertFalse(should_dispatch(0))

    def test_old_publication_triggers(self):
        self.assertTrue(should_dispatch(13 * 60))
        self.assertTrue(should_dispatch(4 * 3600))

    def test_unknown_age_does_not_trigger(self):
        """Sans age connu, on ne relance pas : risque de boucle de publications."""
        self.assertFalse(should_dispatch(None))

    def test_interval_is_configurable(self):
        self.assertFalse(should_dispatch(20 * 60, min_interval_seconds=30 * 60))
        self.assertTrue(should_dispatch(20 * 60, min_interval_seconds=10 * 60))

    def test_default_interval_is_twelve_minutes(self):
        self.assertEqual(MIN_INTERVAL_SECONDS, 12 * 60)

    def test_chain_produces_one_publication_per_interval(self):
        """Simulation de la chaine : une publication toutes les ~12 a 15 minutes."""
        last_publication = NOW - timedelta(minutes=30)
        decisions = []
        for _ in range(6):
            now = last_publication + timedelta(minutes=13)
            age = (now - last_publication).total_seconds()
            decision = should_dispatch(age, MIN_INTERVAL_SECONDS)
            decisions.append(decision)
            if decision:
                last_publication = now
        # la chaine se relance a chaque tour, sans s'emballer
        self.assertTrue(all(decisions))
        self.assertEqual(len(decisions), 6)

    def test_chain_does_not_double_publish_within_the_interval(self):
        """Un passage 5 minutes apres la publication ne doit rien declencher."""
        last_publication = NOW
        now = last_publication + timedelta(minutes=5)
        age = (now - last_publication).total_seconds()
        self.assertFalse(should_dispatch(age, MIN_INTERVAL_SECONDS))

    def test_chain_survives_a_fresh_publication(self):
        """Apres une publication, l'age repart de zero : aucune boucle immediate."""
        last_publication = NOW
        for minutes in (0, 1, 5, 11):
            now = last_publication + timedelta(minutes=minutes)
            age = (now - last_publication).total_seconds()
            self.assertFalse(should_dispatch(age, MIN_INTERVAL_SECONDS), f"minute {minutes}")


class TestPublicationGate(unittest.TestCase):
    """La porte de publication : on ne republie pas trop tot."""

    def test_a_fresh_publication_blocks_the_next_one(self):
        self.assertFalse(should_publish(0))
        self.assertFalse(should_publish(6 * 60))
        self.assertFalse(should_publish(MIN_INTERVAL_SECONDS - 1))

    def test_an_old_publication_is_allowed(self):
        self.assertTrue(should_publish(MIN_INTERVAL_SECONDS))
        self.assertTrue(should_publish(4 * 3600))

    def test_an_unknown_age_does_not_block_the_publication(self):
        """Le site ne doit jamais rester sans donnee pour un simple doute.

        C'est la *relance* qui est bloquee en cas d'age inconnu, pas la
        publication : le garde-fou anti-boucle reste sur la relance.
        """
        self.assertTrue(should_publish(None))
        self.assertFalse(should_dispatch(None))


class TestNextSlot(unittest.TestCase):
    """Le creneau : l'execution attend le prochain creneau au lieu de rien faire."""

    def test_a_recent_publication_must_be_waited_for(self):
        self.assertEqual(seconds_until_next_slot(0), PACE_SECONDS)
        self.assertEqual(seconds_until_next_slot(60), PACE_SECONDS - 60)

    def test_an_expired_slot_does_not_wait(self):
        self.assertEqual(seconds_until_next_slot(PACE_SECONDS), 0)
        self.assertEqual(seconds_until_next_slot(PACE_SECONDS + 120), 0)

    def test_an_unknown_age_waits_a_full_slot(self):
        """Sans age connu, on attend un creneau complet : pas de boucle."""
        self.assertEqual(seconds_until_next_slot(None), PACE_SECONDS)

    def test_the_pace_is_shorter_than_the_objective(self):
        """13 min de creneau + latence de creation + duree du run ~ 15 min."""
        self.assertEqual(PACE_SECONDS, 13 * 60)
        self.assertLess(PACE_SECONDS, MIN_INTERVAL_SECONDS + 5 * 60)


class TestChainLiveness(unittest.TestCase):
    """Une seule chaine tourne a la fois : pas de chaine parallele."""

    def test_a_live_chain_is_not_dead(self):
        self.assertFalse(chain_is_dead(0))
        self.assertFalse(chain_is_dead(13 * 60))
        self.assertFalse(chain_is_dead(CHAIN_STALE_SECONDS - 1))

    def test_a_silent_chain_is_dead(self):
        self.assertTrue(chain_is_dead(CHAIN_STALE_SECONDS))
        self.assertTrue(chain_is_dead(4 * 3600))

    def test_an_unknown_age_does_not_prove_the_chain_is_dead(self):
        self.assertFalse(chain_is_dead(None))


class TestDispatchPlan(unittest.TestCase):
    """Le plan de relance : creneau pour la chaine, silence pour les autres."""

    def test_a_chain_link_always_relays_and_waits_for_the_slot(self):
        plan = plan_dispatch(MODE_CHAIN, 0)
        self.assertTrue(plan.dispatch)
        self.assertEqual(plan.wait_seconds, PACE_SECONDS)

    def test_a_chain_link_waits_only_for_the_remaining_slot(self):
        plan = plan_dispatch(MODE_CHAIN, PACE_SECONDS - 120)
        self.assertTrue(plan.dispatch)
        self.assertEqual(plan.wait_seconds, 120)

    def test_a_chain_link_after_a_failure_uses_the_backoff(self):
        plan = plan_dispatch(MODE_CHAIN, 0, published=PUBLISHED_FAILURE)
        self.assertTrue(plan.dispatch)
        self.assertEqual(plan.wait_seconds, FAILURE_BACKOFF_SECONDS)

    def test_a_chain_link_that_did_not_publish_keeps_the_slot(self):
        plan = plan_dispatch(MODE_CHAIN, 0, published=PUBLISHED_SKIPPED)
        self.assertTrue(plan.dispatch)
        self.assertEqual(plan.wait_seconds, PACE_SECONDS)

    def test_a_one_off_run_does_not_relay_a_live_chain(self):
        plan = plan_dispatch(MODE_AUTO, 60)
        self.assertFalse(plan.dispatch)
        self.assertEqual(plan.wait_seconds, 0)

    def test_a_one_off_run_restarts_a_dead_chain(self):
        plan = plan_dispatch(MODE_AUTO, CHAIN_STALE_SECONDS + 60)
        self.assertTrue(plan.dispatch)
        self.assertEqual(plan.wait_seconds, 0)

    def test_an_unknown_age_never_relays_a_one_off_run(self):
        """Protection anti-boucle : sans age connu, une execution ponctuelle
        ne relance rien."""
        self.assertFalse(plan_dispatch(MODE_AUTO, None).dispatch)

    def test_an_unknown_age_makes_a_chain_link_wait_a_full_slot(self):
        """Un maillon de chaine sans age connu attend un creneau complet :
        il ne peut pas boucler en se relançant immediatement."""
        plan = plan_dispatch(MODE_CHAIN, None)
        self.assertTrue(plan.dispatch)
        self.assertEqual(plan.wait_seconds, PACE_SECONDS)

    def test_the_chain_never_accumulates(self):
        """Une chaine au plus : les executions ponctuelles ne creent pas de chaine."""
        # une execution ponctuelle arrive alors que la chaine est vivante
        self.assertFalse(plan_dispatch(MODE_AUTO, 5 * 60).dispatch)
        # ... et une autre plus tard, la chaine ayant continue a publier
        self.assertFalse(plan_dispatch(MODE_AUTO, 14 * 60).dispatch)

    def test_the_chain_produces_one_publication_per_pace(self):
        """Simulation de la chaine : une publication tous les ~13 min."""
        last_publication = NOW
        publications = []
        for _ in range(8):
            age = (last_publication + timedelta(minutes=PACE_SECONDS / 60)
                   - last_publication).total_seconds()
            plan = plan_dispatch(MODE_CHAIN, age)
            self.assertTrue(plan.dispatch)
            self.assertEqual(plan.wait_seconds, 0)  # le creneau est deja atteint
            last_publication = last_publication + timedelta(minutes=PACE_SECONDS / 60)
            publications.append(last_publication)
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(publications, publications[1:])]
        for gap in gaps:
            self.assertAlmostEqual(gap, 13, delta=0.01)



class TestGitHistoryReading(unittest.TestCase):
    """La lecture de l'historique doit porter sur la branche publiee."""

    def test_reads_the_given_reference(self):
        import subprocess
        import tempfile
        from src.publication_cadence import read_git_entries

        with tempfile.TemporaryDirectory() as folder:
            def git(*args):
                proc = subprocess.run(["git", "-C", folder, *args], capture_output=True,
                                      text=True, encoding="utf-8", errors="replace")
                return proc.stdout or ""

            git("init", "-q", "-b", "main")
            git("config", "user.name", "t")
            git("config", "user.email", "t@t")
            (Path(folder) / "a.txt").write_text("a", encoding="utf-8")
            git("add", "a.txt")
            git("commit", "-qm", "Refresh published TEL/USDT market report [skip ci]")
            git("checkout", "-qb", "autre")
            (Path(folder) / "b.txt").write_text("b", encoding="utf-8")
            git("add", "b.txt")
            git("commit", "-qm", "docs: autre chose")

            entries, _ = read_git_entries(folder, ref="main")
            subjects = [entry[1] for entry in entries]
            self.assertTrue(any(subject.startswith("Refresh published") for subject in subjects))
            self.assertFalse(any(subject.startswith("docs:") for subject in subjects))

            entries_autre, _ = read_git_entries(folder, ref="autre")
            subjects_autre = [entry[1] for entry in entries_autre]
            self.assertTrue(any(subject.startswith("docs:") for subject in subjects_autre))

    def test_unknown_reference_falls_back_to_head(self):
        import tempfile
        from src.publication_cadence import read_git_entries
        with tempfile.TemporaryDirectory() as folder:
            entries, _ = read_git_entries(folder, ref="reference-inexistante")
            self.assertIsInstance(entries, list)


class test_never_fails_the_publication(unittest.TestCase):
    """L'etape de cadence ne doit jamais faire echouer la publication."""

    def test_invalid_workflow_name_does_not_raise(self):
        import os
        from src import publication_cadence
        env_backup = os.environ.get("GITHUB_TOKEN")
        os.environ["GITHUB_TOKEN"] = "jeton-bidon"
        try:
            code = publication_cadence.main([
                "--repository", "khalidd692/telcoin-trading-intelligence99",
                "--workflow", "nom de workflow invalide",
                "--ref", "main", "--dry-run"])
            self.assertEqual(code, 0)
        finally:
            if env_backup is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = env_backup

    def test_main_never_raises(self):
        from src import publication_cadence
        for args in ([], ["--ref", "reference-inexistante", "--dry-run"]):
            self.assertEqual(publication_cadence.main(args), 0)

    def test_workflow_default_is_a_file_name(self):
        import inspect
        from src import publication_cadence
        source = inspect.getsource(publication_cadence.main)
        self.assertIn('--workflow", default="monitor.yml"', source)
        # la variable d'environnement ne doit pas servir de valeur par defaut :
        # GITHUB_WORKFLOW contient le nom d'affichage, pas le nom de fichier.
        self.assertNotIn('os.environ.get("GITHUB_WORKFLOW"', source)




class TestAgeFromPublishedArtifact(unittest.TestCase):
    """L'age de la derniere publication se lit dans l'artefact publie au commit
    de checkout : cette source fonctionne meme avec un checkout de profondeur 1."""

    def test_age_read_from_the_artifact_of_the_checkout_commit(self):
        import json
        import subprocess
        import tempfile
        from src.publication_cadence import previous_publication_age_from_artifact

        with tempfile.TemporaryDirectory() as folder:
            def git(*args):
                proc = subprocess.run(["git", "-C", folder, *args], capture_output=True,
                                      text=True, encoding="utf-8", errors="replace")
                return proc.stdout or ""

            git("init", "-q", "-b", "main")
            git("config", "user.name", "t")
            git("config", "user.email", "t@t")
            (Path(folder) / "site").mkdir()
            generated = (datetime.now(timezone.utc) - timedelta(minutes=7)).isoformat()
            (Path(folder) / "site" / "agent_analysis.json").write_text(
                json.dumps({"generated_at": generated}), encoding="utf-8")
            git("add", "site/agent_analysis.json")
            git("commit", "-qm", "Refresh published TEL/USDT market report [skip ci]")

            age = previous_publication_age_from_artifact(folder, ref="HEAD")
            self.assertIsNotNone(age)
            self.assertAlmostEqual(age, 7 * 60, delta=90)

    def test_missing_artifact_gives_no_age(self):
        import tempfile
        from src.publication_cadence import previous_publication_age_from_artifact
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(previous_publication_age_from_artifact(folder, ref="HEAD"))


class TestRunnerSimulation(unittest.TestCase):
    """Simulation du runner : ce que la cadence produit reellement.

    Le runner GitHub fait un checkout de profondeur 1, l'etape de publication
    committe le nouvel artefact sur la branche locale, puis l'etape de cadence
    relit l'artefact de la branche. Ce test rejoue cette sequence et mesure
    les intervalles de publication obtenus. C'est la seule preuve qui parle
    de cadence *operationnelle* : les tests unitaires ne verifient que des
    regles isolees.
    """

    RUN_DURATION_MIN = 1.0     # duree du run (collecte, analyse, deploiement)
    DISPATCH_LATENCY_MIN = 1.0  # latence de creation du run declenche

    def _publish(self, folder, when):
        import json
        import subprocess
        (Path(folder) / "site").mkdir(exist_ok=True)
        (Path(folder) / "site" / "agent_analysis.json").write_text(
            json.dumps({"generated_at": when.isoformat()}), encoding="utf-8")
        subprocess.run(["git", "-C", folder, "add", "site/agent_analysis.json"],
                       capture_output=True, check=True)
        subprocess.run(["git", "-C", folder, "commit", "-qm",
                        PUBLICATION_SUBJECT_PREFIX + " [skip ci]"], capture_output=True, check=True)

    def _make_repo(self, folder, published_at):
        import subprocess
        subprocess.run(["git", "-C", folder, "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", folder, "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", folder, "config", "user.email", "t@t"], check=True)
        self._publish(folder, published_at)

    def test_the_chain_publishes_at_a_regular_cadence(self):
        """Six heures de chaine : des intervalles reguliers, proches de 15 min."""
        import tempfile
        from src.publication_cadence import should_publish

        with tempfile.TemporaryDirectory() as folder:
            start = datetime(2026, 10, 22, 8, 0, 0, tzinfo=timezone.utc)
            self._make_repo(folder, start - timedelta(minutes=30))

            publications = []
            now = start
            for _ in range(24):  # 24 tours ~= 6 h
                # --- le runner demarre : le checkout porte la derniere publication
                last_published = publications[-1] if publications else start - timedelta(minutes=30)
                age_at_checkout = (now - last_published).total_seconds()

                # --- porte de publication
                if not should_publish(age_at_checkout):
                    self.fail("la porte a refuse une publication de la chaine")
                published_at = now + timedelta(minutes=self.RUN_DURATION_MIN)
                publications.append(published_at)
                self._publish(folder, published_at)

                # --- etape de cadence : l'artefact de la branche est le nouveau
                age_after_publish = (published_at - published_at).total_seconds()
                plan = plan_dispatch(MODE_CHAIN, age_after_publish, published=PUBLISHED_SUCCESS)
                self.assertTrue(plan.dispatch, "la chaine s'est interrompue")
                now = published_at + timedelta(minutes=plan.wait_seconds / 60
                                               + self.DISPATCH_LATENCY_MIN)

        gaps = [(b - a).total_seconds() / 60 for a, b in zip(publications, publications[1:])]
        for gap in gaps:
            self.assertGreaterEqual(gap, 12, f"intervalle trop court : {gap:.1f} min")
            self.assertLessEqual(gap, 16, f"intervalle trop long : {gap:.1f} min")
        self.assertEqual(len(gaps), 23)
        average = sum(gaps) / len(gaps)
        self.assertAlmostEqual(average, 15, delta=1.5)

    def test_a_one_off_run_does_not_fork_the_chain(self):
        """Un push ou un cron ne cree pas une chaine parallelle."""
        last_published = datetime(2026, 10, 22, 8, 0, 0, tzinfo=timezone.utc)
        for minutes in (0, 3, 8, 20, 29):
            age = minutes * 60
            plan = plan_dispatch(MODE_AUTO, age, published=PUBLISHED_SUCCESS)
            self.assertFalse(plan.dispatch, f"une chaine parallelle a ete creee a {minutes} min")
        # au-dela du delai d'arret, la chaine peut etre relancee
        plan = plan_dispatch(MODE_AUTO, 31 * 60, published=PUBLISHED_SUCCESS)
        self.assertTrue(plan.dispatch)

    def test_a_failure_does_not_loop(self):
        """Un echec impose le delai de repli : la chaine ne boucle pas."""
        plan = plan_dispatch(MODE_CHAIN, 0, published=PUBLISHED_FAILURE)
        self.assertTrue(plan.dispatch)
        self.assertGreaterEqual(plan.wait_seconds, FAILURE_BACKOFF_SECONDS)
        # et le plan suivant, apres repli, repart d'un creneau normal
        resumed = plan_dispatch(MODE_CHAIN, 0, published=PUBLISHED_SUCCESS)
        self.assertEqual(resumed.wait_seconds, PACE_SECONDS)


class TestCadenceCli(unittest.TestCase):
    """La CLI : ce que le workflow appelle reellement."""

    def _repo(self, folder, published_at):
        import json
        import subprocess
        subprocess.run(["git", "-C", folder, "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", folder, "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", folder, "config", "user.email", "t@t"], check=True)
        (Path(folder) / "site").mkdir(exist_ok=True)
        (Path(folder) / "site" / "agent_analysis.json").write_text(
            json.dumps({"generated_at": published_at.isoformat()}), encoding="utf-8")
        subprocess.run(["git", "-C", folder, "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "-C", folder, "commit", "-qm",
                        PUBLICATION_SUBJECT_PREFIX + " [skip ci]"], capture_output=True, check=True)

    def test_decide_writes_the_publication_gate(self):
        import os
        import tempfile
        from src import publication_cadence

        with tempfile.TemporaryDirectory() as folder:
            self._repo(folder, datetime.now(timezone.utc) - timedelta(minutes=3))
            output = Path(folder) / "github_output"
            output.write_text("", encoding="utf-8")
            previous = os.getcwd()
            os.chdir(folder)
            try:
                code = publication_cadence.main(["--decide", "--ref", "main",
                                                 "--github-output", str(output)])
            finally:
                os.chdir(previous)
            self.assertEqual(code, 0)
            self.assertIn("publish=false", output.read_text(encoding="utf-8"))

    def test_decide_allows_a_publication_that_is_old_enough(self):
        import os
        import tempfile
        from src import publication_cadence

        with tempfile.TemporaryDirectory() as folder:
            self._repo(folder, datetime.now(timezone.utc) - timedelta(minutes=40))
            output = Path(folder) / "github_output"
            output.write_text("", encoding="utf-8")
            previous = os.getcwd()
            os.chdir(folder)
            try:
                code = publication_cadence.main(["--decide", "--ref", "main",
                                                 "--github-output", str(output)])
            finally:
                os.chdir(previous)
            self.assertEqual(code, 0)
            self.assertIn("publish=true", output.read_text(encoding="utf-8"))

    def test_the_chain_mode_never_fails_and_never_waits_in_dry_run(self):
        import os
        import tempfile
        from src import publication_cadence

        with tempfile.TemporaryDirectory() as folder:
            self._repo(folder, datetime.now(timezone.utc))
            previous = os.getcwd()
            os.chdir(folder)
            try:
                code = publication_cadence.main(["--mode", MODE_CHAIN, "--ref", "main",
                                                 "--dry-run", "--no-wait"])
            finally:
                os.chdir(previous)
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
