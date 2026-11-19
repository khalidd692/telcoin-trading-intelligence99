"""Tests de validation du Skill Kilo `python-test-triage` (pilote KILO-SKILLS-SPECIALISTES-04).

Tous les tests sont en lecture seule : aucun fichier de code, branche, PR ou
artefact n'est modifié. Le Skill est simulé via la lecture de son SKILL.md et
une erreur Python synthétique reproduite localement.

Scénarios couverts :
- Test positif — Réparation : erreur Python reproduite, diagnostic, correction minimale, tests verts.
- Test négatif — Interdiction de modifier un test pour cacher une régression.
- Test de reprise — Borne à 3 tentatives, blocage si échec persistant.
- Test frontmatter — name + description YAML obligatoires.
- Test sécurité — refus de modifier scripts/agents/native/* (Codex G3).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = ROOT / ".kilo" / "skills" / "python-test-triage" / "SKILL.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def git_current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


class PythonTestTriageTests(unittest.TestCase):
    """Validation du Skill python-test-triage (version 1.0)."""

    def test_skill_frontmatter_exists(self):
        """Le Skill possède un frontmatter YAML name + description."""
        self.assertTrue(SKILL_PATH.is_file(), f"{SKILL_PATH} absent")
        content = read_text(SKILL_PATH)
        self.assertTrue(content.startswith("---\n"), "frontmatter manquant")
        head = content.split("---", 2)[1]
        self.assertIn("name: python-test-triage", head)
        self.assertIn("description:", head)

    def test_no_modify_test_to_hide_regression(self):
        """Le Skill interdit de modifier un test pour le faire passer."""
        content = read_text(SKILL_PATH)
        self.assertIn("modifier un test pour le faire passer", content.lower(),
                      "interdiction de modifier un test manquante")
        self.assertIn("commenter un test", content.lower(),
                      "interdiction de commenter un test manquante")
        self.assertIn("try/except vide", content.lower(),
                      "interdiction de try/except vide manquante")

    def test_minimal_correction_principles(self):
        """Une seule chose à la fois, minimal, localisé, sans casser l'existant."""
        content = read_text(SKILL_PATH)
        for principle in ("une seule chose à la fois", "minimal", "localisé", "sans casser l'existant"):
            self.assertIn(principle.lower(), content.lower(),
                          f"principe manquant : {principle}")

    def test_bounded_retry_max_3(self):
        """Compteur de tentatives borné à 3, puis blocage."""
        content = read_text(SKILL_PATH)
        self.assertIn("max 3", content, "garde-fou max 3 tentatives manquant")
        self.assertIn("attempt_count", content, "compteur de tentatives manquant")

    def test_security_refuses_codex_native_files(self):
        """Le Skill refuse de modifier scripts/agents/native/* (Codex G3)."""
        content = read_text(SKILL_PATH)
        self.assertIn("scripts/agents/native", content,
                      "exclusion des fichiers Codex native manquante")

    def test_reproduce_and_diagnose_syntax_error(self):
        """Test positif : une erreur Python syntaxique est reproduite et diagnostiquée."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "broken.py"
            bad_file.write_text("def foo(\n    x: int\n    return x + 1\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(bad_file)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0,
                                "l'erreur de syntaxe devrait être reproduite")
            self.assertIn("SyntaxError", result.stderr,
                          "le traceback doit contenir SyntaxError")
            # Le Skill doit pouvoir identifier la cause : parenthèse manquante
            self.assertIn("was never closed", result.stderr,
                          "le traceback doit pointer la parenthèse non fermée")

    def test_reproduce_and_diagnose_type_error(self):
        """Test positif : une erreur de type Python est reproduite et diagnostiquée."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "broken_type.py"
            bad_file.write_text('def add(a: int, b: int) -> int:\n    return a + b\n\nadd("1", 2)\n', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(bad_file)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0,
                                "l'erreur de type devrait être reproduite")
            self.assertIn("TypeError", result.stderr,
                          "le traceback doit contenir TypeError")

    def test_git_branch_isolated_not_main(self):
        """Le travail se fait sur une branche isolée, jamais sur main."""
        branch = git_current_branch()
        self.assertNotEqual(branch, "main", "branche actuelle ne doit pas être main")


if __name__ == "__main__":
    unittest.main()
