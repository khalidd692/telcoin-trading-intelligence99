"""Bind the Windows supervisor's existing approval, claim and verdict to the agent bus."""

from __future__ import annotations

import hashlib
import json
import re

from protocol.bus import Bus
from protocol.envelope import Actor, Envelope, Evidence, validate
from protocol.handoff import Inbox
from protocol.store import CASConflict


class WindowsBus:
    def __init__(self, store):
        self.bus = Bus(store=store)
        self.inbox = Inbox("codex-windows", store=store)

    def _correlation(self, mission, approval):
        digest = hashlib.sha256(f"{mission['issue']}:{mission['id']}:{approval}".encode()).hexdigest()
        return f"msn-windows-{digest}"

    def _persist(self, envelope):
        data = envelope.to_dict()
        if validate(data):
            raise CASConflict("Invalid Windows bus envelope.")
        key = f"envelopes/{envelope.envelope_id}"
        if self.bus.store.put_cas(key, data, None):
            return
        existing = self.bus.store.get(key)
        if not isinstance(existing, dict) or any(
            existing.get(field) != value for field, value in data.items()
            if field not in {"created_at", "updated_at"}
        ):
            raise CASConflict("Conflicting Windows bus envelope.")

    def admit(self, mission, approval):
        """Emit REQUEST and durable ACK before letting the worker start."""
        correlation = self._correlation(mission, approval)
        target = Actor(environment="unknown", id="codex-windows", connected=True)
        request = Envelope.create(
            origin=Actor(environment="human", id="github-owner"),
            target=target, kind="mission", state="queued", mission_id=mission["id"],
            title=f"GitHub #{mission['issue']}", correlation_id=correlation,
            envelope_id=f"{correlation}-request", tags=["REQUEST"], read_only=False,
        )
        self._persist(request)
        delivery = self.inbox.receive({"request_id": request.envelope_id})
        if delivery["status"] != "ACK":
            raise CASConflict("Delivery needs reconciliation.")
        self._persist(Envelope.create(
            origin=target, kind="heartbeat", state="claimed",
            correlation_id=correlation, parent_envelope_id=request.envelope_id,
            envelope_id=f"{correlation}-ack", tags=["ACK"],
        ))
        return delivery["accepted"]

    def outcome(self, mission, checkpoint):
        """Record PREPARED as partial and independently accepted evidence separately."""
        claim = self.bus.store.get(f"claims/{mission['id']}")
        if not isinstance(claim, dict) or claim.get("issue") != mission.get("issue"):
            return
        approval = claim.get("approval")
        if not isinstance(approval, str) or not re.fullmatch(r"[0-9a-f]{64}", approval):
            return
        correlation = self._correlation(mission, approval)
        ack = self.bus.read_envelope(f"{correlation}-ack")
        if not ack:
            return  # Do not invent an ACK for historic deliveries.
        sha = checkpoint["commit"]
        if (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
                or ack.kind != "heartbeat" or ack.state != "claimed" or ack.tags != ["ACK"]
                or ack.correlation_id != correlation or ack.parent_envelope_id != f"{correlation}-request"):
            raise CASConflict("Invalid ACK or candidate commit for the Windows bus.")
        accepted = checkpoint["status"] == "ACCEPTED"
        proof = checkpoint.get("acceptance")
        if accepted and (not isinstance(proof, dict) or (
            proof.get("status"), proof.get("mission_id"), proof.get("commit_sha")
        ) != ("VERIFIED_EXTERNAL", mission["id"], sha)):
            raise CASConflict("Acceptance evidence does not match the bus result.")
        result_id = f"{correlation}-result"
        actor = Actor(environment="unknown", id="codex-windows", connected=True)
        self._persist(Envelope.create(
            origin=actor, kind="result", state="awaiting_human",
            correlation_id=correlation, parent_envelope_id=f"{correlation}-ack",
            envelope_id=result_id, tags=["RESULT", "PREPARED"],
            result={"status": "partial", "summary": f"PREPARED {sha}", "artifacts": []},
        ))
        if not accepted:
            return
        digest = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
        self._persist(Envelope.create(
            origin=actor, kind="evidence", state="done",
            correlation_id=correlation, parent_envelope_id=result_id,
            envelope_id=f"{correlation}-evidence", tags=["EVIDENCE", "ACCEPTED"],
            evidence=[Evidence(kind="external-verification", claim=f"ACCEPTED {sha}",
                               output_digest=digest, reproducible=True)],
        ))
