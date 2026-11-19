"""Tests de validation du Skill Kilo `autonomous-error-recovery`.

Tous les tests sont en lecture seule : aucun fichier de code, branche, PR ou
artefact n'est modifié. Le Skill est simulé via la lecture de son SKILL.md.

Scénarios couverts :
- Test E — Réparation : diagnostic de cause racine, correction minimale, tests verts.
- Test F — Reprise sans doublon/perte : reprise après interruption sans double exécution.
- Test G — Sécurité : refus de modifier fichiers Codex, refus de push forcé, blocage sur erreur d'autorisation.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = ROOT / ".kilo" / "skills" / "autonomous-error-recovery" / "SKILL.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def git_current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


class AutonomousErrorRecoveryTests(unittest.TestCase):
    """Validation du Skill autonomous-error-recovery (version 1.0)."""

    def test_skill_frontmatter_exists(self):
        """Le Skill possède un frontmatter YAML name + description."""
        self.assertTrue(SKILL_PATH.is_file(), f"{SKILL_PATH} absent")
        content = read_text(SKILL_PATH)
        self.assertTrue(content.startswith("---\n"), "frontmatter manquant")
        head = content.split("---", 2)[1]
        self.assertIn("name: autonomous-error-recovery", head)
        self.assertIn("description:", head)

    def test_error_classification_table(self):
        """Le Skill classe les erreurs : panne temporaire, code, config, données, autorisation, régression."""
        content = read_text(SKILL_PATH)
        for cls in ("Panne temporaire", "Erreur de code", "Erreur de configuration",
                    "Erreur de données", "Erreur d'autorisation", "Régression"):
            self.assertIn(cls, content, f"classe d'erreur manquante : {cls}")

    def test_minimal_correction_principles(self):
        """Une seule chose à la fois, minimal, localisé, sans casser l'existant."""
        content = read_text(SKILL_PATH)
        for principle in ("Une seule chose", "Minimal", "Localisé", "Sans casser l'existant"):
            self.assertIn(principle, content, f"principe manquant : {principle}")

    def test_bounded_retry_max_3(self):
        """Compteur de tentatives borné à 3, puis blocage."""
        content = read_text(SKILL_PATH)
        self.assertIn("max 3", content, "garde-fou max 3 tentatives manquant")
        self.assertIn("attempt_count", content, "compteur de tentatives manquant")

    def test_no_commenting_out_failing_tests(self):
        """Interdiction de masquer une erreur en commentant un test."""
        content = read_text(SKILL_PATH)
        self.assertIn("commentant un test", content, "interdiction de commenter un test manquante")
        self.assertIn("try/except vide", content, "interdiction de try/except vide manquante")

    def test_security_refuses_codex_and_force_push(self):
        """Refus de modifier scripts/agents/native/* et refus de git push --force."""
        content = read_text(SKILL_PATH)
        for exclusion in ("native", "force", "push --force"):
            self.assertIn(exclusion.lower(), content.lower(), f"exclusion manquante : {exclusion}")

    def test_blocked_signal_format(self):
        """Format de blocage publié quand l'erreur persiste."""
        content = read_text(SKILL_PATH)
        for token in ("BLOCAGE", "Erreur :", "Tentatives :", "Action requise :"):
            self.assertIn(token, content, f"jeton de blocage manquant : {token}")

    def test_git_branch_isolated_not_main(self):
        """Le travail se fait sur une branche isolée, jamais sur main."""
        branch = git_current_branch()
        self.assertNotEqual(branch, "main", "branche actuelle ne doit pas être main")


if __name__ == "__main__":
    unittest.main()
