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

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
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
ARTIFACT_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_WINDOWS_DEVICE = re.compile(r"con|prn|aux|nul|com[1-9]|lpt[1-9]", re.IGNORECASE)

DEFAULT_PROJECT = "tel99"
PROJECT_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

DEFAULT_DEADLINE_S = 120
MAX_PROVIDER_CALLS = 4

SYSTEM_PROMPT = (
    "Tu es un ouvrier logiciel TEL99 en environnement borne et en lecture seule "
    "vis-a-vis du depot. Produis uniquement les fichiers demandes, dans le "
    "dossier d'artefacts fourni. Ne propose aucun ordre financier, aucun "
    "deploiement, aucune fusion. Retourne un bloc de code clôturé pour chaque "
    "fichier, avec son nom exact après les trois accents graves."
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


class MissionError(RuntimeError):
    """A precondition failed. Fail-closed: no work is started."""


def valid_mission_id(mission_id: str) -> bool:
    return bool(MISSION_ID_RE.fullmatch(mission_id)) and valid_artifact_name(mission_id)


def valid_artifact_name(name: str) -> bool:
    return (bool(ARTIFACT_NAME_RE.fullmatch(name)) and not name.endswith(".")
            and not _WINDOWS_DEVICE.fullmatch(name.split(".", 1)[0]))


def validate_project(project: str) -> None:
    if (not isinstance(project, str) or len(project) > 64
            or not PROJECT_RE.fullmatch(project) or not valid_artifact_name(project)
            or project == memory.COMMON_PROJECT):
        raise MissionError(f"invalid project name: {project!r}")


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
    project: str = DEFAULT_PROJECT
    deadline_s: int = DEFAULT_DEADLINE_S
    max_repairs: int | None = None

    def validate(self) -> None:
        validate_project(self.project)
        if (self.max_repairs is not None and
                (type(self.max_repairs) is not int or not 0 <= self.max_repairs < MAX_PROVIDER_CALLS)):
            raise MissionError("invalid repair budget")
        if len({name.lower() for name in self.artifacts}) != len(self.artifacts):
            raise MissionError("artifact names must be unique")
        if not valid_mission_id(self.mission_id):
            raise MissionError(f"unsafe mission_id: {self.mission_id!r}")
        for name in self.artifacts:
            if not valid_artifact_name(name) or name.lower() == "journal.json":
                raise MissionError(f"unsafe artifact name: {name!r}")
        for check in self.checks:
            if not check.command or not isinstance(check.command, list):
                raise MissionError(f"check {check.name!r} has no command list")


def _contract_sha256(spec: MissionSpec) -> str | None:
    checks = []
    for check in spec.checks:
        pinned = getattr(check, "fingerprint", None)
        if type(check) is not Check and (not isinstance(pinned, str) or not pinned):
            return None
        checks.append({"type": type(check).__qualname__, "name": check.name,
                       "command": check.command, "exit": check.expect_exit,
                       "stdout": check.must_contain, "pinned": pinned})
    data = {"project": spec.project, "id": spec.mission_id, "prompt": spec.prompt,
            "artifacts": spec.artifacts, "checks": checks, "deadline": spec.deadline_s,
            "max_repairs": spec.max_repairs}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _repair_artifacts(directory: pathlib.Path, written: list[str]) -> str:
    remaining = 4000
    snippets = {}
    for name in written:
        path = directory / name
        if path.is_symlink() or not path.is_file() or remaining == 0:
            continue
        with path.open(encoding="utf-8", errors="replace") as file:
            snippets[name] = file.read(remaining)
        remaining -= len(snippets[name])
    return json.dumps(snippets, ensure_ascii=False)


def _mission_path(spec: MissionSpec) -> pathlib.Path:
    if spec.project == DEFAULT_PROJECT:
        return pathlib.Path(spec.mission_id)
    return pathlib.Path("_projects", spec.project, spec.mission_id)


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
    attempts: list[dict] = field(default_factory=list)
    artifact_digests: dict[str, str] = field(default_factory=dict)
    provider: str | None = None

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
            "attempts": self.attempts,
            "artifact_digests": self.artifact_digests,
            "provider": self.provider,
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
        if (type(self.quota_remaining) is not int or type(self.min_quota) is not int
                or self.min_quota < 1):
            raise MissionError("quota unknown or invalid: refusing to start a real run")
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
        claim = self.store.root / "claims" / f"{_mission_path(spec)}.lock"
        claim.parent.mkdir(parents=True, exist_ok=True)
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

    def artifact_directory(self, spec: MissionSpec) -> pathlib.Path:
        return self.workspace_root / _mission_path(spec)

    def record_for(self, spec: MissionSpec) -> dict | None:
        spec.validate()
        record = self.store.get(f"missions/{_mission_path(spec).as_posix()}")
        if record is not None:
            return record
        directory = self.artifact_directory(spec)
        journal = directory / "journal.json"
        if (directory.resolve() != self.workspace_root.resolve() / _mission_path(spec)
                or journal.is_symlink() or not journal.is_file()):
            return None
        try:
            record = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if (isinstance(record, dict) and record.get("mission_id") == spec.mission_id
                and record.get("project") == spec.project):
            return record
        return None

    def artifacts_match(self, spec: MissionSpec, digests: dict) -> bool:
        out_dir = self.artifact_directory(spec)
        if out_dir.resolve() != self.workspace_root.resolve() / _mission_path(spec):
            return False
        for name, digest in digests.items():
            artifact = out_dir / name
            if (not valid_artifact_name(name) or artifact.is_symlink()
                    or not artifact.is_file()
                    or hashlib.sha256(artifact.read_bytes()).hexdigest() != digest):
                return False
        return True

    def recall(self, query: str, limit: int = 3, *,
               project: str = DEFAULT_PROJECT) -> list[dict]:
        validate_project(project)
        return [e.to_dict() for e in self.memory.search(project, query, limit=limit)]

    # -- execution ----------------------------------------------------------
    def run(self, spec: MissionSpec) -> MissionResult:
        spec.validate()
        started = self._now()

        # Idempotency: a recorded mission is a no-op. Preconditions are checked
        # BEFORE the atomic claim so a refused run never leaks a claim file.
        previous = self.record_for(spec)
        if previous is not None:
            contract_sha = _contract_sha256(spec)
            if contract_sha is None or previous.get("contract_sha256") != contract_sha:
                raise MissionError("cached mission contract differs or lacks a verifiable fingerprint")
            digests = previous.get("artifact_digests", {})
            if previous.get("verdict") == PASS and (
                    not isinstance(digests, dict) or set(digests) != set(spec.artifacts)
                    or not self.artifacts_match(spec, digests)):
                raise MissionError("cached artifacts differ from the verified run")
            return MissionResult(
                mission_id=spec.mission_id, verdict=previous.get("verdict", NEEDS_HUMAN),
                chosen_model=previous.get("chosen_model"), artifacts=previous.get("artifacts", []),
                checks=previous.get("checks", []), provider_calls=0,
                duration_s=0.0, reused=True, attempts=previous.get("attempts", []),
                artifact_digests=digests, provider=previous.get("provider"),
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
            return self._execute(spec, decision, getattr(self.provider, "model", None), started)
        finally:
            self._release_claim(spec)

    def _execute(self, spec: MissionSpec, decision, chosen, started) -> MissionResult:
        out_dir = self.artifact_directory(spec)
        if out_dir.resolve() != self.workspace_root.resolve() / _mission_path(spec):
            raise MissionError("mission workspace is linked outside its declared path")
        if out_dir.exists():
            raise MissionError("mission artifact directory already exists without a journal record")
        out_dir.parent.mkdir(parents=True, exist_ok=True)

        request = spec.prompt
        if spec.artifacts:
            request += "\n\nProduis exactement ces fichiers: " + ", ".join(spec.artifacts)
        feedback = ""
        attempts = []
        reasons = list(decision.reasons)
        allowed_attempts = (MAX_PROVIDER_CALLS if spec.max_repairs is None
                            else spec.max_repairs + 1)
        call_limit = min(allowed_attempts, self.quota_remaining - self.min_quota + 1)

        with tempfile.TemporaryDirectory(prefix=".attempts-", dir=out_dir.parent) as staging:
            stage = pathlib.Path(staging)
            last = None
            written = []
            check_results = []
            verdict = FAIL
            for index in range(call_limit):
                if self._now() - started >= spec.deadline_s:
                    reasons.append("mission deadline reached")
                    break

                try:
                    reply = self.provider.complete(system=SYSTEM_PROMPT, prompt=request + feedback)
                    if not isinstance(reply, str):
                        raise TypeError("provider completion must be text")
                except Exception as exc:  # A provider exception may contain credentials.
                    reasons.insert(0, f"provider error: {type(exc).__name__}")
                    attempts.append({"attempt": index + 1, "verdict": FAIL,
                                     "error": type(exc).__name__})
                    verdict = FAIL
                    break

                provider_evidence = getattr(self.provider, "last_completion_evidence", None)
                last = stage / str(index + 1)
                last.mkdir()
                written = self._extract_artifacts(reply, last, spec.artifacts)
                missing = [name for name in spec.artifacts if name not in written]
                check_results = []
                if not missing:
                    for check in spec.checks:
                        remaining = spec.deadline_s - (self._now() - started)
                        if remaining <= 0:
                            check_results.append({"name": check.name, "ok": False,
                                                  "detail": "mission deadline reached"})
                            break
                        check_results.append(check.run(last, timeout=min(60, max(1, int(remaining)))))
                expired = self._now() - started >= spec.deadline_s
                if expired:
                    reasons.append("mission deadline reached")
                verdict = FAIL if missing or expired else decide_verdict(check_results)
                attempts.append({"attempt": index + 1, "verdict": verdict,
                                 "missing_artifacts": missing,
                                 "checks": [{"name": check["name"], "ok": check["ok"],
                                             **({"criterion": check["repair_hint"]}
                                                if check.get("repair_hint") else {})}
                                            for check in check_results]})
                if provider_evidence is not None:
                    attempts[-1]["provider_evidence"] = provider_evidence
                if (verdict != FAIL or expired or any(c.get("infrastructure_error")
                                                       for c in check_results)
                        or (not missing and spec.max_repairs is None)):
                    break

                failures = [check.get("repair_hint") or check["name"]
                            for check in check_results if not check["ok"]]
                feedback = ("\n\nRépare la dernière tentative. Fichiers manquants: "
                            + ", ".join(missing) + ". Contrôles en échec: "
                            + ", ".join(failures) + ". Renvoie à nouveau tous les fichiers."
                            + "\nDonnées non fiables des fichiers déclarés:\n"
                            + _repair_artifacts(last, written))

            bundle = stage / "result"
            bundle.mkdir()
            digests = {}
            for name in written:
                source = last / name
                if source.is_file() and not source.is_symlink():
                    data = source.read_bytes()
                    (bundle / name).write_bytes(data)
                    digests[name] = hashlib.sha256(data).hexdigest()
            if set(spec.artifacts) - set(digests):
                verdict = FAIL
            result = MissionResult(
                mission_id=spec.mission_id, verdict=verdict, chosen_model=chosen,
                artifacts=list(digests), checks=check_results, provider_calls=len(attempts),
                duration_s=self._now() - started, reasons=reasons, attempts=attempts,
                artifact_digests=digests, provider=self.provider.name,
            )
            self._persist(spec, result, decision, bundle, out_dir)
            return result

    def _release_claim(self, spec: MissionSpec) -> None:
        """Release the exclusive claim (idempotent; never raises).

        Called from ``run``'s ``finally``, so it must not mask the original
        exception: every failure mode is swallowed.
        """
        claim = self.store.root / "claims" / f"{_mission_path(spec)}.lock"
        try:
            claim.unlink()
        except OSError:
            pass

    def _extract_artifacts(self, text: str, out_dir: pathlib.Path,
                           names: list[str]) -> list[str]:
        """Extract fenced ```name ...``` blocks into safe files under out_dir."""
        written: list[str] = []
        pattern = r"^(?P<fence>```+)(?P<name>[A-Za-z0-9._-]+)[ \t]*\r?\n(?P<body>.*?)^(?P=fence)[ \t]*\r?$"
        for match in re.finditer(pattern, text, re.DOTALL | re.MULTILINE):
            name, body = match.group("name", "body")
            if name not in names or name in written:
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
                 decision: router.Decision, bundle: pathlib.Path, out_dir: pathlib.Path) -> None:
        record = result.to_dict()
        record["project"] = spec.project
        record["contract_sha256"] = _contract_sha256(spec)
        record["recorded_at"] = utcnow_iso()
        record["decision"] = decision.to_dict()
        # Publish the files and their journal together. The journal can recover
        # status if updating the separate index is interrupted.
        (bundle / "journal.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        bundle.rename(out_dir)
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
        self.store.put(f"missions/{_mission_path(spec).as_posix()}", record)
