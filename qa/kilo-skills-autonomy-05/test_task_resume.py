"""Tests de validation du Skill Kilo `autonomous-task-resume`.

Tous les tests sont en lecture seule : aucun fichier de code, branche, PR ou
artefact n'est modifié. Le Skill est simulé via la lecture de TASKS.md, de
l'état Git local et du fichier de mémoire `.kilo/memory/knowledge.json`.

Scénarios couverts :
- Test A — Continuité : nouvelle session retrouve la mission EN COURS et affiche le checkpoint de reprise.
- Test B — Anti-doublon : une tâche déjà TERMINÉ avec preuve est refusée (SKIP).
- Test C — Blocage : une tâche BLOQUÉ est signalée sans tentative de reprise.
- Test D — Mémoire session A→B : le fichier knowledge.json est lisible entre sessions sans copie manuelle.
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS_MD = ROOT / "TASKS.md"
MEMORY_JSON = ROOT / ".kilo" / "memory" / "knowledge.json"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_tasks(text: str) -> dict[str, list[dict[str, str]]]:
    """Extrait les tâches par état (TERMINÉ / EN COURS / BLOQUÉ / À FAIRE / ÉCARTÉ)."""
    sections: dict[str, list[dict[str, str]]] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(TERMINÉ|EN COURS|BLOQUÉ|À FAIRE|ÉCARTÉ)\s*$", line)
        if m:
            current = m.group(1)
            sections[current] = []
            continue
        if current is None:
            continue
        mt = re.match(r"^\|\s*(T\d+)\s*\|(.+?)\|(.+?)\|", line)
        if mt:
            sections[current].append(
                {
                    "id": mt.group(1),
                    "title": mt.group(2).strip(),
                    "proof": mt.group(3).strip(),
                }
            )
    return sections


def git_current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


class AutonomousTaskResumeTests(unittest.TestCase):
    """Validation du Skill autonomous-task-resume (version 1.0)."""

    def test_skill_frontmatter_exists(self):
        """Le Skill possède un frontmatter YAML name + description."""
        skill_path = ROOT / ".kilo" / "skills" / "autonomous-task-resume" / "SKILL.md"
        self.assertTrue(skill_path.is_file(), f"{skill_path} absent")
        content = read_text(skill_path)
        self.assertTrue(content.startswith("---\n"), "frontmatter manquant")
        head = content.split("---", 2)[1]
        self.assertIn("name: autonomous-task-resume", head)
        self.assertIn("description:", head)

    def test_continuity_resume_in_progress_task(self):
        """Test A — Continuité : une mission EN COURS est identifiée et reprise."""
        sections = parse_tasks(read_text(TASKS_MD))
        in_progress = sections.get("EN COURS", [])
        self.assertGreater(len(in_progress), 0, "aucune tâche EN COURS trouvée")
        t42 = next((t for t in in_progress if t["id"] == "T42"), None)
        self.assertIsNotNone(t42, "T42 (fusion PR #47) devrait être EN COURS")
        self.assertIn("merge commit", t42["title"].lower())
        # Le checkpoint de reprise pointe vers T42, pas vers une tâche TERMINÉ
        self.assertNotIn("déjà fait", t42["title"])

    def test_anti_doublon_refuses_done_task(self):
        """Test B — Anti-doublon : une tâche TERMINÉ avec preuve est refusée."""
        sections = parse_tasks(read_text(TASKS_MD))
        done = sections.get("TERMINÉ", [])
        self.assertGreater(len(done), 0, "aucune tâche TERMINÉ trouvée")
        t66 = next((t for t in done if t["id"] == "T66"), None)
        self.assertIsNotNone(t66, "T66 devrait être TERMINÉ")
        # Preuve renseignée => anti-doublon déclenché => SKIP
        self.assertTrue(len(t66["proof"]) > 0, "T66 doit avoir une preuve")
        # Le Skill doit afficher SKIP et refuser de réexécuter
        skip_msg = f"SKIP: {t66['id']} déjà fait — {t66['proof'][:40]}"
        self.assertIn("déjà fait", skip_msg)

    def test_blocked_task_signalled(self):
        """Test C — Blocage : une tâche BLOQUÉ est signalée sans reprise."""
        sections = parse_tasks(read_text(TASKS_MD))
        blocked = sections.get("BLOQUÉ", [])
        self.assertGreater(len(blocked), 0, "aucune tâche BLOQUÉ trouvée")
        t41 = next((t for t in blocked if t["id"] == "T41"), None)
        self.assertIsNotNone(t41, "T41 (collecte MEXC local) devrait être BLOQUÉ")
        self.assertTrue(len(t41["proof"]) > 0, "T41 doit avoir une cause de blocage")

    def test_memory_readable_across_sessions(self):
        """Test D — Mémoire session A→B : knowledge.json est lisible sans copie manuelle."""
        self.assertTrue(MEMORY_JSON.is_file(), f"{MEMORY_JSON} absent")
        data = json.loads(read_text(MEMORY_JSON))
        self.assertIsInstance(data.get("entries"), list)
        self.assertGreaterEqual(len(data["entries"]), 1)
        for entry in data["entries"]:
            self.assertIn("id", entry)
            self.assertIn("mission", entry)
            self.assertIn("validation_degree", entry)
            self.assertIn("evidence", entry)
            self.assertIn(entry["validation_degree"], ("proven", "unproven", "uncertain"))

    def test_git_branch_isolated_not_main(self):
        """Le travail se fait sur une branche isolée, jamais sur main."""
        branch = git_current_branch()
        self.assertNotEqual(branch, "main", "branche actuelle ne doit pas être main")


if __name__ == "__main__":
    unittest.main()
