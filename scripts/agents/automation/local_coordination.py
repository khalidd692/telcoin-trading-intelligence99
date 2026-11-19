"""Windows binding to the existing TEL99 CAS lease and GitHub verifier."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from uuid import uuid4

import acceptance
import g3_bot_acceptance
import orchestrator
from protocol.store import KvStore, StoreError, kv_env
from upstash_coordination import RedisLease, RedisRest, RedisUnavailable


class CoordinationUnavailable(RuntimeError):
    pass


G3_POLICY_SHA = "f74741b38b8ea56ba28b0d0dbc9ba80bdef65afd4c0be4fe9aeb49d1beb6768a"
G3_TASK = "CODEX110-WINDOWS-NATIVE-SHORTPATH"


def g3_policy():
    path = Path(__file__).resolve().parents[3] / "docs/agents/G3_AUTO_TRUST_114.json"
    # Hash the policy's Git LF representation across Windows/Linux checkouts.
    # Candidate artefact bytes are verified exactly and never normalized.
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != G3_POLICY_SHA:
        raise ValueError("Politique d'acceptation #114 divergente.")
    return json.loads(raw)


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

    def update(self, key, new_value, expected, *, owner):
        try:
            return self.store.put_cas(key, new_value, expected)
        except (StoreError, OSError, ValueError) as exc:
            raise CoordinationUnavailable("Écriture CAS partagée indisponible.") from exc

    def read(self, key):
        try:
            return self.store.get(key)
        except (StoreError, OSError, ValueError) as exc:
            raise CoordinationUnavailable("Lecture de la réservation partagée impossible.") from exc

    def acquire(self, owner):
        acquired, _ = orchestrator.acquire_lock(owner)
        return acquired

    def release(self, owner):
        orchestrator.release_lock(owner)

    def shared_state(self):
        return orchestrator.kv_get(orchestrator._STATE_KEY)

    @contextmanager
    def claim(self, task_id, issue_number, approval):
        owner = f"codex-windows-{uuid4().hex}"
        try:
            acquired = self.acquire(owner)
        except Exception as exc:
            raise CoordinationUnavailable("La prise CAS de #94 est indisponible.") from exc
        if not acquired:
            raise CoordinationUnavailable("Le verrou partagé de #94 est occupé ou indisponible.")
        safe_to_release = True
        try:
            self.owns(owner)
            try:
                cloud = self.shared_state()
            except (OSError, ValueError, KeyError) as exc:
                raise CoordinationUnavailable("Lecture de l’état partagé impossible.") from exc
            if not isinstance(cloud, dict) or "active" not in cloud or cloud["active"] is not None:
                raise CoordinationUnavailable("L’état partagé de #94 est absent ou une mission est active.")
            key = f"codex-windows/{task_id}"
            claim = {"id": task_id, "issue": issue_number, "approval": approval,
                     "owner": owner, "status": "CLAIMED"}
            if not self.update(key, claim, None, owner=owner):
                raise CoordinationUnavailable("Une réservation durable existe déjà pour cette mission.")
            safe_to_release = False

            def finish(status, commit=None):
                nonlocal safe_to_release
                self.owns(owner)
                terminal = {**claim, "status": status, "commit": commit}
                if not self.update(key, terminal, claim, owner=owner):
                    raise CoordinationUnavailable("La réservation partagée a changé.")
                safe_to_release = True

            yield owner, finish
        finally:
            if safe_to_release:
                self.release(owner)

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
            if not self.update(key, terminal, claim, owner=owner):
                raise CoordinationUnavailable("La réservation partagée a changé.")
            self.release(owner)

        return current, finish


class UpstashCoordination(SharedCoordination):
    """CAS for the Windows ticket lane, with no legacy-service fallback."""

    def __init__(self, url, token):
        try:
            self.store = RedisLease(RedisRest(url, token))
        except RedisUnavailable as exc:
            raise CoordinationUnavailable(str(exc)) from exc

    def acquire(self, owner):
        return self.store.acquire(owner, ttl_ms=1_800_000)

    def release(self, owner):
        self._run(self.store.release, owner)

    def owns(self, owner):
        if not self._run(self.store.owns, owner):
            raise CoordinationUnavailable("Le verrou Redis a changé ou expiré.")

    def update(self, key, new_value, expected, *, owner):
        return self._run(self.store.put_cas, key, new_value, expected, owner=owner)

    def read(self, key):
        return self._run(self.store.read, key)

    def shared_state(self):
        state = self.read("state")
        return {"active": None} if state is None else state

    def promote_prepared(self, task_id, issue, approval, commit, verify):
        """Reconcile the existing reservation under a fresh fenced lease, with no worker."""
        owner = f"codex-windows-{uuid4().hex}"
        if not self.acquire(owner):
            raise CoordinationUnavailable("Le verrou partagé est occupé.")
        try:
            state = self.shared_state()
            if not isinstance(state, dict) or "active" not in state or state["active"] is not None:
                raise CoordinationUnavailable("Une mission active empêche la réconciliation.")
            key = f"codex-windows/{task_id}"
            current = self.read(key)
            original_owner = current.get("owner") if isinstance(current, dict) else None
            if not isinstance(original_owner, str) or not re.fullmatch(r"codex-windows-[0-9a-f]{32}", original_owner):
                raise CoordinationUnavailable("Réservation PREPARED absente ou invalide.")
            prepared = {"id": task_id, "issue": issue, "approval": approval, "commit": commit,
                        "owner": original_owner, "status": "PREPARED"}
            if current != prepared and current != {**prepared, "status": "ACCEPTED",
                                                    "evidence": current.get("evidence")}:
                raise CoordinationUnavailable("La réservation ne correspond pas au checkpoint.")
            proof = verify(current["status"] == "PREPARED")
            if not isinstance(proof, dict) or (
                proof.get("status"), proof.get("mission_id"), proof.get("commit_sha")
            ) != ("VERIFIED_EXTERNAL", task_id, commit):
                raise CoordinationUnavailable("Preuve externe indépendante absente ou invalide.")
            accepted = {**prepared, "status": "ACCEPTED", "evidence": proof}
            if current == accepted:
                return current
            if current != prepared or not self.update(key, accepted, prepared, owner=owner):
                raise CoordinationUnavailable("Écriture d'acceptation refusée par le CAS.")
            return accepted
        finally:
            self.release(owner)

    def _run(self, op, *args, **kwargs):
        try:
            return op(*args, **kwargs)
        except (RedisUnavailable, OSError, ValueError) as exc:
            raise CoordinationUnavailable("Le CAS Redis est indisponible.") from exc

    def probe(self):
        """Exercise the real endpoint in a unique, disposable key namespace."""
        namespace = "{tel99-94-probe-" + uuid4().hex + "}"
        left, right = (RedisLease(self.store.transport.fork(), namespace) for _ in range(2))
        record = {"version": 1}
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                wins = list(pool.map(lambda item: item[0].acquire(item[1], 60_000),
                                     [(left, "left"), (right, "right")]))
            if sum(wins) != 1:
                raise CoordinationUnavailable("Le CAS de précontrôle n’a pas un gagnant unique.")
            winner, loser = ("left", "right") if wins[0] else ("right", "left")
            checks = (
                left.put_cas("claim", record, None, owner=winner),
                not right.put_cas("claim", {"version": 2}, record, owner=loser),
                not right.release(loser),
                left.release(winner),
                right.acquire(loser, 60_000),
                not left.put_cas("claim", {"version": 2}, record, owner=winner),
                not right.put_cas("claim", {"version": 2}, None, owner=loser),
                right.put_cas("claim", {"version": 2}, record, owner=loser),
                left.read("claim") == {"version": 2},
            )
            if not all(checks):
                raise CoordinationUnavailable("Le précontrôle Redis CAS/fencing a échoué.")
            self.store.transport.command("DEL", left.key("claim"), left.key("active_mission_lock"))
        except (RedisUnavailable, OSError, ValueError) as exc:
            raise CoordinationUnavailable("Le précontrôle Redis REST a échoué.") from exc


def coordination_backend():
    url = os.environ.get("TEL99_UPSTASH_REST_URL", "")
    token = os.environ.get("TEL99_UPSTASH_REST_TOKEN", "")
    free = os.environ.get("TEL99_UPSTASH_FREE", "")
    if url or token or free:
        if free != "1" or any(kv_env()):
            raise CoordinationUnavailable("Exiger Upstash Free confirmé et un seul backend KV.")
        return UpstashCoordination(url, token)
    return SharedCoordination()


def accepted_proof(descriptor, *, repository, mission_body, fetch, comments):
    """Require verified, immutable, mission-scoped proof; never trust an LLM verdict."""
    if descriptor.get("verification_mode") == "g3-bot-v1":
        # The original #104 acceptance verifier is unchanged. This explicitly
        # enabled alternative is only for the owner's pinned, synthetic #114.
        try:
            if descriptor.get("policy_sha256") != G3_POLICY_SHA:
                return None
            policy = g3_policy()
            required = ("issue", "mission_id", "work_branch", "commit_sha", "criteria")
            if (descriptor.get("issue") != 114
                    or not all(descriptor.get(key) == policy.get(key) for key in required)
                    or policy.get("schema_version") != 1):
                return None
            return g3_bot_acceptance.verify(
                policy=policy, comments=comments, repository=repository, fetch=fetch,
            )
        except (OSError, ValueError, TypeError, KeyError):
            return None
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
