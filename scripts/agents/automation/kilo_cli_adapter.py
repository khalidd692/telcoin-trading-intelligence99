"""Smallest native Kilo CLI adapter for the TEL99 supervisor.

Launches ``kilo_executor.py worker`` as a real subprocess in an isolated
worktree, with mandate validation, JSON output, timeout, STOP and safe failure.
Uses the pinned ``kilo-auto/free`` model only; no paid fallback, no secret on
disk.

The supervisor (:class:`scripts.agents.automation.autonomy_runtime.Runtime`)
accepts this adapter through its ``executor=`` parameter -- no new supervisor
is created. :func:`build_runtime` is the canonical wiring: it returns a standard
Runtime whose executor runs this adapter, preserving STOP responsiveness, the
session deadline, and rate-limit to quota-backoff translation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import shutil
import sys
import tempfile
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agents.automation.kilo_executor import (  # noqa: E402
    ExecutorUnavailable, ProviderRateLimited,
)
from scripts.agents.team_config import KILO_FREE_MODEL_ID  # noqa: E402

KILO_MODEL = "kilo/kilo-auto/free"
DEFAULT_TIMEOUT_S = 100
HEX64 = re.compile(r"[0-9a-f]{64}")
MISSION_ID_RE = re.compile(r"[A-Za-z0-9-]{1,48}")
ROLES = frozenset({"tel99-dev", "tel99-analyst", "tel99-verifier"})
_ENV_DENY = ("_TOKEN", "_KEY", "_SECRET", "_PASSWORD")
_ENV_PREFIX_DENY = ("OPENAI_", "ANTHROPIC_", "GH_", "GITHUB_", "PYTHON")


class KiloCliError(RuntimeError):
    """The adapter cannot run the mission. Fail-closed: no fallback."""


class KiloCliMandateError(KiloCliError):
    """The mandate contract is invalid; no provider call is attempted."""


class KiloCliTimeout(KiloCliError):
    """The kilo run exceeded its deadline."""


class KiloCliStopped(KiloCliError):
    """A STOP marker was observed; the run was not started or was aborted."""


def validate_mandate(mission) -> None:
    """Validate a synthetic text mission contract before any provider call.

    Mirrors the contract accepted by :class:`scripts.agents.automation.kilo_executor.Executor`
    so a bad mandate is rejected before the subprocess is ever spawned.
    """
    if not isinstance(mission, dict):
        raise KiloCliMandateError("mission must be a JSON object")
    specialist = (mission.get("specialist") or mission.get("assigned_to")
                  or mission.get("role"))
    objective = mission.get("objective")
    if (mission.get("synthetic_data") is not True
            or specialist not in ROLES
            or not isinstance(objective, str) or not 1 <= len(objective) <= 4000
            or not HEX64.fullmatch(str(mission.get("expected_sha256", "")))):
        raise KiloCliMandateError("unsupported synthetic text contract")
    mid = mission.get("id")
    if not isinstance(mid, str) or not MISSION_ID_RE.fullmatch(mid):
        raise KiloCliMandateError("invalid mission id")


def _sanitized_env() -> dict:
    """Inherit the process environment minus credentials and model keys."""
    env = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper.endswith(_ENV_DENY) or upper.startswith(_ENV_PREFIX_DENY):
            continue
        env[key] = value
    env["TEL99_NATIVE_MODEL"] = KILO_MODEL
    env["TEL99_NATIVE_BASE_URL"] = "https://ai-gateway.kilo.ai/api/v1"
    return env


class KiloCliAdapter:
    """Run one bounded kilo mission in an isolated worktree subprocess."""

    def __init__(self, *, model=KILO_MODEL, timeout=DEFAULT_TIMEOUT_S,
                 worktree_root=None, launcher=None, kilo_executor=None):
        if model != KILO_MODEL:
            raise KiloCliError(f"only {KILO_MODEL} is allowed; no paid fallback")
        self.model = model
        self.timeout = int(timeout)
        self.worktree_root = Path(worktree_root) if worktree_root else None
        self.kilo_executor = kilo_executor or str(
            Path(__file__).resolve().parent / "kilo_executor.py")
        self.launcher = launcher or self._launch_worker
        self._worktree = None

    # -- mandate -----------------------------------------------------------
    def validate_mandate(self, mission) -> None:
        validate_mandate(mission)

    def __call__(self, mission, *, stop_check=None, deadline=None) -> dict:
        """Allow ``Runtime(executor=adapter)``: the supervisor calls ``executor(m)``."""
        return self.run(mission, stop_check=stop_check, deadline=deadline)

    # -- worktree ----------------------------------------------------------
    def __init__(self, *, model=KILO_MODEL, timeout=DEFAULT_TIMEOUT_S,
                 worktree_root=None, launcher=None, kilo_executor=None,
                 base_repo=None, base_sha=None):
        if model != KILO_MODEL:
            raise KiloCliError(f"only {KILO_MODEL} is allowed; no paid fallback")
        self.model = model
        self.timeout = int(timeout)
        self.worktree_root = Path(worktree_root) if worktree_root else None
        self.base_repo = Path(base_repo) if base_repo else None
        self.base_sha = base_sha
        self.kilo_executor = kilo_executor or str(
            Path(__file__).resolve().parent / "kilo_executor.py")
        self.launcher = launcher or self._launch_worker
        self._worktree = None
        self._git_worktree = False

    # -- worktree ----------------------------------------------------------
    def _enter_worktree(self) -> Path:
        if self.base_repo is not None and self.base_sha is not None:
            import subprocess as _sp
            # verify repo
            check = _sp.run(["git", "-C", str(self.base_repo), "rev-parse", "--is-inside-work-tree"],
                            capture_output=True, text=True)
            if check.returncode != 0 or check.stdout.strip() != "true":
                raise KiloCliError("base_repo is not a git work tree")
            sha_check = _sp.run(["git", "-C", str(self.base_repo), "rev-parse", self.base_sha],
                                capture_output=True, text=True)
            if sha_check.returncode != 0:
                raise KiloCliError("base_sha not found")
            root = self.worktree_root if self.worktree_root else Path(tempfile.mkdtemp(prefix="tel99-kilo-wt-"))
            root.mkdir(parents=True, exist_ok=True)
            self._worktree = root / f"kilo-run-{os.getpid()}-{int(time.monotonic()*1000)}"
            if self._worktree.exists():
                raise KiloCliError("worktree path collision")
            _sp.run(["git", "-C", str(self.base_repo), "worktree", "add", "--detach",
                     str(self._worktree), self.base_sha], check=True, capture_output=True)
            self._git_worktree = True
            # verify
            head = _sp.run(["git", "-C", str(self._worktree), "rev-parse", "HEAD"],
                           capture_output=True, text=True)
            if head.stdout.strip() != sha_check.stdout.strip():
                raise KiloCliError("worktree HEAD mismatch")
            return self._worktree
        if self.worktree_root is not None:
            self.worktree_root.mkdir(parents=True, exist_ok=True)
            self._worktree = (self.worktree_root
                              / f"kilo-run-{os.getpid()}-{int(time.monotonic() * 1000)}")
            self._worktree.mkdir(parents=True, exist_ok=True)
        else:
            self._worktree = Path(tempfile.mkdtemp(prefix="tel99-kilo-run-"))
        return self._worktree

    def _leave_worktree(self) -> None:
        # Preserve worktree for audit: never remove/prune automatically.
        self._worktree = None

    # -- subprocess --------------------------------------------------------
    def _resolve_kilo(self):
        for name in ("kilo", "kilo.cmd", "kilo.exe"):
            path = shutil.which(name)
            if path:
                return path
        raise KiloCliError("kilo CLI not found on PATH; no native run possible")

    def _launch_worker(self, mission, worktree, env, deadline, stop_check):
        """Run the native Kilo CLI as a subprocess; return (stdout, stderr, rc)."""
        exe = self._resolve_kilo()
        objective = str(mission.get("objective", ""))
        command = [exe, "run", "--model", self.model, "--agent", "code",
                   "--format", "json", objective]
        if "--auto" in command:
            raise KiloCliError("--auto is forbidden")
        proc = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, cwd=str(worktree),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        try:
            result_holder = {}

            def _comm():
                try:
                    out, err = proc.communicate()
                    result_holder["out"] = out
                    result_holder["err"] = err
                except Exception as exc:  # pragma: no cover
                    result_holder["exc"] = exc

            import threading
            t = threading.Thread(target=_comm, daemon=True)
            t.start()
            while proc.poll() is None and t.is_alive():
                if stop_check is not None and stop_check():
                    self._terminate(proc)
                    raise KiloCliStopped("STOP requested during kilo run")
                if time.monotonic() > deadline:
                    self._terminate(proc)
                    raise KiloCliTimeout("kilo run exceeded deadline")
                time.sleep(0.1)
            t.join(timeout=10)
            if t.is_alive():
                self._terminate(proc)
                raise KiloCliTimeout("kilo run exceeded deadline")
            if "exc" in result_holder:
                raise result_holder["exc"]
            stdout = result_holder.get("out", b"")
            stderr = result_holder.get("err", b"")
        except KiloCliStopped:
            raise
        except KiloCliTimeout:
            raise
        finally:
            if proc.poll() is None:
                self._terminate(proc)
        return stdout, stderr, proc.returncode

    def _terminate(self, proc):
        if proc.poll() is not None:
            return
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, timeout=10)
            else:
                proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=10)
        except Exception:
            pass

    # -- run ---------------------------------------------------------------
    def run(self, mission, *, stop_check=None, deadline=None) -> dict:
        """Launch the kilo worker in an isolated worktree and return its JSON result."""
        self.validate_mandate(mission)
        if stop_check is not None and stop_check():
            raise KiloCliStopped("STOP requested before kilo launch")
        worktree = self._enter_worktree()
        try:
            env = _sanitized_env()
            end = deadline if deadline is not None else time.monotonic() + self.timeout
            stdout, stderr, rc = self.launcher(mission, worktree, env, end, stop_check)
            if time.monotonic() > end:
                raise KiloCliTimeout("kilo run exceeded deadline")
            if rc == 5:
                raise ProviderRateLimited("Kilo free provider HTTP 429")
            if rc != 0:
                detail = stderr.decode("utf-8", errors="replace").strip()[-500:]
                raise KiloCliError(
                    f"kilo worker exited {rc}: {detail}" if detail
                    else f"kilo worker exited {rc}")
            try:
                raw_out = stdout.decode("utf-8", errors="replace").strip()
                result = self._parse_output(raw_out)
            except (ValueError, UnicodeDecodeError) as exc:
                raise KiloCliError(f"kilo worker did not return JSON: {exc}") from exc
            if result is None:
                raise KiloCliError("kilo worker returned an incomplete result")
            if isinstance(result, dict) and result.get("status") in ("permission_denied", "PERMISSION_DENIED"):
                raise KiloCliError("kilo permission denied")
            if isinstance(result, dict) and result.get("status") in ("quota", "QUOTA_EXCEEDED"):
                raise ProviderRateLimited("Kilo free provider HTTP 429")
            if not isinstance(result, dict) or "artifact" not in result:
                # CODE mission: require git evidence instead of artifact-only
                if not (isinstance(result, dict) and result.get("git_changed") is True
                        and result.get("tests_passed") is True):
                    raise KiloCliError("kilo worker returned an incomplete result")
            return result
        finally:
            self._leave_worktree()

    def _parse_output(self, raw):
        # Accept single JSON object or newline-delimited JSON events
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        if not lines:
            return None
        try:
            obj = json.loads(raw)
            return obj
        except json.JSONDecodeError:
            events = []
            for ln in lines:
                try:
                    events.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
            if not events:
                return None
            # last event wins
            return events[-1]
        finally:
            self._leave_worktree()


def build_runtime(root, *, adapter=None, launcher=None, worktree_root=None,
                  timeout=DEFAULT_TIMEOUT_S, legacy_stop=None):
    """Finish the native TEL99 wiring: a standard Runtime driven by this adapter.

    No new supervisor is created. The returned object is the ordinary
    :class:`scripts.agents.automation.autonomy_runtime.Runtime` whose executor
    runs the native Kilo CLI adapter in an isolated worktree. Three invariants
    are preserved when the adapter is wired this way:

    * STOP interrupts an active worker (``stop_check=runtime.stopped``), so a
      requested stop never waits for the full adapter timeout.
    * The supervisor session deadline bounds the run
      (``deadline=min(now + timeout, runtime.deadline)``).
    * A free-provider rate limit (``ProviderRateLimited``) is translated to the
      supervisor's ``QuotaBlocked`` so quota backoff and no-replay semantics are
      identical to the built-in worker. The independent verifier is unchanged.
    """
    from scripts.agents.automation.autonomy_runtime import Runtime, QuotaBlocked

    import subprocess as _sp
    base_repo = Path(__file__).resolve().parents[3]
    r = _sp.run(["git", "-C", str(base_repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    base_sha = r.stdout.strip() if r.returncode == 0 else None
    if adapter is None:
        adapter = KiloCliAdapter(timeout=timeout, worktree_root=worktree_root,
                                 launcher=launcher, base_repo=base_repo, base_sha=base_sha)
    runtime = Runtime(root, legacy_stop=legacy_stop)

    def execute(mission):
        ceiling = runtime.deadline if runtime.deadline is not None else float("inf")
        deadline = min(time.monotonic() + timeout, ceiling)
        try:
            return adapter(mission, stop_check=runtime.stopped, deadline=deadline)
        except ProviderRateLimited as exc:
            raise QuotaBlocked(
                getattr(exc, "reason", "BLOCKED_PROVIDER_RATE_LIMIT")) from exc

    runtime.executor = execute
    return runtime


def main(argv=None) -> int:
    """CLI entry point: read a mission from stdin, run it, print JSON result."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(1_000_000)
        mission = json.loads(raw.decode("utf-8"))
        adapter = KiloCliAdapter(timeout=args.timeout)
        result = adapter.run(mission)
        print(json.dumps(result, ensure_ascii=True), flush=True)
        return 0
    except KiloCliStopped:
        print(json.dumps({"status": "BLOCKED", "reason": "STOPPED"}),
              ensure_ascii=True, flush=True)
        return 2
    except ProviderRateLimited:
        print(json.dumps({"status": "BLOCKED", "reason": "BLOCKED_PROVIDER_RATE_LIMIT"}),
              ensure_ascii=True, flush=True)
        return 5
    except (KiloCliError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "BLOCKED", "reason": "KILO_CLI_UNAVAILABLE_OR_INVALID_MANDATE"}),
              ensure_ascii=True, flush=True)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
