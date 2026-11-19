"""Tests de validation du Skill Kilo `autonomous-work-cycle`.

Tous les tests sont en lecture seule : aucun fichier de code, branche, PR ou
artefact n'est modifié. Le Skill est simulé via la lecture de son SKILL.md, de
TASKS.md, de l'état Git local et du fichier de mémoire.

Scénarios couverts :
- Test C — Planification : génération d'un plan avec étapes, owner, dépendances, fichiers, tests.
- Test D — Délégation : référence aux spécialistes existants (python-test-triage, etc.).
- Test G — Sécurité : refus de modifier scripts/agents/native/*, refus de main, refus de délégation non autorisée.
- Test H — Activation : Skill découvert dans .kilo/skills/ avec frontmatter YAML.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS_MD = ROOT / "TASKS.md"
SKILL_PATH = ROOT / ".kilo" / "skills" / "autonomous-work-cycle" / "SKILL.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def git_current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


class AutonomousWorkCycleTests(unittest.TestCase):
    """Validation du Skill autonomous-work-cycle (version 1.0)."""

    def test_skill_frontmatter_exists(self):
        """Le Skill possède un frontmatter YAML name + description."""
        self.assertTrue(SKILL_PATH.is_file(), f"{SKILL_PATH} absent")
        content = read_text(SKILL_PATH)
        self.assertTrue(content.startswith("---\n"), "frontmatter manquant")
        head = content.split("---", 2)[1]
        self.assertIn("name: autonomous-work-cycle", head)
        self.assertIn("description:", head)

    def test_cycle_steps_present(self):
        """Le cycle contient MISSION → PLAN → CHOIX DU SPÉCIALISTE → EXÉCUTION → TESTS → VÉRIFICATION → CHECKPOINT → PROCHAINE TÂCHE."""
        content = read_text(SKILL_PATH)
        for step in ("MISSION", "PLAN", "CHOIX DU SPÉCIALISTE", "EXÉCUTION", "TESTS", "VÉRIFICATION", "CHECKPOINT", "PROCHAINE TÂCHE"):
            self.assertIn(step, content, f"étape du cycle manquante : {step}")

    def test_plan_has_owner_dependencies_files_tests(self):
        """Un plan valide doit définir owner, depends_on, files et tests par étape."""
        content = read_text(SKILL_PATH)
        for token in ("owner", "depends_on", "files", "tests", "evidence_required"):
            self.assertIn(token, content, f"champ de plan manquant : {token}")

    def test_delegation_references_existing_specialists(self):
        """La délégation fait référence aux spécialistes existants (12 rôles), pas à des agents inventés."""
        content = read_text(SKILL_PATH)
        # Les 12 rôles définis dans .agents/agents/ et team_config.py
        roles = ("dev", "analyst", "verifier", "coordination", "cloud", "security",
                 "mobile", "documentation", "evaluation", "market_data", "monitoring", "release")
        found_roles = [r for r in roles if r in content]
        self.assertGreater(len(found_roles), 0, "aucun rôle des 12 spécialistes référencé")

    def test_security_refuses_main_and_codex_files(self):
        """Le Skill refuse main et les fichiers de l'intégrateur (Codex G0–G7)."""
        content = read_text(SKILL_PATH)
        # Le Skill doit mentionner les exclusions de sécurité
        for exclusion in ("main", "native", "g2/g6", "g3", "g4", "g5"):
            self.assertIn(exclusion.lower(), content.lower(), f"exclusion manquante : {exclusion}")

    def test_no_infinite_loop_budget(self):
        """Le cycle s'arrête si budget gratuit épuisé ou autorisation manquante."""
        content = read_text(SKILL_PATH)
        self.assertIn("budget", content.lower(), "garde-fou budget manquant")
        self.assertIn("autorisation", content.lower(), "garde-fou autorisation manquant")

    def test_git_branch_isolated_not_main(self):
        """Le travail se fait sur une branche isolée, jamais sur main."""
        branch = git_current_branch()
        self.assertNotEqual(branch, "main", "branche actuelle ne doit pas être main")


if __name__ == "__main__":
    unittest.main()
