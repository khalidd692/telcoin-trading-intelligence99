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
    MIN_INTERVAL_SECONDS,
    PUBLICATION_SUBJECT_PREFIX,
    is_publication,
    parse_timestamp,
    previous_publication_age,
    should_dispatch,
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


if __name__ == "__main__":
    unittest.main()
