"""The first delivery profile and its independent acceptance contract."""

from __future__ import annotations

import hashlib
import pathlib
import subprocess

from . import sandbox
from .mission import Check, MissionError

ARTIFACTS = ("tasks.py", "README.md")
CONTRACT = """Crée un gestionnaire de tâches autonome en Python 3.12 (bibliothèque standard).
tasks.py accepte --db CHEMIN suivi d'une commande :
  add TITRE       crée une tâche et renvoie un objet JSON
  edit ID TITRE   modifie le titre et renvoie un objet JSON
  complete ID     termine la tâche et renvoie un objet JSON
  delete ID       supprime la tâche et renvoie un objet JSON
  list            renvoie un tableau JSON
Chaque tâche contient id (chaîne non vide), title (chaîne), done (booléen).
Stocke les changements dans le fichier indiqué par --db. Chaque invocation
est un processus distinct. Une base absente est vide et les bases choisies
par deux chemins différents sont indépendantes.
README.md explique comment démarrer et utiliser les cinq commandes.
Les tests indépendants sont fournis par le moteur. Ne génère aucun test pour
remplacer ces contrôles. Retourne les deux fichiers complets à chaque essai.
"""

_CASES = (
    "add creates a new open task",
    "list preserves the task across processes",
    "edit persists the new title",
    "complete persists the done flag",
    "different database stays isolated",
    "delete persists removal",
)
_RUNNER = """\
import json, subprocess, sys, uuid

db = "/scratch/" + uuid.uuid4().hex + ".json"
other = "/scratch/" + uuid.uuid4().hex + ".json"
title = uuid.uuid4().hex
edited = uuid.uuid4().hex

def call(path, *args):
    with subprocess.Popen(
        [sys.executable, "-I", "-B", "/work/program.py", "--db", path, *args],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ) as process:
        output = process.stdout.read(4097)
        if len(output) > 4096:
            process.kill()
            raise ValueError("output limit")
        if process.wait() != 0:
            raise ValueError("command exit status")
    return json.loads(output)

checks = [None] * 6
for index in range(len(checks)):
    try:
        if index == 0:
            created = call(db, "add", title)
            tid = created["id"]
            expected = {"id": tid, "title": title, "done": False}
            ok = (isinstance(tid, str) and 0 < len(tid) <= 128
                  and created == expected and created["done"] is False)
        elif index == 1:
            tasks = call(db, "list")
            ok = tasks == [expected] and tasks[0]["done"] is False
        elif index == 2:
            result = call(db, "edit", tid, edited)
            expected["title"] = edited
            tasks = call(db, "list")
            ok = (result == expected and result["done"] is False
                  and tasks == [expected] and tasks[0]["done"] is False)
        elif index == 3:
            result = call(db, "complete", tid)
            expected["done"] = True
            tasks = call(db, "list")
            ok = (result == expected and result["done"] is True
                  and tasks == [expected] and tasks[0]["done"] is True)
        elif index == 4:
            ok = call(other, "list") == []
        else:
            result = call(db, "delete", tid)
            ok = result == expected and result["done"] is True and call(db, "list") == []
        if not ok:
            raise ValueError("criterion not satisfied")
    except (ValueError, TypeError, KeyError, OSError, IndexError):
        print(index)
        sys.exit(1)
print("task-app: verified")
"""


class TaskAppCheck(Check):
    """Execute the candidate's CLI in separate processes and validate its state."""

    def __init__(self, image: str):
        if not sandbox.valid_image(image):
            raise MissionError("task profile requires a locally installed image pinned by sha256")
        super().__init__(name="task-app-acceptance", command=["python", "tasks.py"])
        self.image = image
        self.fingerprint = hashlib.sha256((image + "\n" + _RUNNER).encode()).hexdigest()

    def run(self, cwd: pathlib.Path, timeout: int = 60) -> dict:
        guide = (cwd / "README.md").read_text(encoding="utf-8")
        if "tasks.py" not in guide or not all(
                f" {command}" in guide
                for command in ("--db", "add", "list", "edit", "complete", "delete")):
            return {"name": self.name, "ok": False, "exit": 1,
                    "detail": "README must show how to use tasks.py and all five commands",
                    "repair_hint": "README must document tasks.py --db and all five commands"}
        return self.verify_file(cwd / "tasks.py", timeout)

    def verify_file(self, program: pathlib.Path, timeout: int = 60) -> dict:
        evidence = {"name": self.name, "sandbox_fingerprint": self.fingerprint,
                    "checks": list(_CASES)}
        try:
            if not program.is_file() or program.is_symlink():
                raise MissionError("missing task application")
            evidence["artifact_sha256"] = hashlib.sha256(program.read_bytes()).hexdigest()
            result = sandbox._run_container(self.image, program, timeout, runner=_RUNNER)
        except (MissionError, OSError, subprocess.TimeoutExpired, TimeoutError) as exc:
            return {**evidence, "ok": False, "exit": None, "infrastructure_error": True,
                    "detail": f"task app verification unavailable ({type(exc).__name__})"}
        if result.returncode == 0 and result.stdout == b"task-app: verified\n":
            return {**evidence, "ok": True, "exit": 0, "detail": ""}
        detail = "task app sandbox did not produce a verification result"
        failed = result.stdout.strip()
        if result.returncode == 1 and failed in tuple(str(i).encode() for i in range(len(_CASES))):
            detail = _CASES[int(failed)]
            evidence["repair_hint"] = detail
        return {**evidence, "ok": False, "exit": result.returncode, "detail": detail,
                "infrastructure_error": "repair_hint" not in evidence}
