"""Windows binding to the existing TEL99 CAS lease and GitHub verifier."""

from contextlib import contextmanager
from urllib.parse import urlsplit
from uuid import uuid4

import acceptance
import orchestrator
from protocol.store import KvStore, StoreError, kv_env


class CoordinationUnavailable(RuntimeError):
    pass


class SharedCoordination:
    def __init__(self):
        base, token = kv_env()
        address = urlsplit(base)
        if not token or address.scheme != "https" or not address.hostname or address.username:
            raise CoordinationUnavailable("Le service KV partagé de #94 est indisponible.")
        self.store = KvStore(base, token)

    def probe(self):
        try:
            orchestrator.kv_get_meta(orchestrator._LOCK_KEY)
            state = orchestrator.kv_get(orchestrator._STATE_KEY)
        except Exception as exc:
            raise CoordinationUnavailable("Lecture des métadonnées CAS partagées impossible.") from exc
        if not isinstance(state, dict) or "active" not in state:
            raise CoordinationUnavailable("Le registre partagé de #94 est absent.")

    def owns(self, owner):
        try:
            lock = orchestrator.kv_get(orchestrator._LOCK_KEY)
        except (OSError, ValueError, KeyError) as exc:
            raise CoordinationUnavailable("Lecture du verrou partagé impossible.") from exc
        if (
            not isinstance(lock, dict) or lock.get("owner") != owner
            or not orchestrator._lock_held(lock)
        ):
            raise CoordinationUnavailable("Le verrou partagé de #94 a changé.")

    def update(self, key, new_value, expected):
        try:
            return self.store.put_cas(key, new_value, expected)
        except (StoreError, OSError, ValueError) as exc:
            raise CoordinationUnavailable("Écriture CAS partagée indisponible.") from exc

    def read(self, key):
        try:
            return self.store.get(key)
        except (StoreError, OSError, ValueError) as exc:
            raise CoordinationUnavailable("Lecture de la réservation partagée impossible.") from exc

    @contextmanager
    def claim(self, task_id, issue_number, approval):
        owner = f"codex-windows-{uuid4().hex}"
        try:
            acquired, _ = orchestrator.acquire_lock(owner)
        except Exception as exc:
            raise CoordinationUnavailable("La prise CAS de #94 est indisponible.") from exc
        if not acquired:
            raise CoordinationUnavailable("Le verrou partagé de #94 est occupé ou indisponible.")
        safe_to_release = True
        try:
            self.owns(owner)
            try:
                cloud = orchestrator.kv_get(orchestrator._STATE_KEY)
            except (OSError, ValueError, KeyError) as exc:
                raise CoordinationUnavailable("Lecture de l’état partagé impossible.") from exc
            if not isinstance(cloud, dict) or "active" not in cloud or cloud["active"] is not None:
                raise CoordinationUnavailable("L’état partagé de #94 est absent ou une mission est active.")
            key = f"codex-windows/{task_id}"
            claim = {"id": task_id, "issue": issue_number, "approval": approval,
                     "owner": owner, "status": "CLAIMED"}
            if not self.update(key, claim, None):
                raise CoordinationUnavailable("Une réservation durable existe déjà pour cette mission.")
            safe_to_release = False

            def finish(status, commit=None):
                nonlocal safe_to_release
                self.owns(owner)
                terminal = {**claim, "status": status, "commit": commit}
                if not self.update(key, terminal, claim):
                    raise CoordinationUnavailable("La réservation partagée a changé.")
                safe_to_release = True

            yield owner, finish
        finally:
            if safe_to_release:
                orchestrator.release_lock(owner)

    def resume(self, task_id, issue_number, approval, owner):
        key = f"codex-windows/{task_id}"
        claim = {"id": task_id, "issue": issue_number, "approval": approval,
                 "owner": owner, "status": "CLAIMED"}
        current = self.read(key)
        if current != claim and not (
            isinstance(current, dict)
            and current == {**claim, "status": "PREPARED", "commit": current.get("commit")}
        ):
            raise CoordinationUnavailable("Réservation distante incohérente avec le checkpoint.")

        def finish(status, commit=None):
            terminal = {**claim, "status": status, "commit": commit}
            if current == terminal:
                return
            self.owns(owner)
            if not self.update(key, terminal, claim):
                raise CoordinationUnavailable("La réservation partagée a changé.")
            orchestrator.release_lock(owner)

        return current, finish


def accepted_proof(descriptor, *, repository, mission_body, fetch, comments):
    """A PASS exists only when #104 independently checks every pinned criterion."""
    checks = [{"id": item, "automatable": True} for item in descriptor["criteria"]]
    verdicts, proof = acceptance.verify(
        comments=comments, verifiers=set(descriptor["verifiers"]),
        conversation_id=descriptor["conversation_id"],
        mission_digest=descriptor["mission_digest"], mission_body=mission_body,
        repository=repository, work_branch=descriptor["work_branch"],
        checks=checks, trusted_workflows=descriptor["trusted_workflows"], fetch=fetch,
    )
    if not proof or proof.get("commit_sha") != descriptor["commit_sha"]:
        return None
    if {item.get("id") for item in verdicts} != {item["id"] for item in checks}:
        return None
    if not checks or not all(item.get("exit_code") == 0 for item in verdicts):
        return None
    return proof
