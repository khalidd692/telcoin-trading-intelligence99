#!/usr/bin/env python3
"""Delegation vers specialiste Kilo — vraie delegation par sous-agent task.

Ce script relie un contrat de mission (avec SHA-256) a une delegation reelle
vers un specialiste Kilo (tel99-analyst, tel99-dev, tel99-verifier) via
l'outil task. Il :
  1. Lit le contrat de mission et verifie son SHA-256
  2. Cree le repertoire .kilo/specialists/<mission_id>/ avec mission.json
  3. Delegue au specialiste via l'outil task (appele par l'orchestrateur)
  4. Recupere le resultat et ecrit result.json avec le SHA-256 de l'artefact

Usage:
    python scripts/kilocli/delegate_to_specialist.py <contract_file> [--delegate]
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]   # project root (scripts/kilocli/ -> scripts/ -> root)
SPECIALISTS_DIR = ROOT / ".kilo" / "specialists"


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return "sha256:" + h.hexdigest()


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_contract(contract_path: pathlib.Path) -> dict:
    return json.loads(contract_path.read_text(encoding="utf-8"))


def verify_contract(contract: dict) -> tuple[bool, str]:
    """Verifie que le contrat a un SHA-256 valide et un statut approuve."""
    if contract.get("status") != "approved":
        return False, "contrat non approuve (status != approved)"
    if "sha256" not in contract:
        return False, "sha256 manquant dans le contrat"
    # Recalcule le hash du contrat sans le champ sha256 lui-meme
    contract_copy = {k: v for k, v in contract.items() if k != "sha256"}
    expected = sha256_text(json.dumps(contract_copy, sort_keys=True))
    if contract["sha256"] != expected:
        return False, f"SHA-256 du contrat invalide (attendu {expected}, trouve {contract['sha256']})"
    return True, "contrat valide"


def create_mission_dir(contract: dict) -> pathlib.Path:
    mission_id = contract["mission_id"]
    mission_dir = SPECIALISTS_DIR / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)

    mission_json = {
        "mission_id": mission_id,
        "title": contract["title"],
        "description": contract["description"],
        "assigned_to": contract["assigned_to"],
        "verify_by": contract.get("verify_by"),
        "files": contract.get("files", []),
        "scope": contract.get("scope", "read-only"),
        "approved_by": contract["approved_by"],
        "approved_at": contract["approved_at"],
        "contract_sha256": contract["sha256"],
        "status": "assigned",
        "assigned_at": datetime.now(timezone.utc).isoformat(),
        "author": contract["approved_by"],
    }
    (mission_dir / "mission.json").write_text(
        json.dumps(mission_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Journal de delegation vide (rempli par l'orchestrateur)
    delegation_log = mission_dir / "delegation_log.jsonl"
    if not delegation_log.is_file():
        delegation_log.write_text("", encoding="utf-8")

    return mission_dir


def write_result(mission_dir: pathlib.Path, contract: dict,
                 specialist: str, result_status: str,
                 artefact_sha256: str, evidence: str = "") -> None:
    result = {
        "mission_id": contract["mission_id"],
        "specialist": specialist,
        "status": result_status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_sha": artefact_sha256,
        "evidence": evidence,
        "source": "delegation_cas_" + contract["mission_id"],
    }
    (mission_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Mettre a jour le claim si present
    claims_dir = ROOT / ".kilo" / "claims"
    claim_file = claims_dir / f"{contract['mission_id']}.json"
    if claim_file.is_file():
        claim = json.loads(claim_file.read_text(encoding="utf-8"))
        claim["status"] = "processed"
        claim["processed_at"] = datetime.now(timezone.utc).isoformat()
        claim["processed_by"] = specialist
        claim["evidence_sha"] = artefact_sha256
        claim_file.write_text(
            json.dumps(claim, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def append_log(mission_dir: pathlib.Path, level: str, message: str) -> None:
    log_file = mission_dir / "delegation_log.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: delegate_to_specialist.py <contract_file> [--delegate]", file=sys.stderr)
        return 1

    contract_path = pathlib.Path(sys.argv[1])
    do_delegate = "--delegate" in sys.argv

    if not contract_path.is_file():
        print(f"Contrat introuvable: {contract_path}", file=sys.stderr)
        return 1

    contract = load_contract(contract_path)
    ok, reason = verify_contract(contract)
    if not ok:
        print(f"Contrat invalide: {reason}", file=sys.stderr)
        return 1

    mission_dir = create_mission_dir(contract)
    specialist = contract["assigned_to"]
    print(f"Mission {contract['mission_id']} assignee a {specialist}")
    print(f"  Repertoire: {mission_dir}")
    print(f"  Contrat SHA-256: {contract['sha256']}")

    append_log(mission_dir, "INFO", f"Contrat verifie: {contract['mission_id']} (SHA-256 OK)")
    append_log(mission_dir, "INFO", f"Specialiste assigne: {specialist}")

    if do_delegate:
        print(f"DELEGATION VERS {specialist} demandee (a executer par l'orchestrateur via task)")
        append_log(mission_dir, "INFO", f"Delegation vers {specialist} en attente")
    else:
        print("Passez --delegate pour marquer la delegation comme engagee.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
