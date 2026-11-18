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
from threading import Thread
import time

from policy import (
    approval_is_authorized, has_authenticated_approval, is_eligible_mission,
    mission_content, mission_digest, utcnow_iso,
)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol.store import FileStore
from local_coordination import CoordinationUnavailable, SharedCoordination, accepted_proof

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
    if digest(issue.get("body") or "") != approval["issue_sha256"]:
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

    def checkpoint(self, mission, status, **details):
        task_id = mission["id"]
        row = {"id": task_id, "status": status, "at": utcnow_iso(), **details}
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
            saved = self.state(mission)
            stage = saved.get("status")
            if stage == "RUNNING":
                self.checkpoint(mission, "INTERRUPTED", reason="Exécution orpheline possible")
                continue
            if stage in {"ACCEPTED", "PREPARED", "INTERRUPTED", "FAILED", "BLOCKED"}:
                continue
            issue_blocker = blockers.get(mission["id"])
            if issue_blocker:
                self.checkpoint(mission, "AWAITING_HUMAN", reason=issue_blocker)
                continue
            unmet = [
                dep for dep in mission.get("dependencies", [])
                if dep not in dependency_proofs
                and (not self.demo or self.state({"id": dep}).get("status") != "ACCEPTED")
            ]
            if unmet:
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
        shared = SharedCoordination()
        approval = digest(json.dumps(mission, sort_keys=True))
        if saved.get("status") == "WORKER_EXITED":
            if saved["approval"] != approval:
                raise CoordinationUnavailable("L’approbation du checkpoint a changé.")
            owner = saved["shared_owner"]
            remote, finish = shared.resume(mission["id"], mission["issue"], approval, owner)
            fence = lambda: shared.owns(owner)
            if remote["status"] == "PREPARED":
                def fence():
                    raise CoordinationUnavailable("Le commit distant est déjà enregistré.")
            self.finalize(mission, saved["base"], saved["branch"], fence=fence, finish=finish)
            return
        # Check the quota before creating a durable reservation.
        limits = allowance(rate_snapshot(self.cli, self.root))
        with shared.claim(mission["id"], mission["issue"], approval) as (owner, finish):
            try:
                reason = fetch_approved_issue(mission)
                if reason:
                    raise Blocked(reason)
                self.execute(
                    mission, limits=limits, shared_owner=owner,
                    fence=lambda: shared.owns(owner), finish=finish,
                )
            except (Blocked, QuotaBlocked, ValueError):
                # These are known outcomes. A timeout or interruption leaves the
                # reservation in place until the worker is reconciled.
                finish("BLOCKED")
                raise

    def execute(self, mission, *, limits=None, shared_owner=None, fence=None, finish=None):
        task_id = mission["id"]
        if not re.fullmatch(r"[A-Z0-9-]{1,48}", task_id):
            raise Blocked("Identifiant de mission invalide.")
        bounds = limits if limits is not None else allowance(rate_snapshot(self.cli, self.root))
        workspace = self.root / task_id
        self.checkpoint(mission, "RUNNING", workspace=str(workspace), quota_used=bounds)
        if workspace.exists():
            raise Blocked("Espace existant. Réconciliation manuelle requise.")
        if self.demo:
            workspace.mkdir()
            checked(["git", "init", "-b", "pilot-base"], cwd=workspace)
            self.commit(workspace, "Initialiser le pilote isolé", empty=True)
        else:
            checked(["git", "clone", "--no-local", "--no-checkout", str(ROOT), str(workspace)])
            checked(["git", "remote", "remove", "origin"], cwd=workspace)
            checked(["git", "checkout", "--detach", mission["base_sha"]], cwd=workspace)
        branch = f"agents/codex-local/{task_id.lower()}"
        checked(["git", "checkout", "-b", branch], cwd=workspace)
        base = checked(["git", "rev-parse", "HEAD"], cwd=workspace)
        prompt = (
            "Mission TEL99 approuvée. Crée uniquement le fichier demandé dans ce checkout. "
            "Tu peux lire et tester dans le checkout. Ne fais aucun commit, aucun accès réseau, "
            "aucun ordre, aucune suppression et aucune opération GitHub. "
            f"Fichier: {mission['path']}\nObjectif approuvé: {mission['objective']}"
        )
        args = [
            self.cli, "-a", "never", "exec", "--ignore-user-config", "--ephemeral",
            "--sandbox", "workspace-write", "--disable", "hooks",
            "-c", "windows.sandbox=mxc",
            "-c", 'web_search="disabled"', "-c", "sandbox_workspace_write.network_access=false",
            "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
            "-c", "sandbox_workspace_write.exclude_slash_tmp=true", "-",
        ]
        if fence:
            fence()
        result = call(args, cwd=workspace, env=model_environment(), timeout=240, input_text=prompt)
        if result.returncode:
            if re.search(r"usage limit|rate.?limit|quota|too many requests", result.stderr, re.I):
                raise QuotaBlocked("Quota atteint pendant le run.")
            if re.search(r"sandbox setup|sandbox failed|access is denied|unauthorized", result.stderr, re.I):
                raise Blocked("Le CLI a signalé une erreur de sandbox ou d'accès.")
            raise Blocked(f"codex exec a quitté avec {result.returncode}")
        self.checkpoint(
            mission, "WORKER_EXITED", base=base, branch=branch, codex_exit=result.returncode,
            approval=digest(json.dumps(mission, sort_keys=True)), shared_owner=shared_owner,
        )
        self.finalize(mission, base, branch, fence=fence, finish=finish)

    def finalize(self, mission, base, branch, *, fence=None, finish=None):
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
    known = {task["id"]: task for task in backlog}
    missions = json.loads(path.read_text(encoding="utf-8-sig"))
    blockers = {}
    seen = set()
    issue_numbers = set()
    for mission in missions:
        task_id = mission["id"]
        if not re.fullmatch(r"[A-Z0-9-]{1,48}", task_id) or task_id in seen:
            raise Blocked("Identifiant absent, invalide ou dupliqué.")
        seen.add(task_id)
        if task_id not in known:
            raise Blocked("La mission doit correspondre au backlog de #94.")
        mission["dependencies"] = known[task_id]["dependencies"]
        mission["priority"] = known[task_id]["priority"]
        if (
            not re.fullmatch(r"docs/agents/codex-local-results/[a-z0-9-]+\.md", mission["path"])
            or not re.fullmatch(r"[0-9a-f]{40}", mission["base_sha"])
            or not re.fullmatch(r"[0-9a-f]{64}", mission["expected_sha256"])
            or type(mission["issue"]) is not int or mission["issue"] <= 0
        ):
            raise Blocked("Le pilote GitHub exige un nouveau fichier de preuve et un SHA de base épinglé.")
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
    except (Blocked, OSError, ValueError, subprocess.TimeoutExpired):
        return "Issue de mission ou approbation GitHub indisponible."
    return None


def dependency_evidence(missions):
    wanted = {dep for mission in missions for dep in mission["dependencies"]}
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
        SharedCoordination()
        coordination_status = "CONFIGURED_UNVERIFIED"
    except CoordinationUnavailable:
        coordination_status = "WAITING_COORDINATION"
    supervisor.store.put("github/admission", {
        "at": utcnow_iso(), "coordination": coordination_status, "tasks": rows, "proofs": proofs,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--demo-attempt", type=int, default=1, choices=range(1, 10))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--approvals", type=Path)
    parser.add_argument("--codex", default=shutil.which("codex.exe"))
    args = parser.parse_args()
    demo_dir = "demo" if args.demo_attempt == 1 else f"demo-{args.demo_attempt}"
    root = STATE / (demo_dir if args.demo else "github")
    approvals = args.approvals or STATE / "approvals.json"
    root.mkdir(parents=True, exist_ok=True)
    supervisor = Supervisor(root, args.codex, demo=args.demo)
    try:
        with exclusive(root / "supervisor.lock"):
            while True:
                try:
                    if args.demo:
                        missions, blockers = demo_missions(), {}
                        proofs = {}
                    else:
                        tasks, state = sync_github(supervisor)
                        if args.approvals or approvals.is_file():
                            missions, blockers = approved_queue(approvals, tasks, master_state=state)
                        else:
                            missions, blockers = [], {}
                        proofs = dependency_evidence(missions)
                        save_admission(supervisor, tasks, missions, blockers, proofs)
                        print(f"GitHub #94 : {len(tasks)} tâches, {len(missions)} approbations locales", flush=True)
                    if missions:
                        if not args.codex:
                            raise Blocked("codex.exe introuvable.")
                        login = call([args.codex, "login", "status"], env=model_environment())
                        if login.returncode or "Logged in using ChatGPT" not in (
                            login.stdout + "\n" + login.stderr
                        ).splitlines():
                            raise Blocked("Authentification ChatGPT requise.")
                        if not supervisor.run(missions, blockers, proofs):
                            return 2
                    if args.demo:
                        return 0 if all(
                            supervisor.state(m).get("status") == "ACCEPTED" for m in missions
                        ) else 2
                    if args.once:
                        return 0
                except (Blocked, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                    print(f"BLOCKED: {exc}", file=sys.stderr, flush=True)
                    if args.demo or args.once:
                        return 2
                time.sleep(60)
    except KeyboardInterrupt:
        return 130
    except Blocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
