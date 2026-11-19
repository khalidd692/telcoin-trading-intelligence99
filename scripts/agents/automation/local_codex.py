"""Windows transport for the TEL99 automation policy and local FileStore."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
from threading import Event, Lock, Thread
import time
import codex_model_router as router

from policy import (
    approval_is_authorized, has_authenticated_approval, is_eligible_mission,
    mission_content, mission_digest, utcnow_iso,
)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol.store import FileStore
from local_coordination import CoordinationUnavailable, UpstashCoordination, accepted_proof, coordination_backend
from local_code import NATIVE_BASE, contract_digest, status_paths, synthetic_missions, valid_scope
import local_native as native

REPO = "khalidd692/telcoin-trading-intelligence99"
BACKLOG = "docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/BACKLOG.json"
BACKLOG_REF = "315fd08c11a18093c99ccaff2bd3b69358e6fbbc"
STATE = ROOT / ".tel99-automation-state" / "local-codex"
MODEL_ENV_DENY = ("OPENAI_", "CODEX_", "GH_", "GITHUB_", "AZURE_", "ANTHROPIC_")


class Blocked(RuntimeError):
    pass


class QuotaBlocked(Blocked):
    pass


@contextmanager
def exclusive(path):
    import msvcrt

    with path.open("a+b") as handle:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise Blocked("Un superviseur utilise déjà cette file.") from exc
        yield


def call(argv, *, cwd=ROOT, timeout=45, env=None, input_text=None):
    return subprocess.run(
        argv, cwd=cwd, env=env, input=input_text, capture_output=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )


def checked(argv, *, cwd=ROOT, env=None):
    result = call(argv, cwd=cwd, env=env)
    if result.returncode:
        raise Blocked(f"{Path(argv[0]).name} {argv[1]} a quitté avec {result.returncode}")
    return result.stdout.strip()


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def model_environment():
    return {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith(MODEL_ENV_DENY)
        and not key.upper().endswith(("_TOKEN", "_KEY", "_SECRET", "_PASSWORD"))
    }


def allowance(snapshot):
    credits = snapshot.get("credits")
    if (
        not isinstance(credits, dict)
        or credits.get("hasCredits") is not False
        or credits.get("unlimited") is not False
    ):
        raise QuotaBlocked("Absence de crédits facturables non confirmée.")
    windows = [snapshot.get(name) for name in ("primary", "secondary")]
    active = [window for window in windows if window is not None]
    if not active or any(
        not isinstance(window, dict) or type(window.get("usedPercent")) not in (int, float)
        or not 0 <= window["usedPercent"] < 90 for window in active
    ):
        raise QuotaBlocked("Quota Codex inconnu ou réserve de 10 % atteinte.")
    return [window["usedPercent"] for window in active]


def rate_snapshot(cli, cwd):
    with subprocess.Popen(
        [cli, "app-server"], cwd=cwd, env=model_environment(),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        encoding="utf-8", errors="replace",
    ) as proc:
        lines = queue.Queue()

        def read():
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)

        reader = Thread(target=read, daemon=True)
        reader.start()
        try:
            for message in (
                {"id": 1, "method": "initialize", "params": {
                    "clientInfo": {"name": "tel99-local", "version": "1.0"}}},
                {"method": "initialized"},
                {"id": 2, "method": "account/rateLimits/read"},
            ):
                proc.stdin.write(json.dumps(message) + "\n")
                proc.stdin.flush()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                line = lines.get(timeout=max(0, deadline - time.monotonic()))
                if line is None:
                    break
                event = json.loads(line)
                if event.get("id") == 2:
                    return event.get("result", {}).get("rateLimits", {})
        except (queue.Empty, OSError, ValueError):
            pass
        finally:
            if proc.poll() is None:
                proc.kill()
            reader.join(timeout=5)
    raise QuotaBlocked("Lecture des limites Codex indisponible.")


def validate_issue(issue, approval):
    if not is_eligible_mission(issue, "codex-local/mission"):
        return "Issue fermée ou label de mission absent."
    if issue.get("user", {}).get("login") != "khalidd692":
        return "Auteur GitHub hors périmètre."
    if [item["login"] for item in issue.get("assignees", [])] != [approval["assignee"]]:
        return "Attribution exclusive divergente."
    body_hash = approval.get("issue_sha256")
    if (body_hash is not None or approval.get("kind") not in {"code", "native"}) and digest(issue.get("body") or "") != body_hash:
        return "Contenu GitHub modifié depuis l’approbation."
    try:
        expiry = datetime.strptime(approval["expires_at"], "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return "Date d’expiration de l’approbation invalide."
    if expiry.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        return "Approbation expirée."
    return None


class Supervisor:
    def __init__(self, root, cli=None, *, demo=False):
        self.root = root
        self.store = FileStore(root / "ledger")
        self.cli = cli
        self.demo = demo
        self.deadline = None
        self.live_lock = Lock()
        self.live = dict(STATE="IDLE", CLAIM="NONE", ACTIVE_TASK=None, QUOTA=None,
                         LAST_VERDICT=None, BLOCKER=None, NEXT=None)

    def observe(self, **fields):
        with self.live_lock:
            self.live.update(fields)

    def checkpoint(self, mission, status, **details):
        task_id = mission["id"]
        row = {"id": task_id, "issue": mission.get("issue"), "status": status, "at": utcnow_iso(), **details}
        self.observe(STATE=status, ACTIVE_TASK=task_id if status in {"RUNNING", "WORKER_EXITED"} else None,
                     BLOCKER=status if status.startswith(("WAITING", "BLOCKED", "AWAITING")) else None)
        if "quota_used" in details:
            self.observe(QUOTA=details["quota_used"] or None)
        if status in {"PREPARED", "ACCEPTED", "BLOCKED", "FAILED"}:
            self.observe(LAST_VERDICT=status)
        self.store.put(f"codex-local/{task_id}", row)
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(row, ensure_ascii=True), flush=True)

    def state(self, mission):
        key = f"codex-local/{mission['id']}"
        value = self.store.get(key)
        if value is None and (self.store.root / f"{key}.json").exists():
            raise Blocked(f"Checkpoint illisible pour {mission['id']}")
        return value or {}

    def run(self, missions, blockers=None, dependency_proofs=None):
        blockers = blockers or {}
        dependency_proofs = dependency_proofs or {}
        for mission in sorted(missions, key=lambda item: (item["priority"], item["id"])):
            if not self.demo and ((self.root / "stop.request").exists()
                                  or self.deadline is not None and time.monotonic() >= self.deadline):
                return True
            saved = self.state(mission)
            stage = saved.get("status")
            recover_native = stage == "RUNNING" and mission.get("kind") == "native" and saved.get("native_base")
            if stage == "RUNNING" and not recover_native:
                self.checkpoint(mission, "INTERRUPTED", reason="Exécution orpheline possible")
                continue
            if stage in {"ACCEPTED", "PREPARED", "INTERRUPTED", "FAILED", "BLOCKED"}:
                continue
            issue_blocker = blockers.get(mission["id"])
            if issue_blocker:
                if stage == "WORKER_EXITED" or recover_native:
                    print(f"AWAITING_HUMAN {mission['id']}: {issue_blocker}", flush=True)
                else:
                    self.checkpoint(mission, "AWAITING_HUMAN", reason=issue_blocker)
                continue
            unmet = [
                dep for dep in mission.get("dependencies", [])
                if dep not in dependency_proofs
                and (not self.demo or self.state({"id": dep}).get("status") != "ACCEPTED")
            ]
            if unmet:
                if stage == "WORKER_EXITED" or recover_native:
                    print(f"WAITING_DEPENDENCY {mission['id']}: {', '.join(unmet)}", flush=True)
                else:
                    self.checkpoint(mission, "WAITING_DEPENDENCY", dependencies=unmet)
                continue
            try:
                if not self.demo:
                    self.run_shared(mission, saved)
                elif stage == "WORKER_EXITED":
                    if saved["approval"] != digest(json.dumps(mission, sort_keys=True)):
                        raise Blocked("Approbation différente depuis la sortie du worker.")
                    self.finalize(mission, saved["base"], saved["branch"])
                else:
                    self.execute(mission)
            except QuotaBlocked as exc:
                status = "INTERRUPTED" if self.state(mission).get("status") == "RUNNING" else "WAITING_QUOTA"
                self.checkpoint(mission, status, reason=str(exc))
                return False
            except CoordinationUnavailable as exc:
                # Preserve a post-worker checkpoint for eventual reconciliation.
                if self.state(mission).get("status") not in {"RUNNING", "WORKER_EXITED"}:
                    self.checkpoint(mission, "WAITING_COORDINATION", reason=str(exc))
                else:
                    print(f"WAITING_COORDINATION {mission['id']}: {exc}", flush=True)
            except (Blocked, OSError, ValueError, subprocess.TimeoutExpired) as exc:
                # Details from third-party processes stay out of the shared ledger.
                reason = str(exc) if isinstance(exc, Blocked) else type(exc).__name__
                self.checkpoint(mission, "BLOCKED" if isinstance(exc, Blocked) else "FAILED", reason=reason)
        return True

    def run_shared(self, mission, saved):
        shared = coordination_backend()
        approval = digest(json.dumps(mission, sort_keys=True))
        if saved.get("status") == "WORKER_EXITED" or (
            saved.get("status") == "RUNNING" and mission.get("kind") == "native" and saved.get("native_base")
        ):
            if saved["approval"] != approval:
                raise CoordinationUnavailable("L’approbation du checkpoint a changé.")
            owner = saved["shared_owner"]
            remote, finish = shared.resume(mission["id"], mission["issue"], approval, owner)
            fence = lambda: shared.owns(owner)
            if remote["status"] == "PREPARED":
                def fence():
                    raise CoordinationUnavailable("Le commit distant est déjà enregistré.")
            self.finalize(mission, saved.get("base") or saved["native_base"],
                          saved.get("branch", ""), fence=fence, finish=finish)
            return
        # Check the quota before creating a durable reservation.
        limits = [] if mission.get("kind") == "native" else allowance(rate_snapshot(self.cli, self.root))
        with shared.claim(mission["id"], mission["issue"], approval) as (owner, finish):
            self.observe(CLAIM="HELD", ACTIVE_TASK=mission["id"])
            self.store.put(f"claims/{mission['id']}", {
                "issue": mission["issue"], "at": utcnow_iso(), "approval": approval, "state": "ACK",
            })
            try:
                reason = fetch_approved_issue(mission)
                if reason:
                    raise Blocked(reason)
                if mission.get("kind") == "code":
                    check_code_conflicts(mission)
                self.execute(
                    mission, limits=limits, shared_owner=owner,
                    fence=lambda: shared.owns(owner), finish=finish,
                )
            except (Blocked, QuotaBlocked, ValueError):
                # These are known outcomes. A timeout or interruption leaves the
                # reservation in place until the worker is reconciled.
                finish("BLOCKED")
                raise
            finally:
                # Release is separately determined by the coordination backend.
                self.observe(CLAIM="RECHECK")

    def execute(self, mission, *, limits=None, shared_owner=None, fence=None, finish=None):
        task_id = mission["id"]
        if not re.fullmatch(r"[A-Z0-9-]{1,48}", task_id):
            raise Blocked("Identifiant de mission invalide.")
        bounds = limits if limits is not None else allowance(rate_snapshot(self.cli, self.root))
        workspace = self.root / task_id
        self.checkpoint(mission, "RUNNING", workspace=str(workspace), quota_used=bounds)
        if workspace.exists():
            raise Blocked("Espace existant. Réconciliation manuelle requise.")
        if mission.get("kind") == "native":
            return self.execute_native(mission, workspace, shared_owner, fence, finish)
        if self.demo:
            workspace.mkdir()
            checked(["git", "init", "-b", "pilot-base"], cwd=workspace)
            if mission.get("kind") == "code":
                tests = workspace / "tests"
                tests.mkdir()
                (tests / mission["test_file"]).write_text(mission["fixture"], encoding="utf-8")
                (workspace / "operation.py").write_text("# Implémentation à compléter.\n", encoding="utf-8")
                checked(["git", "add", "--", "tests", "operation.py"], cwd=workspace)
            self.commit(workspace, "Initialiser le pilote isolé", empty=True)
        else:
            if mission.get("kind") == "code":
                workspace.mkdir()
                checked(["git", "init"], cwd=workspace)
                checked(["git", "fetch", "--depth=1", "--no-tags",
                         f"https://github.com/{REPO}.git", NATIVE_BASE], cwd=workspace)
                if checked(["git", "rev-parse", "FETCH_HEAD"], cwd=workspace) != mission["base_sha"]:
                    raise Blocked("La branche #105 a avancé après l’approbation.")
            else:
                checked(["git", "clone", "--no-local", "--no-checkout", str(ROOT), str(workspace)])
                checked(["git", "remote", "remove", "origin"], cwd=workspace)
            checked(["git", "checkout", "--detach", mission["base_sha"]], cwd=workspace)
        branch = f"agents/codex-local/{task_id.lower()}"
        checked(["git", "checkout", "-b", branch], cwd=workspace)
        base = checked(["git", "rev-parse", "HEAD"], cwd=workspace)
        allowed = mission["files"] if mission.get("kind") == "code" else [mission["path"]]
        prompt = (
            "Mission TEL99 bornée. Modifie uniquement les fichiers autorisés dans ce checkout. "
            "Tu peux lire et tester dans le checkout. Ne fais aucun commit, aucun accès réseau, "
            "aucun ordre, aucune suppression et aucune opération GitHub. "
            f"Fichiers autorisés: {', '.join(allowed)}\nObjectif approuvé: {mission['objective']}"
        )
        args = [
            self.cli, "-a", "never", "exec", "--ignore-user-config", "--ephemeral",
            "--sandbox", "workspace-write", "--disable", "hooks",
            "-c", "windows.sandbox=mxc",
            "-c", 'web_search="disabled"', "-c", "sandbox_workspace_write.network_access=false",
            "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
            "-c", "sandbox_workspace_write.exclude_slash_tmp=true", "-",
        ]
        route = None
        started = time.monotonic()
        if mission.get("routing_profile"):
            approval = digest(json.dumps(mission, sort_keys=True))
            key = f"codex-local-route/{task_id}"
            checkpoint = self.store.get(key) or router.new_checkpoint(task_id, approval, mission["routing_profile"])

            def persist(plan):
                if fence:
                    fence()
                self.store.put(key, plan)

            try:
                snapshot = router.read_snapshot(self.cli, workspace, model_environment())
                route, args = router.prepare_exec(args, checkpoint, approval, base, snapshot, persist)
            except router.RouteBlocked as exc:
                if exc.status == "WAITING_QUOTA":
                    raise QuotaBlocked(str(exc)) from exc
                raise Blocked(f"{exc.status}: {exc}") from exc
            self.store.put(f"codex-local-route-clock/{task_id}", {"started": time.time()})
        if fence:
            fence()
        result = call(args, cwd=workspace, env=model_environment(), timeout=240, input_text=prompt)
        if result.returncode:
            if route:
                self.complete_route(mission, "worker_error", exec_jsonl=result.stdout)
            if re.search(r"usage limit|rate.?limit|quota|too many requests", result.stderr, re.I):
                raise QuotaBlocked("Quota atteint pendant le run.")
            if re.search(r"sandbox setup|sandbox failed|access is denied|unauthorized", result.stderr, re.I):
                raise Blocked("Le CLI a signalé une erreur de sandbox ou d'accès.")
            raise Blocked(f"codex exec a quitté avec {result.returncode}")
        self.checkpoint(
            mission, "WORKER_EXITED", base=base, branch=branch, codex_exit=result.returncode,
            approval=digest(json.dumps(mission, sort_keys=True)), shared_owner=shared_owner,
        )
        if route:
            self.store.put(f"codex-local-route-clock/{task_id}", {
                "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
            })
        self.finalize(mission, base, branch, fence=fence, finish=finish,
                      **({"exec_jsonl": result.stdout} if route else {}))

    def complete_route(self, mission, status, *, proof=None, exec_jsonl=""):
        if not mission.get("routing_profile"):
            return
        task = mission["id"]
        key = f"codex-local-route/{task}"
        checkpoint = self.store.get(key)
        if not checkpoint or checkpoint["attempts"][-1]["status"] != "running":
            return
        clock = self.store.get(f"codex-local-route-clock/{task}") or {}
        duration = clock.get("duration_ms")
        if duration is None:
            duration = max(0, int((time.time() - clock.get("started", time.time())) * 1000))
        try:
            after = router.read_snapshot(self.cli, self.root, model_environment(), include_catalog=False)
        except router.RouteBlocked:
            after = None
        updated = router.record_result(
            checkpoint, digest(json.dumps(mission, sort_keys=True)), checkpoint["attempts"][-1]["number"],
            status, duration_ms=duration, quota_after=after, exec_jsonl=exec_jsonl,
            artifact_sha256=digest(json.dumps(proof["artifact_digests"], sort_keys=True)) if proof else None,
            test_evidence_sha256=digest(json.dumps(proof, sort_keys=True)) if proof else None,
        )
        self.store.put(key, updated)

    def finalize(self, mission, base, branch, *, fence=None, finish=None, exec_jsonl=""):
        if mission.get("kind") == "native":
            return self.finalize_native(mission, base, fence=fence, finish=finish)
        if mission.get("kind") == "code":
            return self.finalize_code(mission, base, branch, fence=fence, finish=finish,
                                      exec_jsonl=exec_jsonl)
        task_id = mission["id"]
        workspace = self.root / task_id
        target = workspace / mission["path"]
        if target.resolve() != target or not target.is_file() or target.stat().st_size > 100_000:
            raise Blocked("Fichier absent, redirigé ou trop volumineux.")
        status = checked([
            "git", "status", "--porcelain", "--untracked-files=all", "--ignored=matching",
        ], cwd=workspace)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != mission["expected_sha256"]:
            raise Blocked("Le SHA-256 du contenu ne correspond pas au critère approuvé.")
        commit = checked(["git", "rev-parse", "HEAD"], cwd=workspace)
        if checked(["git", "branch", "--show-current"], cwd=workspace) != branch:
            raise Blocked("Branche de mission inattendue.")
        if commit == base:
            if status not in {f"?? {mission['path']}", f"A  {mission['path']}"}:
                raise Blocked("Le diff dépasse le nouveau fichier autorisé.")
            if fence:
                fence()
            checked(["git", "add", "--", mission["path"]], cwd=workspace)
            self.commit(workspace, f"TEL99 {task_id}: résultat vérifié")
            commit = checked(["git", "rev-parse", "HEAD"], cwd=workspace)
        elif status or checked(["git", "rev-list", "--parents", "-1", commit], cwd=workspace) != f"{commit} {base}":
            raise Blocked("Historique ou état inattendu pendant la reprise.")
        paths = checked(["git", "diff", "--name-only", base, commit], cwd=workspace)
        blob = subprocess.check_output(["git", "show", f"{commit}:{mission['path']}"], cwd=workspace, timeout=45)
        if paths != mission["path"] or hashlib.sha256(blob).hexdigest() != actual:
            raise Blocked("Contrôle indépendant du résultat échoué.")
        proof = {
            "commit": commit, "base": base, "branch": branch, "file": mission["path"],
            "sha256": actual, "checks": ["exact-content-sha256", "single-file-git-diff"],
            "workspace": str(workspace), "codex_exit": 0,
        }
        (self.root / f"{task_id}.pr.md").write_text(
            f"TEL99 {task_id}\n\nBase {base}\nBranche {branch}\nCommit {commit}\n"
            f"Fichier {mission['path']}\nSHA-256 {actual}\n", encoding="utf-8",
        )
        if finish:
            finish("PREPARED", commit)
        self.checkpoint(mission, "ACCEPTED" if self.demo else "PREPARED", **proof)

    def execute_native(self, mission, workspace, owner, fence, finish):
        data_root = native.storage_root(ROOT, mission["issue"])
        if data_root.resolve() != data_root or data_root.exists():
            raise Blocked("Le stockage natif existe déjà ou est redirigé.")
        workspace.mkdir()
        checked(["git", "init"], cwd=workspace)
        checked(["git", "config", "core.autocrlf", "false"], cwd=workspace)
        checked(["git", "fetch", "--depth=1", "--no-tags", f"https://github.com/{REPO}.git",
                 native.NATIVE_REF], cwd=workspace)
        sha = checked(["git", "rev-parse", "FETCH_HEAD"], cwd=workspace)
        if sha != native.NATIVE_SHA or sha != mission["base_sha"]:
            raise Blocked("Le moteur #110 a changé depuis l’approbation.")
        checked(["git", "checkout", "--detach", sha], cwd=workspace)
        branch = f"agents/codex-local/{mission['id'].lower()}"
        checked(["git", "checkout", "-b", branch], cwd=workspace)
        env = {key: value for key, value in model_environment().items()
               if not key.upper().startswith(("TEL99_NATIVE_", "PYTHON"))}
        env.update(TEL99_NATIVE_MODEL="kilo-auto/free",
                   TEL99_NATIVE_BASE_URL="https://ai-gateway.kilo.ai/api/v1")
        self.checkpoint(
            mission, "RUNNING", native_base=sha, branch=branch, shared_owner=owner,
            approval=digest(json.dumps(mission, sort_keys=True)), short_native_storage=True,
        )
        fence()
        data_root.mkdir(parents=True, exist_ok=False)
        result = call(native.args_for(workspace, mission["issue"], "run", objective=mission["objective"],
                                      data_root=data_root), cwd=workspace,
                      env=env, timeout=240)
        if result.returncode in (0, 3):
            report = json.loads(result.stdout)
            evidence = native.result_evidence(report)
            evidence["exit_code"] = result.returncode
            evidence["base"] = sha
            self.store.put(f"native-results/{mission['id']}", evidence)
        if result.returncode == 3:
            raise Blocked(f"Le moteur natif a rendu {evidence['verdict']} (code 3).")
        if result.returncode:
            raise Blocked(f"Le moteur natif #110 a quitté avec {result.returncode}.")
        if report.get("provider_calls") != 1 or report.get("provider") != "kilo-auto-free":
            raise Blocked("Le journal du fournisseur ne correspond pas au budget approuvé.")
        self.checkpoint(
            mission, "WORKER_EXITED", base=sha, branch=branch,
            approval=digest(json.dumps(mission, sort_keys=True)), shared_owner=owner,
            short_native_storage=True,
        )
        self.finalize_native(mission, sha, fence=fence, finish=finish)

    def finalize_native(self, mission, base, *, fence, finish):
        workspace = self.root / mission["id"]
        head = checked(["git", "rev-parse", "HEAD"], cwd=workspace)
        branch = f"agents/codex-local/{mission['id'].lower()}"
        if (base != native.NATIVE_SHA or checked(["git", "branch", "--show-current"], cwd=workspace) != branch
                or (head != base and checked(["git", "rev-list", "--parents", "-1", head],
                                              cwd=workspace) != f"{head} {base}")):
            raise Blocked("Le SHA du moteur en reprise ne correspond pas à #110.")
        env = {key: value for key, value in model_environment().items()
               if not key.upper().startswith(("TEL99_NATIVE_", "PYTHON"))}
        saved = self.state(mission)
        data_root = native.storage_root(ROOT, mission["issue"]) if saved.get("short_native_storage") else workspace
        result = call(native.args_for(workspace, mission["issue"], "status", data_root=data_root), cwd=workspace,
                      env=env, timeout=45)
        if result.returncode:
            raise Blocked("Absence de journal natif récupérable.")
        record = json.loads(result.stdout)
        if record.get("verdict") != "PASS" or record.get("artifact_integrity") != "matched":
            raise Blocked("Les artefacts natifs ne correspondent pas au journal PASS.")
        directory = Path(record["artifact_directory"])
        expected = data_root / "_native_state" / "artifacts"
        if not directory.resolve().is_relative_to(expected.resolve()):
            raise Blocked("Emplacement des artefacts inattendu.")
        hashes = record["artifact_digests"]
        if set(hashes) != set(native.FILES) or any(
            not (directory / name).is_file() or (directory / name).resolve() != directory.resolve() / name
            or hashlib.sha256((directory / name).read_bytes()).hexdigest() != hashes[name]
            for name in native.FILES
        ):
            raise Blocked("Échec de la vérification des empreintes natives.")
        verify = call([
            sys.executable, "-B", "-m", "scripts.agents.native.cli", "verify-task-app",
            "--file", str(directory / "tasks.py"), "--sandbox-image", native.IMAGE,
        ], cwd=workspace, env=env, timeout=120)
        if verify.returncode:
            raise Blocked("Le rejeu Docker indépendant du moteur natif a échoué.")
        proof = json.loads(verify.stdout)
        if (proof.get("ok") is not True or proof.get("artifact_sha256") != hashes["tasks.py"]
                or not isinstance(proof.get("checks"), list) or len(proof["checks"]) != 6):
            raise Blocked("La preuve Docker au SHA est incohérente.")
        folder = f"docs/agents/codex-local-results/{mission['id'].lower()}"
        paths = [f"{folder}/{name}" for name in native.FILES]
        if head == base:
            fence()
            target = workspace / folder
            if target.resolve() != target:
                raise Blocked("Chemin de publication native redirigé.")
            target.mkdir(parents=True, exist_ok=True)
            for name in native.FILES:
                dest = target / name
                if dest.exists() and (not dest.is_file() or dest.resolve() != dest
                                      or hashlib.sha256(dest.read_bytes()).hexdigest() != hashes[name]):
                    raise Blocked("Artefact de publication antérieur incohérent.")
                if not dest.exists():
                    with dest.open("xb") as output:
                        output.write((directory / name).read_bytes())
            checked(["git", "add", "--", *paths], cwd=workspace)
            staged = checked(["git", "diff", "--cached", "--name-only"], cwd=workspace).splitlines()
            if sorted(staged) != sorted(paths):
                raise Blocked("L’index natif contient des fichiers inattendus.")
            self.commit(workspace, f"TEL99 #{mission['issue']}: artefacts natifs vérifiés")
            head = checked(["git", "rev-parse", "HEAD"], cwd=workspace)
        if sorted(checked(["git", "diff", "--name-only", base, head], cwd=workspace).splitlines()) != sorted(paths):
            raise Blocked("Le diff du commit natif dépasse son périmètre.")
        for name, path in zip(native.FILES, paths):
            blob = subprocess.check_output(["git", "show", f"{head}:{path}"], cwd=workspace, timeout=45)
            if hashlib.sha256(blob).hexdigest() != hashes[name]:
                raise Blocked("Le blob Git natif ne correspond pas à la preuve.")
        finish("PREPARED", head)
        self.checkpoint(mission, "PREPARED", commit=head, base=base, branch=branch,
                        artifact_digests=hashes, test_count=len(proof["checks"]),
                        native=True, provider="kilo-auto-free")

    def finalize_code(self, mission, base, branch, *, fence, finish, exec_jsonl=""):
        task_id = mission["id"]
        workspace = self.root / task_id
        status_cmd = ["git", "status", "--porcelain", "--untracked-files=all", "--ignored=matching"]
        commit = checked(["git", "rev-parse", "HEAD"], cwd=workspace)
        if checked(["git", "branch", "--show-current"], cwd=workspace) != branch:
            raise Blocked("Branche de mission inattendue.")
        initial_status = call(status_cmd, cwd=workspace)
        if initial_status.returncode:
            raise Blocked("Impossible de lire le diff du checkout.")
        status = initial_status.stdout.rstrip("\r\n")
        if commit == base:
            paths = status_paths(status)
            allowed = set(mission["files"])
            if not paths or not set(paths) <= allowed:
                raise Blocked("Le code modifié dépasse le périmètre approuvé.")
            for path in paths:
                target = workspace / path
                if target.resolve() != target or not target.is_file() or target.stat().st_size > 100_000:
                    raise Blocked("Fichier absent, redirigé ou trop volumineux.")
            if fence:
                fence()
            checked(["git", "add", "--", *paths], cwd=workspace)
            self.commit(workspace, f"TEL99 {task_id}: code à vérifier")
            commit = checked(["git", "rev-parse", "HEAD"], cwd=workspace)
        elif status or checked(["git", "rev-list", "--parents", "-1", commit], cwd=workspace) != f"{commit} {base}":
            raise Blocked("Historique ou état inattendu pendant la reprise.")
        diff = checked(["git", "diff", "--name-status", "--no-renames", base, commit], cwd=workspace)
        paths = []
        for line in diff.splitlines():
            operation, path = line.split("\t", 1)
            if operation not in {"A", "M"} or path not in mission["files"]:
                raise Blocked("Le commit dépasse le périmètre approuvé.")
            if not checked(["git", "ls-tree", commit, "--", path], cwd=workspace).startswith("100644 blob "):
                raise Blocked("Mode de fichier inattendu dans le commit.")
            paths.append(path)
        if not paths or checked(status_cmd, cwd=workspace):
            raise Blocked("Le commit de code doit être propre et contenir un diff.")
        test_path = f"tests/{mission['test_file']}"
        test_blob = checked(["git", "rev-parse", f"{base}:{test_path}"], cwd=workspace)
        if checked(["git", "rev-parse", f"{commit}:{test_path}"], cwd=workspace) != test_blob:
            raise Blocked("Le test indépendant a changé.")
        test_count = self.run_code_tests(workspace, mission["test_file"], mission.get("test_selector"))
        extra = mission.get("supplemental_test")
        if extra:
            if f"tests/{extra}" not in paths:
                raise Blocked("Le test complémentaire approuvé manque au commit.")
            test_count += self.run_code_tests(workspace, extra)
        if checked(["git", "rev-parse", "HEAD"], cwd=workspace) != commit or checked(status_cmd, cwd=workspace):
            raise Blocked("Le checkout a changé pendant la vérification.")
        proof = {"commit": commit, "base": base, "branch": branch, "files": paths,
                 "test_file": test_path, "test_blob": test_blob, "test_count": test_count,
                 "test_selector": mission.get("test_selector"), "supplemental_test": extra,
                 "artifact_digests": {
                     path: hashlib.sha256(subprocess.check_output(
                         ["git", "show", f"{commit}:{path}"], cwd=workspace, timeout=45,
                     )).hexdigest()
                     for path in paths
                 }}
        (self.root / f"{task_id}.pr.md").write_text(
            f"TEL99 {task_id}\n\nBase {base}\nCommit {commit}\n"
            f"Test indépendant {test_path} ({test_blob}), "
            f"sélecteur {proof['test_selector']}, complément {extra}: {test_count} PASS.\n",
            encoding="utf-8",
        )
        self.complete_route(mission, "tests_passed", proof=proof, exec_jsonl=exec_jsonl)
        if finish:
            finish("PREPARED", commit)
        self.checkpoint(mission, "ACCEPTED" if self.demo else "PREPARED", **proof)

    def run_code_tests(self, workspace, test_file, selector=None):
        command = [
            self.cli, "-c", "windows.sandbox=mxc", "sandbox", "--include-managed-config",
            "--permission-profile", ":read-only", "--", sys.executable, "-B", "-m",
            "unittest", "discover", "-s", "tests", "-p", test_file,
        ]
        if selector:
            command.extend(["-k", selector])
        result = call(command, cwd=workspace, env=model_environment(), timeout=120)
        report = result.stdout + result.stderr
        run_count = re.search(r"^Ran ([1-9][0-9]*) tests? in ", report, re.M)
        if result.returncode or not run_count or not re.search(r"^OK\s*$", report, re.M):
            raise Blocked(f"Vérification indépendante échouée (sortie {result.returncode}).")
        return int(run_count[1])

    def commit(self, cwd, message, *, empty=False):
        args = ["git", "-c", f"core.hooksPath={self.root / 'no-hooks'}", "-c",
                "user.name=TEL99 Codex Local", "-c", "user.email=tel99-local@users.noreply.github.com",
                "-c", "commit.gpgSign=false", "commit", "-m", message]
        if empty:
            args.append("--allow-empty")
        checked(args, cwd=cwd)


def demo_missions():
    return [
        {"id": task_id, "priority": "P0", "path": "proof.txt", "dependencies": deps,
         "objective": f"Écris exactement le texte ASCII {value} dans proof.txt, sans saut de ligne.",
         "expected_sha256": digest(value)}
        for task_id, value, deps in (
            ("DEMO-01", "TEL99 PILOT ONE", []),
            ("DEMO-02", "TEL99 PILOT TWO", ["DEMO-01"]),
        )
    ]


def sync_github(supervisor):
    master = json.loads(checked(["gh", "api", f"repos/{REPO}/issues/94"]))
    content = checked(["gh", "api", f"repos/{REPO}/contents/{BACKLOG}?ref={BACKLOG_REF}",
                       "-H", "Accept: application/vnd.github.raw+json"])
    backlog = json.loads(content)
    supervisor.store.put("github/master", {
        "issue": 94, "state": master["state"], "updated_at": master["updated_at"],
        "backlog_ref": BACKLOG_REF, "tasks": [
            {key: task[key] for key in ("id", "owner", "priority", "dependencies")}
            for task in backlog["tasks"]
        ],
    })
    return backlog["tasks"], master["state"]


def approved_queue(path, backlog, *, master_state):
    return admit_missions(json.loads(path.read_text(encoding="utf-8-sig")), backlog, master_state=master_state)


def admit_missions(missions, backlog, *, master_state):
    known = {task["id"]: task for task in backlog}
    blockers = {}
    seen = set()
    issue_numbers = set()
    for mission in missions:
        task_id = mission["id"]
        if not re.fullmatch(r"[A-Z0-9-]{1,48}", task_id) or task_id in seen:
            raise Blocked("Identifiant absent, invalide ou dupliqué.")
        seen.add(task_id)
        if not re.fullmatch(r"[0-9a-f]{40}", mission["base_sha"]) or (
            type(mission["issue"]) is not int or mission["issue"] <= 94
        ):
            raise Blocked("Ticket distinct et SHA de base épinglé requis.")
        kind = mission.get("kind")
        if kind in {"code", "native"}:
            deps = mission.get("dependencies")
            if (
                (kind == "code" and (
                    not re.fullmatch(r"CODEX105-[A-Z0-9-]+", task_id) or not valid_scope(mission)
                    or mission.get("routing_profile") not in {None, *router.PROFILES}
                ))
                or (kind == "native" and not native.native_scope(mission))
                or mission.get("priority") not in {"P0", "P1", "P2", "P3"}
                or not isinstance(deps, list)
                or not all(isinstance(dep, str) and (
                    dep in known or re.fullmatch(r"CODEX(?:105|110)-[A-Z0-9-]+", dep)
                ) for dep in deps)
            ):
                raise Blocked("Contrat de code #105 invalide, hors périmètre ou lot déjà attribué.")
        else:
            if task_id not in known or known[task_id]["owner"] != "codex":
                blockers[task_id] = "Lot du backlog réservé à un autre responsable."
                continue
            mission["dependencies"] = known[task_id]["dependencies"]
            mission["priority"] = known[task_id]["priority"]
        if mission["issue"] in issue_numbers:
            raise Blocked("Un même ticket est associé à plusieurs tâches.")
        issue_numbers.add(mission["issue"])
        reason = fetch_approved_issue(mission)
        if mission.get("role") != "codex":
            reason = "Mandat local du rôle Codex absent."
        if master_state != "open":
            reason = "Issue maître fermée."
        if reason:
            blockers[task_id] = reason
    return missions, blockers


def discover_queue(backlog, master_state):
    pages = json.loads(checked([
        "gh", "api", "--paginate", "--slurp",
        f"repos/{REPO}/issues?state=open&labels=codex-local%2Fmission&per_page=100",
    ]))
    candidates, requests, blockers = [], [], {}
    for issue in (issue for page in pages for issue in page):
        if not is_eligible_mission(issue, "codex-local/mission") or issue.get("user", {}).get("login") != "khalidd692":
            continue
        entries = re.findall(r"^tel99-contract:v1 (.+)$", issue.get("body") or "", re.M)
        if not entries:
            continue  # Historical private manifests, including #109.
        try:
            if len(entries) != 1 or len(entries[0]) > 8000:
                raise ValueError("contrat ambigu")
            spec = json.loads(entries[0])
            if (type(spec) is not dict or spec.get("issue") != issue.get("number")
                    or spec.get("kind") not in {"code", "native"}
                    or (spec.get("kind") == "code" and not spec.get("routing_profile"))):
                raise ValueError("contrat incomplet")
            admitted, denied = admit_missions([spec], backlog, master_state=master_state)
            candidates.extend(admitted)
            blockers.update(denied)
            if denied:
                requests.append({"issue": spec["issue"], "id": spec["id"], "reason": denied[spec["id"]]})
        except (Blocked, TypeError, ValueError, KeyError):
            requests.append({"issue": issue["number"], "reason": "Contrat structuré invalide."})
    counts = {item["id"]: 0 for item in candidates}
    for item in candidates:
        counts[item["id"]] += 1
    return [item for item in candidates if counts[item["id"]] == 1], blockers, requests


def issue_comments(number):
    pages = json.loads(checked([
        "gh", "api", "--paginate", "--slurp",
        f"repos/{REPO}/issues/{number}/comments?per_page=100",
    ]))
    return [comment for page in pages for comment in page]


def fetch_approved_issue(mission):
    number = mission["issue"]
    try:
        issue = json.loads(checked(["gh", "api", f"repos/{REPO}/issues/{number}"]))
        reason = validate_issue(issue, mission)
        if reason:
            return reason
        if is_eligible_mission(issue, "tel99-mission"):
            return "Le ticket figure aussi dans la file OpenHands."
        approved, _ = approval_is_authorized(issue, {"khalidd692"})
        if not approved or not has_authenticated_approval(
            issue, issue_comments(number), now=datetime.now(timezone.utc),
        ):
            return "Approbation GitHub #104 authentifiée et liée au contenu absente ou expirée."
        if mission.get("kind") in {"code", "native"}:
            fingerprint = native.native_digest(mission) if mission["kind"] == "native" else contract_digest(mission)
            expected = f"codex-contract-sha256: {fingerprint}"
            rows = [line.strip() for line in issue["body"].splitlines()
                    if line.strip().lower().startswith("codex-contract-sha256:")]
            if rows != [expected]:
                return "Le mandat GitHub ne couvre pas exactement le contrat de code local."
    except (Blocked, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return "Issue de mission ou approbation GitHub indisponible."
    return None


def check_code_conflicts(mission):
    def fetch(resource):
        pages = json.loads(checked([
            "gh", "api", "--paginate", "--slurp", f"repos/{REPO}/{resource}",
        ]))
        return [item for page in pages for item in page]

    for pull in fetch("pulls?state=open&per_page=100"):
        if pull["number"] in {104, 105}:
            continue
        files = fetch(f"pulls/{pull['number']}/files?per_page=100")
        if len(files) >= 3000 or any(
            item.get(name) in mission["files"] for item in files
            for name in ("filename", "previous_filename")
        ):
            raise Blocked(f"Conflit de fichiers possible avec la PR #{pull['number']}.")


def dependency_evidence(missions):
    wanted = {dep for mission in missions for dep in mission.get("dependencies", [])}
    proofs = {}
    if not wanted:
        return proofs

    def fetch(resource):
        return json.loads(checked(["gh", "api", f"repos/{REPO}/{resource}"]))

    descriptors = {}
    for mission in missions:
        for task, descriptor in mission.get("dependency_evidence", {}).items():
            if task in descriptors and descriptors[task] != descriptor:
                raise Blocked(f"Politiques de preuve ambiguës pour {task}")
            descriptors[task] = descriptor
    for task in wanted & descriptors.keys():
        descriptor = descriptors[task]
        try:
            issue = descriptor["issue"]
            if type(issue) is not int or issue < 1:
                continue
            mission_issue = fetch(f"issues/{issue}")
            body = mission_issue.get("body") or ""
            if (
                digest(body) != descriptor["issue_sha256"]
                or mission_digest(mission_content(mission_issue)) != descriptor["mission_digest"]
            ):
                continue
            proof = accepted_proof(
                descriptor, repository=REPO, mission_body=body, fetch=fetch,
                comments=issue_comments(94),
            )
            if proof:
                proofs[task] = proof
        except (Blocked, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            continue
    return proofs


def save_admission(supervisor, tasks, missions, blockers, proofs):
    approved = {mission["id"] for mission in missions}
    rows = []
    for task in tasks:
        task_id = task["id"]
        missing = [dep for dep in task["dependencies"] if dep not in proofs]
        reasons = []
        if task_id not in approved:
            reasons.append("Réservée au propriétaire" if task["owner"] == "owner"
                           else "Aucun mandat d’exécution Codex approuvé pour ce lot")
        if task_id in blockers:
            reasons.append(blockers[task_id])
        if missing:
            reasons.append("Acceptation indépendante manquante pour " + ", ".join(missing))
        rows.append({**task, "unverified_dependencies": missing, "reasons": reasons})
    try:
        coordination_backend()
        coordination_status = "CONFIGURED_UNVERIFIED"
    except CoordinationUnavailable:
        coordination_status = "WAITING_COORDINATION"
    supervisor.store.put("github/admission", {
        "at": utcnow_iso(), "coordination": coordination_status, "tasks": rows, "proofs": proofs,
    })


def report_prepared(supervisor, missions):
    for mission in missions:
        saved = supervisor.state(mission)
        status = saved.get("status")
        sha = saved.get("commit")
        terminal = status in {"PREPARED", "BLOCKED"}
        waiting = {"WAITING_COORDINATION", "WAITING_QUOTA", "WAITING_DEPENDENCY", "AWAITING_HUMAN"}
        if not terminal and status not in waiting:
            continue
        if status == "PREPARED" and (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)):
            continue
        approval = digest(json.dumps(mission, sort_keys=True))
        identity = sha if status == "PREPARED" else approval
        marker = f"<!-- tel99-windows-{status.lower()}:{mission['issue']}:{identity} -->"
        report_key = f"github/report-{mission['issue']}-{identity}" + ("" if status == "PREPARED" else f"-{status}")
        if supervisor.store.get(report_key):
            continue
        try:
            # A local checkpoint can survive a ticket edit or an ID collision.
            # Publish only the result still bound to this exact shared claim.
            if terminal:
                shared = coordination_backend().read(f"codex-windows/{mission['id']}")
                if (
                    not isinstance(shared, dict) or shared.get("status") != status
                    or shared.get("issue") != mission["issue"] or shared.get("commit") != sha
                    or shared.get("approval") != approval
                ):
                    print(f"Rapport GitHub bloqué pour #{mission['issue']}: réservation différente.", flush=True)
                    continue
            body = marker + f"\n#{mission['issue']} — {status}."
            if status == "PREPARED":
                body += (f" SHA `{sha}`. {saved.get('test_count', 0)} tests ou critères vérifiés "
                         "localement. Le verdict externe reste à établir.")
            evidence = supervisor.store.get(f"native-results/{mission['id']}")
            if terminal and evidence:
                # The store only contains the allowlisted result, never the full worker report.
                fence = chr(96) * 3
                body += f"\n\n{fence}json\n" + json.dumps(evidence, ensure_ascii=True) + f"\n{fence}"
            if not any(marker in comment.get("body", "") and comment.get("user", {}).get("login") == "khalidd692"
                       for comment in issue_comments(94)):
                checked([
                    "gh", "api", "--method", "POST", f"repos/{REPO}/issues/94/comments",
                    "-f", "body=" + body,
                ])
            supervisor.store.put(report_key, {"status": "PUBLISHED"})
        except (Blocked, CoordinationUnavailable, OSError, ValueError, subprocess.TimeoutExpired):
            print(f"Rapport GitHub en attente pour #{mission['issue']}.", flush=True)


@contextmanager
def heartbeat(supervisor):
    cancelled = Event()

    def save():
        with supervisor.live_lock:
            row = dict(supervisor.live)
        supervisor.store.put("github/heartbeat", {"PID": os.getpid(), "HEARTBEAT": utcnow_iso(), **row})

    def pulse():
        while not cancelled.wait(10):
            save()

    save()
    worker = Thread(target=pulse, daemon=True)
    worker.start()
    try:
        yield
    finally:
        cancelled.set()
        worker.join()
        supervisor.observe(STATE="STOPPED", ACTIVE_TASK=None)
        save()


def heartbeat_status(github):
    row = FileStore(github / "ledger").get("github/heartbeat")
    if not isinstance(row, dict):
        return {"STATE": "UNKNOWN", "QUOTA": None}
    if row.get("STATE") != "STOPPED":
        try:
            last = datetime.fromisoformat(row["HEARTBEAT"])
            fresh = 0 <= (datetime.now(timezone.utc) - last).total_seconds() <= 30
        except (KeyError, TypeError, ValueError):
            fresh = False
        if not fresh:
            row.update(STATE="UNKNOWN", CLAIM="RECHECK", ACTIVE_TASK=None, BLOCKER="HEARTBEAT_STALE")
    return row


def accept_stop(root):
    signal = root / "stop.request"
    if not signal.exists():
        return False
    signal.replace(root / f"stop-consumed-{time.time_ns()}.request")
    print("Demande d’arrêt reçue. Registre conservé.", flush=True)
    return True


def idle_wait(root, deadline):
    until = time.monotonic() + 60
    if deadline is not None:
        until = min(until, deadline)
    while not (root / "stop.request").exists():
        remaining = until - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(1, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--code-demo", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--await-issue", type=int)
    parser.add_argument("--session-minutes", type=int, choices=range(1, 181))
    parser.add_argument("--status-read", action="store_true")
    parser.add_argument("--request-stop", action="store_true")
    parser.add_argument("--demo-attempt", type=int, default=1, choices=range(1, 10))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--approvals", type=Path)
    parser.add_argument("--codex", default=shutil.which("codex.exe"))
    args = parser.parse_args()
    github = STATE / "github"
    if args.status_read:
        print(json.dumps(heartbeat_status(github), ensure_ascii=True))
        return 0
    if args.request_stop:
        github.mkdir(parents=True, exist_ok=True)
        (github / "stop.request").touch(exist_ok=True)
        print("Arrêt demandé entre les missions.")
        return 0
    if args.preflight:
        try:
            backend = coordination_backend()
            backend.probe()
        except CoordinationUnavailable as exc:
            print(f"BLOCKED_KV: {exc}", file=sys.stderr, flush=True)
            return 2
        if isinstance(backend, UpstashCoordination):
            print("KV_CAS_READY: collision, réservation et fencing vérifiés sur Upstash.", flush=True)
        else:
            print("KV_READ_READY: l’écriture CAS reste à contrôler par une prise réelle.", flush=True)
        return 0
    demo = args.demo or args.code_demo
    demo_dir = "code-demo" if args.code_demo else "demo"
    if args.demo_attempt != 1:
        demo_dir += f"-{args.demo_attempt}"
    root = STATE / (demo_dir if demo else "github")
    approvals = args.approvals or STATE / "approvals.json"
    root.mkdir(parents=True, exist_ok=True)
    supervisor = Supervisor(root, args.codex, demo=demo)
    deadline = time.monotonic() + 60 * args.session_minutes if args.session_minutes else None
    supervisor.deadline = deadline
    try:
        shared_local_lock = STATE / "github" / "supervisor.lock"
        shared_local_lock.parent.mkdir(parents=True, exist_ok=True)
        if args.discover_only:
            tasks, state = sync_github(supervisor)
            missions, blockers, requests = discover_queue(tasks, state)
            print(json.dumps({"discovered": len(missions), "blockers": blockers, "requests": requests},
                             ensure_ascii=True))
            return 0
        with exclusive(shared_local_lock), heartbeat(supervisor):
            while True:
                if not demo and accept_stop(root):
                    return 0
                if deadline is not None and time.monotonic() >= deadline:
                    return 0
                try:
                    if demo:
                        missions, blockers = (synthetic_missions() if args.code_demo else demo_missions()), {}
                        proofs = {}
                    else:
                        tasks, state = sync_github(supervisor)
                        if args.approvals or approvals.is_file():
                            missions, blockers = approved_queue(approvals, tasks, master_state=state)
                        else:
                            missions, blockers, requests = discover_queue(tasks, state)
                            supervisor.store.put("github/approval-requests", requests)
                        proofs = dependency_evidence(missions)
                        save_admission(supervisor, tasks, missions, blockers, proofs)
                        if args.await_issue:
                            missions = [item for item in missions if item["issue"] == args.await_issue]
                            if len(missions) != 1 or state != "open":
                                raise Blocked("Le ticket d’attente n’est plus admissible à la découverte.")
                            if missions[0]["expires_at"] <= utcnow_iso():
                                raise Blocked("Délai d’approbation dépassé.")
                            if missions[0]["id"] in blockers:
                                supervisor.observe(STATE="AWAITING_HUMAN", BLOCKER="APPROVAL",
                                                   NEXT=missions[0]["id"])
                                print(f"AWAITING_HUMAN #{args.await_issue}: "
                                      f"{blockers[missions[0]['id']]}", flush=True)
                                idle_wait(root, deadline)
                                continue
                        ready = sum(mission["id"] not in blockers for mission in missions)
                        supervisor.observe(NEXT=next((mission["id"] for mission in missions
                                                     if mission["id"] not in blockers and
                                                     supervisor.state(mission).get("status") not in
                                                     {"PREPARED", "ACCEPTED", "BLOCKED", "FAILED", "INTERRUPTED"}), None))
                        print(f"GitHub #94 : {len(tasks)} tâches, {len(missions)} contrats, {ready} approuvés", flush=True)
                    if any(mission.get("kind") != "native" and mission["id"] not in blockers
                           for mission in missions):
                        if not args.codex:
                            raise Blocked("codex.exe introuvable.")
                        login = call([args.codex, "login", "status"], env=model_environment())
                        if login.returncode or "Logged in using ChatGPT" not in (
                            login.stdout + "\n" + login.stderr
                        ).splitlines():
                            raise Blocked("Authentification ChatGPT requise.")
                    continued = not missions or supervisor.run(missions, blockers, proofs)
                    if not demo:
                        report_prepared(supervisor, missions)
                        if accept_stop(root):
                            return 0
                    if not continued:
                        return 2
                    if args.await_issue and missions:
                        # An unavailable lease before any worker ran is safe
                        # to retry. Checkpoints with possible work are held.
                        saved = supervisor.state(missions[0])
                        if saved.get("status") in {"WAITING_COORDINATION", "WAITING_DEPENDENCY"}:
                            idle_wait(root, deadline)
                            continue
                    if demo:
                        return 0 if all(
                            supervisor.state(m).get("status") == "ACCEPTED" for m in missions
                        ) else 2
                    if args.once or args.await_issue:
                        return 0
                except (Blocked, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                    print(f"BLOCKED: {exc}", file=sys.stderr, flush=True)
                    if demo or args.once or args.await_issue:
                        return 2
                idle_wait(root, deadline)
    except KeyboardInterrupt:
        return 130
    except Blocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
