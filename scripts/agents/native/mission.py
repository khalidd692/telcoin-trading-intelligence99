#!/usr/bin/env python3
"""Bounded mission kernel for the TEL99 native runner.

This is the smallest engine that can run a *real* mission from a native command
of our own project, with an interchangeable provider and **no** Hermes Desktop,
Kilo Agent Manager or OpenHands Cloud at runtime.

The kernel enforces the owner's "safe" rules by construction:

  * **Fail-closed quota**: a real run refuses to start when the remaining free
    conversation quota is unknown or below the reserve (default 12). An unknown
    quota is never treated as sufficient.
  * **No double run**: a mission is idempotent on ``mission_id``. A completed
    mission is refused on re-launch; a *concurrent* second launch of the same
    id is refused by an atomic exclusive claim file, so two runners cannot both
    spend a provider call.
  * **Never trust the model**: the model only *produces* artifacts. The verdict
    (PASS / FAIL / NEEDS_HUMAN) comes from re-running deterministic acceptance
    checks on disk -- a model that writes "PASS" cannot make a failing check
    pass.
  * **Bounded**: a hard wall-clock deadline and a bounded number of provider
    calls; the first failed precondition aborts before any provider call.
  * **No secrets on disk**: only the model id and the decision journal are
    persisted, never the endpoint, the key or the request headers.
  * **Safe artifact paths**: ``mission_id`` and artifact names are validated so
    a mission can never write outside its own directory.

It reuses, and never re-implements:
  * ``intelligence.router``  -- the free/verified/quota model choice;
  * ``intelligence.memory``  -- versioned shared memory for recall + journal;
  * ``intelligence.catalog`` -- the declared model metadata;
  * ``protocol.store``       -- the durable, atomic key/value store.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

_AGENTS_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

from intelligence import memory, router  # noqa: E402
from protocol.store import FileStore  # noqa: E402

# Verdicts. ``NEEDS_HUMAN`` is the honest outcome when a check is not
# deterministically decidable; it is never collapsed into PASS.
PASS, FAIL, NEEDS_HUMAN = "PASS", "FAIL", "NEEDS_HUMAN"

# Minimum free conversations that must remain before a real launch (issue #86
# "safe night" policy: keep 10 of 20 in reserve).
MIN_QUOTA_REQUIRED = 12

# A mission id is a path segment: restrict it to a safe, bounded charset.
MISSION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

DEFAULT_DEADLINE_S = 120
MAX_PROVIDER_CALLS = 4

SYSTEM_PROMPT = (
    "Tu es un ouvrier logiciel TEL99 en environnement borne et en lecture seule "
    "vis-a-vis du depot. Produis uniquement les fichiers demandes, dans le "
    "dossier d'artefacts fourni. Ne propose aucun ordre financier, aucun "
    "deploiement, aucune fusion. Termine par une ligne 'VERDICT: PASS' ou "
    "'VERDICT: FAIL'."
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


class MissionError(RuntimeError):
    """A precondition failed. Fail-closed: no work is started."""


def valid_mission_id(mission_id: str) -> bool:
    return bool(mission_id) and bool(MISSION_ID_RE.match(mission_id))


def valid_artifact_name(name: str) -> bool:
    return bool(name) and bool(ARTIFACT_NAME_RE.match(name))


@dataclass
class Check:
    """One deterministic acceptance check, re-run by the kernel (not the model)."""

    name: str
    command: list[str]
    expect_exit: int = 0
    must_contain: str = ""

    def run(self, cwd: pathlib.Path, timeout: int = 60) -> dict:
        try:
            proc = subprocess.run(
                self.command, cwd=str(cwd), timeout=timeout,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"name": self.name, "ok": False, "exit": None,
                    "detail": f"check could not run: {type(exc).__name__}"}
        out = proc.stdout.decode(errors="ignore")
        ok = proc.returncode == self.expect_exit
        if ok and self.must_contain and self.must_contain not in out:
            ok = False
        return {"name": self.name, "ok": ok, "exit": proc.returncode,
                "detail": "" if ok else out.strip()[-400:]}


@dataclass
class MissionSpec:
    """A bounded mission: an id, a prompt, artifact names and acceptance checks."""

    mission_id: str
    prompt: str
    artifacts: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    project: str = "tel99"
    deadline_s: int = DEFAULT_DEADLINE_S

    def validate(self) -> None:
        if not valid_mission_id(self.mission_id):
            raise MissionError(f"unsafe mission_id: {self.mission_id!r}")
        for name in self.artifacts:
            if not valid_artifact_name(name):
                raise MissionError(f"unsafe artifact name: {name!r}")
        for check in self.checks:
            if not check.command or not isinstance(check.command, list):
                raise MissionError(f"check {check.name!r} has no command list")


@dataclass
class MissionResult:
    mission_id: str
    verdict: str
    chosen_model: str | None
    artifacts: list[str]
    checks: list[dict]
    provider_calls: int
    duration_s: float
    reasons: list[str]
    reused: bool = False

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "verdict": self.verdict,
            "chosen_model": self.chosen_model,
            "artifacts": self.artifacts,
            "checks": self.checks,
            "provider_calls": self.provider_calls,
            "duration_s": round(self.duration_s, 3),
            "reasons": self.reasons,
            "reused": self.reused,
        }


def decide_verdict(checks: list[dict]) -> str:
    """PASS only when at least one check ran and every check passed.

    A model's self-reported verdict is never an input here.
    """
    if not checks:
        return NEEDS_HUMAN
    return PASS if all(c.get("ok") for c in checks) else FAIL


class MissionEngine:
    """Run a bounded mission with an interchangeable provider."""

    def __init__(self, *, provider, store_root, workspace_root, memory_root,
                 quota_remaining, min_quota: int = MIN_QUOTA_REQUIRED,
                 dry_run: bool = False, now=time.monotonic) -> None:
        self.provider = provider
        self.store = FileStore(store_root)
        self.workspace_root = pathlib.Path(workspace_root)
        self.memory = memory.MemoryStore(memory_root)
        self.quota_remaining = quota_remaining
        self.min_quota = min_quota
        self.dry_run = dry_run
        self._now = now

    # -- preconditions ------------------------------------------------------
    def _check_quota(self) -> None:
        if self.dry_run:
            return
        if self.quota_remaining is None:
            raise MissionError("quota unknown: refusing to start a real run")
        if self.quota_remaining < self.min_quota:
            raise MissionError(
                f"quota too low: {self.quota_remaining} < {self.min_quota}"
            )

    def _claim(self, spec: MissionSpec) -> None:
        """Atomically reserve ``mission_id`` for this run.

        Create an exclusive claim file so a *concurrent* second launch of the
        same ``mission_id`` is refused instead of spending a second provider
        call. Callers must check for an existing record first (the idempotent
        no-op path). The claim is released by :meth:`_release_claim`, which
        ``run`` always calls in a ``finally`` block.
        """
        claim_dir = pathlib.Path(self.store.root) / "claims"
        claim_dir.mkdir(parents=True, exist_ok=True)
        claim = claim_dir / f"{spec.mission_id}.lock"
        try:
            fd = os.open(str(claim), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            raise MissionError(
                f"mission {spec.mission_id!r} is already claimed by another run"
            )
        os.close(fd)

    def _route(self, spec: MissionSpec) -> router.Decision:
        measured = router.load_measured_quality(
            str(pathlib.Path(self.memory.root) / "measured_quality.json")
        )
        task = router.TaskProfile(
            kind="code", description=spec.prompt[:200], touches_files=len(spec.artifacts),
            needs_tools=True, confidential=False, estimated_tokens=2000,
        )
        # In a dry run the router is allowed to propose an unverified model; a
        # real run additionally requires the operator's free-model allowlist to
        # vouch for the provider (the catalogue alone marks it unverified).
        return router.route(
            task, quota_remaining=self.quota_remaining, min_quota=self.min_quota,
            dry_run=True, measured_quality=measured,
        )

    def recall(self, query: str, limit: int = 3) -> list[dict]:
        return [e.to_dict() for e in
                self.memory.search("tel99", query, limit=limit)]

    # -- execution ----------------------------------------------------------
    def run(self, spec: MissionSpec) -> MissionResult:
        spec.validate()
        started = self._now()

        # Idempotency: a recorded mission is a no-op. Preconditions are checked
        # BEFORE the atomic claim so a refused run never leaks a claim file.
        previous = self.store.get(f"missions/{spec.mission_id}")
        if previous is not None:
            return MissionResult(
                mission_id=spec.mission_id, verdict=previous.get("verdict", NEEDS_HUMAN),
                chosen_model=previous.get("chosen_model"), artifacts=previous.get("artifacts", []),
                checks=previous.get("checks", []), provider_calls=0,
                duration_s=0.0, reused=True,
                reasons=["mission already recorded: idempotent no-op (no double run)"],
            )

        self._check_quota()
        decision = self._route(spec)
        chosen = decision.chosen.id if decision.chosen else None

        if self.dry_run:
            return MissionResult(
                mission_id=spec.mission_id, verdict=NEEDS_HUMAN, chosen_model=chosen,
                artifacts=[], checks=[], provider_calls=0,
                duration_s=self._now() - started, reused=False,
                reasons=["dry run: no provider call, no artifact written"],
            )

        # Atomic exclusive claim: refuse a concurrent second launch of the same
        # mission id before spending a provider call. The claim is released in
        # a finally block, so a Python exception (including KeyboardInterrupt)
        # never wedges the id. A SIGKILL or power loss can still leave a stale
        # lock, which an operator may remove after inspecting the state.
        self._claim(spec)
        try:
            return self._execute(spec, decision, chosen, started)
        finally:
            self._release_claim(spec)

    def _execute(self, spec: MissionSpec, decision, chosen, started) -> MissionResult:
        out_dir = self.workspace_root / spec.mission_id
        out_dir.mkdir(parents=True, exist_ok=True)

        calls = 0
        prompt = spec.prompt
        if spec.artifacts:
            prompt += ("\n\nProduis exactement ces fichiers dans le dossier courant: "
                       + ", ".join(spec.artifacts))
        while calls < MAX_PROVIDER_CALLS:
            if self._now() - started > spec.deadline_s:
                break
            try:
                text = self.provider.complete(system=SYSTEM_PROMPT, prompt=prompt)
            except Exception as exc:  # noqa: BLE001 - a provider failure is FAIL, not a crash
                calls += 1
                result = MissionResult(
                    mission_id=spec.mission_id, verdict=FAIL, chosen_model=chosen,
                    artifacts=[], checks=[], provider_calls=calls,
                    duration_s=self._now() - started, reused=False,
                    reasons=[f"provider error: {type(exc).__name__}"],
                )
                self._persist(spec, result, decision)
                return result
            calls += 1
            written = self._extract_artifacts(text, out_dir, spec.artifacts)
            if written or not spec.artifacts:
                break
            prompt += "\n\nIl manque des fichiers. Re-emets UNIQUEMENT les blocs demandes."

        # Deterministic verdict: re-run the acceptance checks on disk.
        check_results = [c.run(out_dir) for c in spec.checks]
        verdict = decide_verdict(check_results)
        result = MissionResult(
            mission_id=spec.mission_id, verdict=verdict, chosen_model=chosen,
            artifacts=[n for n in spec.artifacts
                       if (out_dir / n).is_file()],
            checks=check_results, provider_calls=calls,
            duration_s=self._now() - started, reused=False,
            reasons=decision.reasons,
        )
        self._persist(spec, result, decision, out_dir)
        return result

    def _release_claim(self, spec: MissionSpec) -> None:
        """Release the exclusive claim (idempotent; never raises).

        Called from ``run``'s ``finally``, so it must not mask the original
        exception: every failure mode is swallowed.
        """
        claim = pathlib.Path(self.store.root) / "claims" / f"{spec.mission_id}.lock"
        try:
            claim.unlink()
        except OSError:
            pass

    def _extract_artifacts(self, text: str, out_dir: pathlib.Path,
                           names: list[str]) -> list[str]:
        """Extract fenced ```name ...``` blocks into safe files under out_dir."""
        written: list[str] = []
        for match in re.finditer(r"```([A-Za-z0-9._-]+)\n(.*?)```", text, re.DOTALL):
            name, body = match.group(1), match.group(2)
            if names and name not in names:
                continue
            if not valid_artifact_name(name):
                continue
            target = (out_dir / name).resolve()
            if out_dir.resolve() not in target.parents and target != out_dir.resolve():
                continue
            target.write_text(body, encoding="utf-8")
            written.append(name)
        return written

    def _persist(self, spec: MissionSpec, result: MissionResult,
                 decision: router.Decision, out_dir: pathlib.Path | None = None) -> None:
        record = result.to_dict()
        record["recorded_at"] = utcnow_iso()
        record["decision"] = decision.to_dict()
        record["provider"] = getattr(self.provider, "name", "unknown")
        # Only the model id is stored -- never the endpoint, key or headers.
        self.store.put(f"missions/{spec.mission_id}", record)
        if out_dir is not None:
            (out_dir / "journal.json").write_text(
                json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        entry = memory.Entry(
            id=f"mission-{spec.mission_id}",
            project=spec.project,
            kind="procedure" if result.verdict == PASS else "error",
            title=f"Mission {spec.mission_id}: {result.verdict}",
            body=(f"verdict={result.verdict}; model={result.chosen_model}; "
                  f"checks={[c['name'] for c in result.checks]}; "
                  f"artifacts={result.artifacts}"),
            tags=("native", "mission", result.verdict.lower()),
            source="scripts/agents/native/mission.py",
            author="tel99-native",
            confidence=0.9 if result.verdict == PASS else 0.5,
        )
        self.memory.record(entry)
