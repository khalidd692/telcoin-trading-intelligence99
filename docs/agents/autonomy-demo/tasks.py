#!/usr/bin/env python3
"""Gestionnaire de tâches autonome en Python 3.12 (stdlib uniquement)."""

import argparse
import json
import os
import sys
import uuid


def load_tasks(db_path: str) -> list[dict]:
    """Charge les tâches depuis le fichier JSON, ou retourne une liste vide si absent."""
    if not os.path.exists(db_path):
        return []
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []
            return data
    except (json.JSONDecodeError, OSError):
        return []


def save_tasks(db_path: str, tasks: list[dict]) -> None:
    """Sauvegarde les tâches dans le fichier JSON."""
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)


def find_task_index(tasks: list[dict], task_id: str) -> int | None:
    """Retourne l'index de la tâche avec l'ID donné, ou None si introuvable."""
    for i, task in enumerate(tasks):
        if isinstance(task, dict) and "id" in task and task["id"] == task_id:
            return i
    return None


def cmd_add(db_path: str, title: str) -> None:
    tasks = load_tasks(db_path)
    new_task = {"id": str(uuid.uuid4()), "title": title, "done": False}
    tasks.append(new_task)
    save_tasks(db_path, tasks)
    print(json.dumps(new_task, ensure_ascii=False))


def cmd_edit(db_path: str, task_id: str, title: str) -> None:
    tasks = load_tasks(db_path)
    idx = find_task_index(tasks, task_id)
    if idx is None:
        print(json.dumps({"error": "Task not found"}, ensure_ascii=False))
        sys.exit(1)
    tasks[idx]["title"] = title
    save_tasks(db_path, tasks)
    print(json.dumps(tasks[idx], ensure_ascii=False))


def cmd_complete(db_path: str, task_id: str) -> None:
    tasks = load_tasks(db_path)
    idx = find_task_index(tasks, task_id)
    if idx is None:
        print(json.dumps({"error": "Task not found"}, ensure_ascii=False))
        sys.exit(1)
    tasks[idx]["done"] = True
    save_tasks(db_path, tasks)
    print(json.dumps(tasks[idx], ensure_ascii=False))


def cmd_delete(db_path: str, task_id: str) -> None:
    tasks = load_tasks(db_path)
    idx = find_task_index(tasks, task_id)
    if idx is None:
        print(json.dumps({"error": "Task not found"}, ensure_ascii=False))
        sys.exit(1)
    deleted = tasks.pop(idx)
    save_tasks(db_path, tasks)
    print(json.dumps(deleted, ensure_ascii=False))


def cmd_list(db_path: str) -> None:
    tasks = load_tasks(db_path)
    print(json.dumps(tasks, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestionnaire de tâches")
    parser.add_argument("--db", required=True, help="Chemin vers le fichier JSON de la base")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_add = subparsers.add_parser("add", help="Ajouter une tâche")
    parser_add.add_argument("title", help="Titre de la tâche")

    parser_edit = subparsers.add_parser("edit", help="Modifier une tâche")
    parser_edit.add_argument("id", help="ID de la tâche")
    parser_edit.add_argument("title", help="Nouveau titre")

    parser_complete = subparsers.add_parser("complete", help="Marquer une tâche comme terminée")
    parser_complete.add_argument("id", help="ID de la tâche")

    parser_delete = subparsers.add_parser("delete", help="Supprimer une tâche")
    parser_delete.add_argument("id", help="ID de la tâche")

    subparsers.add_parser("list", help="Lister toutes les tâches")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args.db, args.title)
    elif args.command == "edit":
        cmd_edit(args.db, args.id, args.title)
    elif args.command == "complete":
        cmd_complete(args.db, args.id)
    elif args.command == "delete":
        cmd_delete(args.db, args.id)
    elif args.command == "list":
        cmd_list(args.db)


if __name__ == "__main__":
    main()
