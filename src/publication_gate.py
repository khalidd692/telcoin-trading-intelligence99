"""
Porte de publication : controle de provenance des artefacts avant publication.

Cette porte est le dernier rempart avant que des artefacts de marche ne soient
publies. Elle refuse tout artefact qui n'est pas entierement tracable :

  - les trois artefacts (instantane, rapport, analyse) doivent exister et etre
    non vides ;
  - chacun doit porter un `collection_id` non vide, le symbole TELUSDT et un
    marqueur `collection_status` a `VALID` ou `FALLBACK` ;
  - un artefact en `FALLBACK` (donnees indisponibles) n'est **jamais** publie ;
  - les trois artefacts doivent partager le meme `collection_id`, et celui-ci
    doit correspondre a celui du tour de collecte de la CI ;
  - l'instantane doit porter un `snapshot_id` egal a l'empreinte deterministe
    de ses propres donnees (sources + controle croise).

La logique habitait dans le workflow, en script inline : elle n'etait donc
ni testee, ni reutilisable, et une divergence entre la porte et le collecteur
n'a pas pu etre detectee. Elle vit maintenant dans ce module, utilise tel quel
par le workflow **et** par les tests.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from collector.tel_collector import compute_snapshot_fingerprint

#: Artefacts publies, dans l'ordre de verification.
ARTIFACTS = (
    ("snapshot", "site/tel_snapshot.json"),
    ("report", "site/report.json"),
    ("analysis", "site/agent_analysis.json"),
)

#: Etats de collection acceptes par la porte.
ACCEPTED_COLLECTION_STATUS = {"VALID", "FALLBACK"}


class PublicationRejected(Exception):
    """Raised when the artifacts cannot be published (fail-closed)."""


def validate_artifacts(snapshot: Any, report: Any, analysis: Any,
                        expected_collection_id: Optional[str]) -> None:
    """Verifie la coherence de provenance des trois artefacts.

    Leve PublicationRejected avec un message explicite. Ne leve rien si tout
    est coherent : c'est la seule voie vers la publication.
    """
    for name, obj in (("snapshot", snapshot), ("report", report), ("analysis", analysis)):
        if not isinstance(obj, dict):
            raise PublicationRejected(f"{name} artifact is not an object")
        if obj.get("collection_id") is None or str(obj.get("collection_id")).strip() == "":
            raise PublicationRejected(f"{name} artifact missing or empty collection_id")
        if obj.get("symbol") != "TELUSDT":
            raise PublicationRejected(f"{name} artifact symbol mismatch")
        if obj.get("collection_status") not in ACCEPTED_COLLECTION_STATUS:
            raise PublicationRejected(f"{name} artifact missing reliable collection_status marker")
        if obj.get("collection_status") == "FALLBACK":
            raise PublicationRejected(f"{name} artifact is a fallback and cannot be published")

    if snapshot.get("collection_id") != report.get("collection_id"):
        raise PublicationRejected("snapshot and report have different collection_id")
    if snapshot.get("collection_id") != analysis.get("collection_id"):
        raise PublicationRejected("snapshot and analysis have different collection_id")

    if not expected_collection_id or str(expected_collection_id).strip() == "":
        raise PublicationRejected("COLLECTION_ID is empty or missing in workflow environment")
    if snapshot.get("collection_id") != expected_collection_id:
        raise PublicationRejected("collection_id mismatch with workflow value")

    if not isinstance(snapshot.get("snapshot_id"), str) or len(snapshot["snapshot_id"]) != 64:
        raise PublicationRejected("snapshot_id missing or malformed")

    try:
        expected_hash = compute_snapshot_fingerprint(snapshot.get("sources"),
                                                      snapshot.get("cross_check"))
    except Exception as exc:
        raise PublicationRejected(f"snapshot fingerprint invalid: {exc}") from exc
    if snapshot.get("snapshot_id") != expected_hash:
        raise PublicationRejected(
            "snapshot_id does not match the deterministic fingerprint of the snapshot payload")


def load_artifacts(root: Any = ".") -> tuple[dict, dict, dict]:
    """Charge les trois artefacts depuis un repertoire. Leve PublicationRejected."""
    base = Path(root)
    loaded: list[dict] = []
    for name, relative in ARTIFACTS:
        path = base / relative
        if not path.exists() or path.stat().st_size == 0:
            raise PublicationRejected(f"Artifact missing or empty: {path}")
        try:
            loaded.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PublicationRejected(f"Artifact unreadable: {path} ({type(exc).__name__})") from exc
    return loaded[0], loaded[1], loaded[2]


def validate_paths(root: Any = ".", expected_collection_id: Optional[str] = None) -> dict:
    """Charge et valide les artefacts. Retourne le triplet valide."""
    if expected_collection_id is None:
        expected_collection_id = os.environ.get("COLLECTION_ID")
    snapshot, report, analysis = load_artifacts(root)
    validate_artifacts(snapshot, report, analysis, expected_collection_id)
    return {"snapshot": snapshot, "report": report, "analysis": analysis}


def main(argv: Optional[list] = None) -> int:
    """Point d'entree en ligne de commande. Retourne 0 si la publication est autorisee.

    Retourne 1 (et affiche la raison) si les artefacts ne peuvent pas etre
    publies : la porte est fail-closed, elle ne laisse jamais passer un
    artefact incoherent.
    """
    parser = argparse.ArgumentParser(description="Porte de publication (provenance)")
    parser.add_argument("--root", default=".", help="racine du depot")
    parser.add_argument("--collection-id", default=None,
                        help="identifiant de collecte attendu (defaut : variable COLLECTION_ID)")
    args = parser.parse_args(argv)
    try:
        validated = validate_paths(args.root, args.collection_id)
    except PublicationRejected as exc:
        print(f"PUBLICATION REFUSEE : {exc}")
        return 1
    print("provenance validation OK for collection",
          validated["snapshot"]["collection_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
