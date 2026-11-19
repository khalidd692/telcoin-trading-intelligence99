#!/usr/bin/env python3
"""Kilo G5 Amélioration contrôlée — garde-fous et rollback sans git reset --hard.

Fournit :
  * un registre des changements (changelog) avec SHA-256 de chaque version
  * une fonction de rollback qui restaure un état précédent par copie de fichier
    (jamais `git reset --hard`, qui détruirait l'historique)
  * une validation pré-application (garde-fous) : un changement ne s'applique
    que si le SHA-256 du fichier cible correspond à l'état attendu
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]  # scripts/kilocli -> scripts -> root
CHANGELOG_DIR = ROOT / ".kilo" / "changelog"
BACKUP_DIR = ROOT / ".kilo" / "backups"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return "sha256:" + h.hexdigest()


class ChangeRegistry:
    """Registre des changements applicables avec garde-fous SHA-256."""

    def __init__(self, root: pathlib.Path | None = None) -> None:
        self.root = pathlib.Path(root or ROOT)
        self.changelog_dir = self.root / ".kilo" / "changelog"
        self.backup_dir = self.root / ".kilo" / "backups"
        self.changelog_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def record_change(self, change_id: str, file_path: pathlib.Path,
                      old_sha: str, new_sha: str, description: str,
                      author: str = "KILO-INTEGRATOR") -> None:
        """Enregistre un changement dans le changelog."""
        entry = {
            "change_id": change_id,
            "file": str(pathlib.Path(file_path).resolve().relative_to(self.root)),
            "old_sha256": old_sha,
            "new_sha256": new_sha,
            "description": description,
            "author": author,
            "applied_at": _now_iso(),
            "status": "applied",
        }
        path = self.changelog_dir / f"{change_id}.json"
        path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    def verify_before_apply(self, file_path: pathlib.Path,
                            expected_sha: str) -> tuple[bool, str]:
        """Garde-fous : vérifie que le fichier actuel correspond à l'état attendu."""
        if not file_path.is_file():
            return False, f"fichier introuvable: {file_path}"
        actual = sha256_file(file_path)
        if actual != expected_sha:
            return False, (f"SHA-256 mismatch: attendu {expected_sha}, "
                           f"actuel {actual} — le fichier a été modifié, abandon")
        return True, "SHA-256 conforme, application autorisée"

    def backup(self, file_path: pathlib.Path, change_id: str) -> pathlib.Path:
        """Sauvegarde une copie du fichier avant modification."""
        dest = self.backup_dir / f"{change_id}_{file_path.name}"
        shutil.copy2(file_path, dest)
        return dest

    def rollback(self, change_id: str) -> tuple[bool, str]:
        """Restaure un fichier à son état avant un changement donné.

        Jamais `git reset --hard` : on recopie la sauvegarde sur le fichier
        actuel, préservant l'historique git.
        """
        entry_path = self.changelog_dir / f"{change_id}.json"
        if not entry_path.is_file():
            return False, f"changement introuvable: {change_id}"
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        file_rel = entry["file"]
        file_path = (self.root / file_rel).resolve()
        backup_name = f"{change_id}_{pathlib.Path(file_rel).name}"
        backup_path = self.backup_dir / backup_name
        if not backup_path.is_file():
            return False, f"sauvegarde introuvable: {backup_path}"
        # Vérifier que le fichier actuel correspond au new_sha (garde-fous)
        if file_path.is_file():
            actual = sha256_file(file_path)
            if actual != entry["new_sha256"]:
                return False, (f"SHA-256 du fichier actuel ({actual}) ne "
                               f"correspond pas à new_sha256 ({entry['new_sha256']}) — "
                               f"rollback abandonné")
        # Restaurer la sauvegarde
        shutil.copy2(backup_path, file_path)
        entry["status"] = "rolled_back"
        entry["rolled_back_at"] = _now_iso()
        entry_path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
        return True, f"rollback effectué: {file_rel} restauré depuis {backup_path}"


def apply_change_with_guard(file_path: pathlib.Path, new_content: str,
                            change_id: str, description: str,
                            registry: ChangeRegistry | None = None) -> tuple[bool, str]:
    """Applique un changement avec garde-fous SHA-256 et sauvegarde préalable.

    Retourne (ok, message).
    """
    registry = registry or ChangeRegistry()
    file_path = pathlib.Path(file_path).resolve()

    if file_path.is_file():
        old_sha = sha256_file(file_path)
    else:
        old_sha = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # vide

    ok, msg = registry.verify_before_apply(file_path, old_sha)
    if not ok:
        return False, msg

    # Sauvegarde avant modification
    backup_path = registry.backup(file_path, change_id)

    # Écrire le nouveau contenu
    tmp = file_path.with_suffix(file_path.suffix + ".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    tmp.replace(file_path)

    new_sha = sha256_file(file_path)
    registry.record_change(change_id, file_path, old_sha, new_sha, description)
    return True, f"changement appliqué: {file_path} (sha={new_sha})"


def _cmd_apply(args, registry):
    new_content = pathlib.Path(args.content_file).read_text(encoding="utf-8")
    ok, msg = apply_change_with_guard(
        pathlib.Path(args.file), new_content, args.change_id, args.description,
        registry=registry)
    print(msg)
    raise SystemExit(0 if ok else 1)


def _cmd_rollback(args, registry):
    ok, msg = registry.rollback(args.change_id)
    print(msg)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kilo G5 — amélioration contrôlée et rollback")
    sub = parser.add_subparsers(dest="command", required=True)

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--file", required=True)
    p_apply.add_argument("--content-file", required=True, help="fichier contenant le nouveau contenu")
    p_apply.add_argument("--change-id", required=True)
    p_apply.add_argument("--description", required=True)
    p_apply.set_defaults(func=lambda args: _cmd_apply(args, registry))

    p_rollback = sub.add_parser("rollback")
    p_rollback.add_argument("--change-id", required=True)
    p_rollback.set_defaults(func=lambda args: _cmd_rollback(args, registry))

    args = parser.parse_args()
    registry = ChangeRegistry()
    args.func(args)
