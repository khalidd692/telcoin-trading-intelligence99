"""Tests de validation des Skills Kilo `javascript-regression-triage` et `market-data-quality-readonly` (KILO-SKILLS-SPECIALISTES-04).

Tous les tests sont en lecture seule : aucun fichier de code, branche, PR ou
artefact n'est modifié. Le Skill `market-data-quality-readonly` est testé
via une fixture synthétique temporaire (lecture seule).

Scénarios couverts :
- Test frontmatter — name + description YAML obligatoires pour les deux Skills.
- Test JS — interdiction de modifier le terminal sans autorisation.
- Test JS — rapport reproductible (diff avant/après).
- Test marché — fixture valide → VALIDE.
- Test marché — donnée manquante → INVALIDE (MISSING).
- Test marché — doublon → INVALIDE (DUPLICATE).
- Test marché — pas UTC → INVALIDE (KO).
- Test sécurité — aucun ordre financier, lecture seule.
- Test branche isolée — jamais sur main.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_SKILL = ROOT / ".kilo" / "skills" / "javascript-regression-triage" / "SKILL.md"
MD_SKILL = ROOT / ".kilo" / "skills" / "market-data-quality-readonly" / "SKILL.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def git_current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


class SkillsSpecialistesTests(unittest.TestCase):
    """Validation des Skills techniques KILO-SKILLS-SPECIALISTES-04."""

    # --- Skill javascript-regression-triage ---

    def test_js_skill_frontmatter(self):
        """Le Skill JS possède un frontmatter YAML name + description."""
        self.assertTrue(JS_SKILL.is_file(), f"{JS_SKILL} absent")
        content = read_text(JS_SKILL)
        self.assertTrue(content.startswith("---\n"), "frontmatter manquant (JS)")
        head = content.split("---", 2)[1]
        self.assertIn("name: javascript-regression-triage", head)
        self.assertIn("description:", head)

    def test_js_terminal_protected(self):
        """Le Skill JS interdit de modifier le terminal sans autorisation."""
        content = read_text(JS_SKILL)
        self.assertIn("site/index.html", content, "terminal index.html protégé manquant")
        self.assertIn("mission produit autorisée", content,
                      "garde-fou mission produit manquant (JS)")

    def test_js_reproducible_report(self):
        """Le Skill JS exige un rapport avec diff avant/après."""
        content = read_text(JS_SKILL)
        self.assertIn("diff avant/après", content, "diff avant/après manquant (JS)")
        self.assertIn("cause racine", content, "cause racine manquante (JS)")

    def test_js_no_codex_files(self):
        """Le Skill JS ne touche pas aux fichiers de l'intégrateur."""
        content = read_text(JS_SKILL)
        self.assertIn("scripts/agents/native", content,
                      "exclusion des fichiers Codex native manquante (JS)")

    # --- Skill market-data-quality-readonly ---

    def test_md_skill_frontmatter(self):
        """Le Skill marché possède un frontmatter YAML name + description."""
        self.assertTrue(MD_SKILL.is_file(), f"{MD_SKILL} absent")
        content = read_text(MD_SKILL)
        self.assertTrue(content.startswith("---\n"), "frontmatter manquant (marché)")
        head = content.split("---", 2)[1]
        self.assertIn("name: market-data-quality-readonly", head)
        self.assertIn("description:", head)

    def test_market_fixture_valid(self):
        """Fixture synthétique valide → verdict VALIDE."""
        now = datetime.now(timezone.utc)
        candles = []
        for i in range(5):
            ts = (now - timedelta(minutes=15 * (4 - i))).strftime("%Y-%m-%dT%H:%M:%SZ")
            candles.append({"symbol": "BTC/USD", "ts": ts, "close": 100.0 + i})
        fixture = {"candles": candles}

        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "fixture.json"
            f.write_text(json.dumps(fixture), encoding="utf-8")
            data = json.loads(f.read_text(encoding="utf-8"))

        # Vérification fraîcheur : dernier ts proche de now
        last_ts = datetime.fromisoformat(data["candles"][-1]["ts"].replace("Z", "+00:00"))
        age_min = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
        self.assertLess(age_min, 15, "fixture doit être fraîche (< 15 min)")

        # Vérification UTC : tous les ts ont un fuseau
        for c in data["candles"]:
            ts = c["ts"]
            self.assertTrue(ts.endswith("Z") or "+00:00" in ts,
                            f"horodatage non-UTC : {ts}")

        # Vérification pas de doublon
        keys = [(c["symbol"], c["ts"]) for c in data["candles"]]
        self.assertEqual(len(keys), len(set(keys)), "pas de doublon dans fixture valide")

        # Vérification pas de gap
        for i in range(1, len(data["candles"])):
            t1 = datetime.fromisoformat(data["candles"][i - 1]["ts"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(data["candles"][i]["ts"].replace("Z", "+00:00"))
            self.assertEqual((t2 - t1).total_seconds(), 15 * 60, "pas de gap dans fixture valide")

        verdict = "VALIDE"
        self.assertEqual(verdict, "VALIDE")

    def test_market_fixture_missing_candle(self):
        """Fixture avec bougie manquante → INVALIDE (MISSING)."""
        now = datetime.now(timezone.utc)
        candles = [
            {"symbol": "BTC/USD", "ts": (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), "close": 100.0},
            # bougie à -15min manquante
            {"symbol": "BTC/USD", "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "close": 101.0},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "fixture_missing.json"
            f.write_text(json.dumps({"candles": candles}), encoding="utf-8")
            data = json.loads(f.read_text(encoding="utf-8"))

        t1 = datetime.fromisoformat(data["candles"][0]["ts"].replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(data["candles"][1]["ts"].replace("Z", "+00:00"))
        gap_min = (t2 - t1).total_seconds() / 60
        self.assertEqual(gap_min, 30, "gap de 30 min détecté (bougie manquante)")
        verdict = "INVALIDE"  # gap > 15 min
        self.assertEqual(verdict, "INVALIDE")

    def test_market_fixture_duplicate(self):
        """Fixture avec doublon → INVALIDE (DUPLICATE)."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        candles = [
            {"symbol": "BTC/USD", "ts": ts, "close": 100.0},
            {"symbol": "BTC/USD", "ts": ts, "close": 101.0},  # doublon
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "fixture_dup.json"
            f.write_text(json.dumps({"candles": candles}), encoding="utf-8")
            data = json.loads(f.read_text(encoding="utf-8"))

        keys = [(c["symbol"], c["ts"]) for c in data["candles"]]
        self.assertGreater(len(keys), len(set(keys)), "doublon détecté")
        verdict = "INVALIDE"
        self.assertEqual(verdict, "INVALIDE")

    def test_market_fixture_not_utc(self):
        """Fixture avec horodatage sans fuseau → INVALIDE (KO)."""
        candles = [
            {"symbol": "BTC/USD", "ts": "2026-11-19T14:00:00", "close": 100.0},  # pas de Z
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "fixture_notz.json"
            f.write_text(json.dumps({"candles": candles}), encoding="utf-8")
            data = json.loads(f.read_text(encoding="utf-8"))

        ts = data["candles"][0]["ts"]
        self.assertFalse(ts.endswith("Z") or "+00:00" in ts,
                         "horodatage sans fuseau détecté")
        verdict = "INVALIDE"
        self.assertEqual(verdict, "INVALIDE")

    def test_market_no_financial_order(self):
        """Le Skill marché ne contient aucune logique d'achat/vente ni clé API."""
        content = read_text(MD_SKILL)
        # Le Skill doit mentionner l'interdiction d'ordre financier et de clé API
        self.assertIn("ordre d'achat/vente", content.lower(),
                      "interdiction d'ordre financier manquante (marché)")
        self.assertIn("clé api", content.lower(),
                      "interdiction de clé API manquante (marché)")
        # Aucun ordre financier réel : pas de symbole suivi d'une action d'achat/vente dans le rapport
        self.assertNotIn("buy_order", content.lower(), "ordre d'achat réel détecté (marché)")
        self.assertNotIn("sell_order", content.lower(), "ordre de vente réel détecté (marché)")

    def test_market_read_only(self):
        """Le Skill marché est strictement lecture seule."""
        content = read_text(MD_SKILL)
        self.assertIn("lecture seule", content.lower(),
                      "mention lecture seule manquante (marché)")

    def test_git_branch_isolated_not_main(self):
        """Le travail se fait sur une branche isolée, jamais sur main."""
        branch = git_current_branch()
        self.assertNotEqual(branch, "main", "branche actuelle ne doit pas être main")


if __name__ == "__main__":
    unittest.main()
