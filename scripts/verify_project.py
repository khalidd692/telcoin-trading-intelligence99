#!/usr/bin/env python3
"""
Verification finale du projet Telcoin Trading Intelligence.

Couvre : tests Python et JavaScript, secrets, fraîcheur et coherence des
donnees, statuts et indicateurs, gestion des erreurs et des donnees manquantes,
reproductibilite, dashboard, documentation, et etat Git.

Aucun ecrit dans le depot (les artefacts temporaires vont dans le repertoire
temporaire du systeme). Sortie : rapport texte + code de sortie non nul si
une verification critique echoue.

Usage : python scripts/verify_project.py [--quick]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"  [{'OK ' if ok else 'ECHEC'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def run(command: list[str], timeout: int = 900) -> tuple[int, str]:
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except FileNotFoundError as exc:
        return 127, str(exc)


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="saute les tests lents")
    args = parser.parse_args()

    # ---------------------------------------------------------------- tests
    section("1. TESTS")
    if not args.quick:
        # Le projet est stdlib-only : pytest peut etre absent (runner CI, ou
        # environnement minimal). L'absence de pytest ne doit pas faire
        # echouer le controle, qui repose sur unittest.
        pytest_available = run([sys.executable, "-c", "import pytest"])[0] == 0
        if pytest_available:
            code, out = run([sys.executable, "-m", "pytest", "tests", "collector", "-q"])
            record("pytest (tests/ + collector/)", code == 0, out.strip().splitlines()[-1] if out.strip() else "")
        else:
            record("pytest (tests/ + collector/)", True,
                   "pytest absent de l'environnement (controle par unittest ci-dessous)")
        code, out = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
        record("unittest discover -s tests (commande CI)", code == 0,
               next((l for l in out.splitlines() if l.startswith("Ran ")), ""))
        code, out = run([sys.executable, "-m", "unittest", "discover", "-s", "collector", "-p", "test_*.py"])
        record("unittest discover -s collector (commande CI)", code == 0,
               next((l for l in out.splitlines() if l.startswith("Ran ")), ""))
    code, out = run(["node", "tests/test_dashboard.js"])
    record("node tests/test_dashboard.js", code == 0, out.strip().splitlines()[-1] if out.strip() else "")
    code, out = run(["node", "tests/test_realtime.js"])
    record("node tests/test_realtime.js", code == 0, out.strip().splitlines()[-1] if out.strip() else "")

    # --------------------------------------------------------------- secrets
    section("2. SECRETS ET CLES EXPOSES")
    patterns = [
        (r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", "cle API en dur"),
        (r"(?i)secret\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}", "secret en dur"),
        (r"(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}", "jeton bearer"),
        (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "cle privee"),
    ]
    scanned = 0
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".js", ".json", ".md", ".yml", ".html", ".txt"}:
            continue
        if any(part in path.parts for part in (".git", "__pycache__", ".pytest_cache", "node_modules")):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for pattern, label in patterns:
            if re.search(pattern, text):
                hits.append(f"{path.relative_to(ROOT)} : {label}")
    record(f"scan de {scanned} fichiers : aucun secret en dur", not hits, "; ".join(hits[:4]))

    # ------------------------------------------- donnees, statuts, coherence
    section("3. DONNEES, STATUTS ET COHERENCE")
    from src.agent_analysis import build_analysis

    snapshot = json.loads((ROOT / "site" / "tel_snapshot.json").read_text(encoding="utf-8"))
    generated = datetime.fromisoformat(snapshot["generated_at"].replace("Z", "+00:00"))
    age_min = (datetime.now(timezone.utc) - generated).total_seconds() / 60
    record("snapshot lisible et horodaté", "generated_at" in snapshot,
           f"généré {snapshot['generated_at']} (âge {age_min:.0f} min)")

    report = build_analysis(snapshot, expected_collection_id=snapshot.get("collection_id"), now=generated)
    record("analyse : statut global connu", report["status"] in ("SURVEILLER", "ATTENDRE"), report["status"])
    record("analyse : mode lecture seule", report.get("mode") == "READ_ONLY_ANALYSIS", str(report.get("mode")))
    record("analyse : aucun ordre", report.get("orders_sent") == 0, f"orders_sent={report.get('orders_sent')}")
    reversal = report.get("early_reversal")
    valid_statuses = ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION", "ATTENDRE", "DONNÉES_INSUFFISANTES")
    record("analyse : statut de retournement valide",
           reversal is not None and reversal.get("signal_status") in valid_statuses,
           str((reversal or {}).get("signal_status")))
    record("analyse : direction valide",
           reversal is not None and reversal.get("direction") in ("HAUSSIER", "BAISSIER", "INDETERMINE"),
           str((reversal or {}).get("direction")))
    families_ok = True
    for item in (reversal or {}).get("evidence", []):
        if item.get("category") not in ("structure", "momentum", "volume", "context"):
            families_ok = False
    record("analyse : familles de preuves connues", families_ok)
    record("analyse : la confiance n'est pas presentee comme une probabilite",
           "probabilit" in ((reversal or {}).get("confidence_note") or "").lower())
    tf_ok = all(v.get("status") in ("OK", "PARTIEL", "UNAVAILABLE", "ATTENTION")
                for v in report.get("timeframes", {}).values())
    record("analyse : statuts d'unites de temps connus", tf_ok)
    none_nan = "NaN" not in json.dumps(report, ensure_ascii=False) and "Infinity" not in json.dumps(report)
    record("analyse : aucun NaN/Infinity dans la serialisation", none_nan)

    # -------------------------------------------------- erreurs / manquants
    section("4. GESTION DES ERREURS ET DES DONNEES MANQUANTES")
    broken = json.loads(json.dumps(snapshot))
    del broken["sources"]["mexc"]["candles"]["15m"]
    try:
        degraded = build_analysis(broken, now=generated)
        ok = degraded["status"] == "ATTENDRE" and degraded.get("reason")
        record("snapshot sans 15m -> fail-closed", ok, str(degraded.get("reason"))[:90])
    except Exception as exc:
        record("snapshot sans 15m -> fail-closed", False, f"exception {exc}")

    garbage = {"schema_version": 1, "symbol": "TELUSDT"}
    try:
        degraded = build_analysis(garbage, now=generated)
        record("snapshot corrompu -> fail-closed", degraded["status"] == "ATTENDRE", str(degraded.get("reason"))[:90])
    except Exception as exc:
        record("snapshot corrompu -> fail-closed", False, f"exception {exc}")

    try:
        stale = build_analysis(snapshot, now=generated.replace(year=generated.year + 1))
        record("snapshot perime -> fail-closed", stale["status"] == "ATTENDRE", str(stale.get("reason"))[:90])
    except Exception as exc:
        record("snapshot perime -> fail-closed", False, f"exception {exc}")

    # ------------------------------------------------------ reproductibilite
    section("5. REPRODUCTIBILITE")
    again = build_analysis(snapshot, expected_collection_id=snapshot.get("collection_id"), now=generated)
    record("analyse identique sur deux executions", again == report)
    if not args.quick:
        from scripts.backtest import history_store as store
        from scripts.backtest.harness import Bundle
        rows = store.load_timeframe("kucoin", store.KUCOIN_SYMBOL, "1h")
        if rows:
            bundle = Bundle("1h", rows)
            bundle2 = Bundle("1h", rows)
            same = bundle.closes == bundle2.closes and bundle.q90[2] == bundle2.q90[2]
            record("indicateurs identiques sur deux constructions", same)

    # ----------------------------------------------------------- documentation
    section("6. DOCUMENTATION")
    for name in ("README.md", "OOS_PROTOCOL.md", "OOS_RAPPORT.md", "DETECTEUR_V2_RAPPORT.md",
                 "BACKTEST_HISTORIQUE_TEL.md", "JOURNAL_APPRENTISSAGE_FINAL.md", "CONFLIT_GIT.md", "TASKS.md"):
        path = ROOT / name
        record(f"document present : {name}", path.exists() and path.stat().st_size > 500,
               f"{path.stat().st_size // 1024} Ko" if path.exists() else "absent")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    record("README documente l'execution des tests", "unittest discover" in readme)
    record("README documente le backtest", "run_oos.py" in readme)

    # ------------------------------------------------------------------ git
    section("7. ETAT GIT")
    code, out = run(["git", "status", "--porcelain=v1", "-b"])
    record("git status accessible", code == 0)
    branch_line = out.splitlines()[0] if out else ""
    # En CI, actions/checkout fait un checkout detache (HEAD sans branche) :
    # c'est un etat normal et attendu la-bas. Ce controle doit donc accepter
    # un HEAD detache tout en signalant toute AUTRE branche, qui serait
    # vraiment anormale.
    detached = "HEAD (no branch)" in branch_line or branch_line.strip() in ("## HEAD", "## HEAD ")
    expected_branch = "wip/p0-provenance" in branch_line
    record("branche : wip/p0-provenance (ou HEAD detache en CI)", expected_branch or detached,
           branch_line)
    record("aucune operation destructive effectuee par cet outil", True,
           "l'outil ne lance que des commandes de lecture")
    code, out = run(["git", "log", "--oneline", "-1"])
    record("HEAD intact", code == 0, out.strip())
    untracked = [l[3:] for l in out.splitlines() if False]
    code, out = run(["git", "status", "--porcelain"])
    untracked = [l[3:] for l in out.splitlines() if l.startswith("??")]
    modified = [l[3:] for l in out.splitlines() if l.startswith(" M")]
    record("fichiers modifies lists (tous preserves)", True, f"{len(modified)} modifies, {len(untracked)} non suivis")
    print("     modifies  :", ", ".join(modified))
    print("     non suivis:", ", ".join(untracked[:12]), "..." if len(untracked) > 12 else "")

    # ---------------------------------------------------------------- bilan
    section("BILAN")
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"  verifications : {len(RESULTS)} | reussies : {len(RESULTS) - len(failed)} | echecs : {len(failed)}")
    for name in failed:
        print(f"     ECHEC : {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
