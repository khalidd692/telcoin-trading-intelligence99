"""TEL99 Autonomous Multi-Agent Project Runner (REUSE-FIRST, zero new supervisor).

Connects `launch-tel99.ps1` directly to existing TEL99 autonomous infrastructure:
- `project_kit` (isolated project workspace, state, memory, artifacts)
- `autonomy_runtime.Runtime.run_queue` + `project-file` sealed contracts (CAS claims, Inbox ACKs, zero replay)
- `mission_planner.assess_and_decompose_mission` + `TopologicalSorter` DAG ordering
- `specialist_dispatch` (all 12 official TEL99 roles selected on demand)
- `context_engine` (AST code graph + SQLite FTS5 hybrid memory + structured JSON validation)
- `mentor_curriculum` (2-layer generalist + specialized role Skill context)
- `local_deterministic_tools` (deterministic security gate + atomic file-locked JSON)
- `scripts.agents.native.sandbox` + `env_doctor.DEFAULT_SANDBOX_IMAGE` (OS Docker sandbox, --network none, RO mount)
- `smart_repair` (root-cause error diagnostics, bounded diff, SHA-256 anti-repetition)
- `metacognition` (`TrajectoryRecorder`, `FailureLibrary`, secret scrubbing)
- `ollama_native.OllamaNativeProvider` (concurrence=1 CAS lease) + optional free Groq mentors (`--hybrid`, $0.00)

Domain-agnostic: contains ZERO project-specific code templates. The agents themselves design,
code, test, independently verify in an OS sandbox, repair, learn, and deliver any authorized local project.
"""
from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from graphlib import CycleError, TopologicalSorter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents import project_kit, specialist_dispatch, team_config
from scripts.agents.automation import (
    autonomy_runtime,
    context_engine,
    env_doctor,
    ide_coordination,
    local_deterministic_tools,
    mentor_curriculum,
    metacognition,
    mission_planner,
    ollama_native,
    provider_router,
    smart_repair,
)
from scripts.agents.automation.autonomy_runtime import Runtime, fingerprint, seal, validate_project_file_contract
from scripts.agents.intelligence.memory import Entry, MemoryStore
from scripts.agents.native import sandbox as native_sandbox
from scripts.agents.native.mission import MissionError
from scripts.agents.native.provider import ProviderError

LOCAL_MODEL = "gemma4:e4b-tel99-8k"
SKILLS_DIR = ROOT / ".agents" / "skills"
SHARED_MEM_DIR = Path.home() / "Desktop" / "TEL99_BENCHMARK_120_STATE" / "memory"
DEFAULT_SANDBOX_IMAGE = env_doctor.DEFAULT_SANDBOX_IMAGE
RESERVED_PROJECT_TOP_DIRS = frozenset({
    "state", "memory", "artifacts", ".git", "project.json", "__pycache__",
})
SUPPORTED_EXTENSIONS = frozenset({
    ".py", ".html", ".css", ".js", ".ps1", ".md", ".json", ".txt", ".csv", ".toml", ".yml", ".yaml",
})
MAX_PLAN_MISSIONS = 36
RUNTIME_BATCH_SIZE = 18
MAX_REPLAN_ROUNDS = 2
MAX_INFRA_RETRIES = 2
_SANDBOX_OUTPUT_LIMIT = 262_144


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _slugify_project(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)[:44]
    if not slug or slug == "synthetic" or len(slug) < 2:
        slug = "tel99-project"
    return slug


def _safe_mission_id(raw: str, idx: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9-]+", "-", str(raw or "")).strip("-")[:40]
    return cleaned or f"m-{idx:02d}"


def _scope_config_hash(*, explicit_specialist: str | None, confidential: bool) -> str:
    payload = json.dumps(
        {"explicit_specialist": explicit_specialist or "", "confidential": bool(confidential)},
        sort_keys=True,
    )
    return _sha256_text(payload)


def _is_forbidden_workspace(target: Path) -> str | None:
    """Block protected system folders or the TEL99 supervisor repo itself as a target project."""
    resolved = target.resolve()
    if resolved == ROOT.resolve() or ROOT.resolve() in resolved.parents:
        return "target project directory must be isolated outside the TEL99 supervisor repository"
    parts_low = [p.lower() for p in resolved.parts]
    if len(parts_low) <= 2:
        return "refusing filesystem root or top-level drive directory"
    if any(p in {"windows", "system32", "program files", "program files (x86)", ".git"} for p in parts_low):
        return "refusing protected system or git directory"
    return None


def ensure_isolated_project_kit(project_dir: Path, *, project_slug: str | None = None) -> project_kit.ProjectKit:
    """Load an existing isolated ProjectKit or scaffold a brand-new one safely."""
    err = _is_forbidden_workspace(project_dir)
    if err:
        raise ValueError(err)
    project_dir = project_dir.resolve()
    if (project_dir / "project.json").is_file():
        return project_kit.load(project_dir)

    slug = _slugify_project(project_slug or project_dir.name)
    all_roles = list(team_config.role_catalog().keys())
    profile = project_kit.scaffold_profile(
        slug,
        f"local/{slug}",
        roles=all_roles,
    )
    if project_dir.exists():
        for sub in ("state", "memory", "artifacts"):
            (project_dir / sub).mkdir(parents=True, exist_ok=True)
        local_deterministic_tools.write_json_atomic_locked(project_dir / "project.json", profile)
        return project_kit.load(project_dir)
    return project_kit.install(project_dir, profile)


# ---------------------------------------------------------------------------
# OS-level Docker Sandbox (reusing scripts.agents.native.sandbox)
# ---------------------------------------------------------------------------

def check_docker_sandbox_ready(image: str = DEFAULT_SANDBOX_IMAGE) -> tuple[bool, str]:
    """Verify local Docker daemon + pinned SHA-256 Python image are ready (fail-closed)."""
    if not native_sandbox.valid_image(image):
        return False, "sandbox image must be pinned by a sha256 digest"
    try:
        native_sandbox.require_local_image(image)
        return True, "ok"
    except MissionError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"docker probe error: {type(exc).__name__}"


def _copy_deliverables_for_sandbox(project_root: Path, dest_dir: Path) -> None:
    """Copy ONLY project deliverables into a clean staging directory (excludes state/memory/artifacts/.git)."""
    root = project_root.resolve()
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if not rel.parts:
            continue
        if rel.parts[0].lower() in RESERVED_PROJECT_TOP_DIRS or "__pycache__" in rel.parts:
            continue
        if p.is_symlink() or os.path.islink(p):
            continue
        target = dest_dir / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif p.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            try:
                target.chmod(0o644)
            except OSError:
                pass


def run_python_in_docker_sandbox(
    project_root: Path,
    python_args: list[str],
    *,
    timeout: int = 40,
    image: str = DEFAULT_SANDBOX_IMAGE,
) -> dict[str, Any]:
    """Execute untrusted project Python code inside an isolated local Docker container.

    Security controls:
    - Pinned SHA-256 image (`--pull never`), fail-closed if Docker or image unavailable.
    - `--network none` (isolated container loopback 127.0.0.1 only; zero outbound/host network).
    - Host staging dir mounted STRICTLY READ-ONLY at `/src`; container executes inside RAM tmpfs `/work`.
    - `--read-only` rootfs, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--user 65534:65534`.
    - `--pids-limit 64`, `--memory 256m`, `--cpus 1`, scrubbed env, forced `docker rm -f` on timeout.
    """
    ready, reason = check_docker_sandbox_ready(image)
    if not ready:
        return {
            "sandbox_used": False,
            "sandbox_unavailable": True,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": f"sandbox_unavailable: {reason}",
        }

    name = "tel99-proj-" + uuid.uuid4().hex
    bootstrap = (
        "import os, shutil, subprocess, sys\n"
        "dst = '/work/proj'\n"
        "os.makedirs(dst, exist_ok=True)\n"
        "for r, dirs, files in os.walk('/src'):\n"
        "    rel = os.path.relpath(r, '/src')\n"
        "    out_dir = dst if rel == '.' else os.path.join(dst, rel)\n"
        "    os.makedirs(out_dir, exist_ok=True)\n"
        "    for fn in files:\n"
        "        shutil.copyfile(os.path.join(r, fn), os.path.join(out_dir, fn))\n"
        "os.chdir(dst)\n"
        "env = {'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'), "
        "'PYTHONPATH': dst, 'PYTHONUTF8': '1', 'HOME': '/tmp', 'TMPDIR': '/tmp'}\n"
        "p = subprocess.run([sys.executable, '-B', *sys.argv[1:]], cwd=dst, env=env)\n"
        "raise SystemExit(p.returncode)\n"
    )

    with tempfile.TemporaryDirectory(prefix="tel99-proj-sbx-") as tmp:
        tmp_root = Path(tmp)
        cfg_dir = tmp_root / "config"
        src_dir = tmp_root / "src"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        src_dir.mkdir(parents=True, exist_ok=True)
        _copy_deliverables_for_sandbox(project_root, src_dir)
        if "," in str(src_dir):
            return {
                "sandbox_used": False,
                "sandbox_unavailable": True,
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "error": "sandbox_unavailable: staging path contains comma",
            }
        docker, env = native_sandbox._local_docker(cfg_dir)
        cmd = [
            *docker, "run", "--name", name, "--rm", "--pull", "never",
            "--network", "none", "--read-only", "--log-driver", "none",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", "65534:65534", "--pids-limit", "64",
            "--memory", "256m", "--cpus", "1",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m,mode=1777",
            "--tmpfs", "/work:rw,nosuid,nodev,size=64m,mode=1777",
            "--mount", f"type=bind,source={src_dir},target=/src,readonly",
            "--entrypoint", "python", image, "-I", "-B", "-c", bootstrap, *python_args,
        ]
        try:
            with subprocess.Popen(
                cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ) as client, ThreadPoolExecutor(2) as pool:
                f_out = pool.submit(client.stdout.read, _SANDBOX_OUTPUT_LIMIT + 1)
                f_err = pool.submit(client.stderr.read, _SANDBOX_OUTPUT_LIMIT + 1)
                try:
                    raw_out = f_out.result(timeout=timeout)
                    raw_err = f_err.result(timeout=timeout)
                    rc = client.wait(timeout=5)
                except (TimeoutError, subprocess.TimeoutExpired, KeyboardInterrupt):
                    client.kill()
                    client.wait()
                    subprocess.run(
                        [*docker, "rm", "-f", name], env=env, check=False,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                    )
                    return {
                        "sandbox_used": True,
                        "sandbox_unavailable": False,
                        "returncode": -1,
                        "stdout": "",
                        "stderr": "",
                        "error": f"sandbox execution timed out after {timeout}s",
                    }
            return {
                "sandbox_used": True,
                "sandbox_unavailable": False,
                "returncode": rc,
                "stdout": raw_out[:_SANDBOX_OUTPUT_LIMIT].decode("utf-8", errors="replace"),
                "stderr": raw_err[:_SANDBOX_OUTPUT_LIMIT].decode("utf-8", errors="replace"),
                "error": None,
            }
        except OSError as exc:
            return {
                "sandbox_used": False,
                "sandbox_unavailable": True,
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "error": f"sandbox_unavailable: {exc}",
            }


def _exec_python_isolated(
    project_root: Path,
    python_args: list[str],
    *,
    timeout: int = 35,
    require_sandbox: bool = True,
    sandbox_image: str = DEFAULT_SANDBOX_IMAGE,
) -> dict[str, Any]:
    """Run Python inside Docker sandbox when required; fail closed if sandbox unavailable."""
    if require_sandbox:
        return run_python_in_docker_sandbox(project_root, python_args, timeout=timeout, image=sandbox_image)
    env = provider_router.scrubbed_env()
    env["PYTHONPATH"] = str(project_root.resolve())
    env["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, "-B", *python_args],
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "sandbox_used": False,
            "sandbox_unavailable": False,
            "returncode": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "error": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "sandbox_used": False,
            "sandbox_unavailable": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": f"host subprocess timed out after {timeout}s",
        }


# ---------------------------------------------------------------------------
# Requirements Manifest & Independent Plan Verification
# ---------------------------------------------------------------------------

# Domain-agnostic business capability extraction rules (goal text -> behavioral requirements)
_BUSINESS_CAPABILITY_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str], ...] = (
    (
        "crud_create",
        ("création", "creation", "ajouter", "ajout", "create", "add ", "nouvelle", "nouveau", "enregistrer", "crud"),
        ("create", "add", "insert", "new", "post", "append", "save"),
        "Create/add domain records with validated fields",
    ),
    (
        "crud_update",
        ("modification", "modifier", "mise à jour", "mise a jour", "update", "edit", "éditer", "crud"),
        ("update", "edit", "modify", "patch", "put"),
        "Modify/update existing domain records safely",
    ),
    (
        "crud_delete",
        ("suppression", "supprimer", "effacer", "delete", "remove", "crud"),
        ("delete", "remove", "del_", "pop", "do_delete"),
        "Delete existing domain records cleanly",
    ),
    (
        "search_filter",
        ("filtrage", "filtrer", "filtre", "filter", "recherche", "rechercher", "search", "par tag", "par catégorie", "par categorie"),
        ("filter", "search", "query", "find", "tag", "category", "categorie"),
        "Search and filter records by criteria/category/tag",
    ),
    (
        "summary_stats",
        ("synthèse", "synthese", "résumé", "resume", "summary", "solde", "balance", "mensuel", "total", "statistique"),
        ("summary", "synthese", "balance", "solde", "total", "stats", "monthly", "mensuel"),
        "Compute accurate domain summaries/totals/balances",
    ),
    (
        "persistence",
        ("persistance", "persistant", "sauvegarde", "sauvegardé", "sauvegardee", "stockage", "storage", "sqlite", ".json"),
        ("json.dump", "json.dumps", "json.load", "write_text", "sqlite3", "save", "load", "persist"),
        "Persist and reload domain data durably across restarts",
    ),
    (
        "input_validation",
        ("validation", "valider", "rejet", "rejetant", "bool", "invalide", "montant", "date", "vide", "négatif", "negatif"),
        ("isinstance", "valueerror", "assertraises", "400", "invalid", "bool"),
        "Reject invalid/empty/bool/out-of-range inputs cleanly (positive + negative tests)",
    ),
)


def build_requirements_manifest(
    goal_text: str,
    *,
    project_slug: str,
    explicit_specialist: str | None = None,
) -> dict[str, Any]:
    """Deterministically extract a persistent technical + business Requirements Manifest BEFORE planning."""
    raw = str(goal_text or "").strip()
    low = raw.lower()
    reqs: list[dict[str, Any]] = []

    def _spec(role_key: str) -> str:
        if explicit_specialist:
            return specialist_dispatch.resolve_specialist(explicit_specialist).name
        return specialist_dispatch.resolve_specialist(role_key).name

    reqs.append({
        "id": "REQ-CORE",
        "source_text": raw[:320] or f"Core implementation for {project_slug}",
        "mandatory": True,
        "specialist": _spec("development"),
        "deliverables": [],
        "expected_kind": "python_core",
        "acceptance_criteria": [
            "At least one clean Python core deliverable parses, passes security gate, and imports cleanly in sandbox"
        ],
        "verification_method": "ast_security_and_sandbox_import",
        "status": "PENDING",
        "evidence": [],
    })

    needs_web = any(tok in low for tok in ("html", "interface web", "frontend", "navigateur", "dashboard", "web/", "page web"))
    needs_css = needs_web or any(tok in low for tok in ("css", "styles.css", "responsive"))
    needs_js = needs_web or any(tok in low for tok in ("app.js", "javascript", ".js", "fetch"))
    needs_server = needs_web or any(tok in low for tok in ("serveur", "server", "http", "api", "rest", "route", "127.0.0.1"))
    needs_ps1 = any(tok in low for tok in ("start.ps1", "powershell", ".ps1", "lancement"))
    needs_readme = any(tok in low for tok in ("readme", "documentation", "notice", "guide"))

    if needs_server:
        reqs.append({
            "id": "REQ-HTTP-SERVER",
            "source_text": "Local loopback HTTP server/API (127.0.0.1 only)",
            "mandatory": True,
            "specialist": _spec("development"),
            "deliverables": [],
            "expected_kind": "http_server",
            "acceptance_criteria": [
                "Loopback server starts inside sandbox, answers HTTP 200 on /, serves static assets, answers 200 on GET API routes, 4xx on invalid JSON POST, and 404 on unknown route"
            ],
            "verification_method": "docker_sandbox_http_e2e",
            "status": "PENDING",
            "evidence": [],
        })
    if needs_web:
        reqs.append({
            "id": "REQ-WEB-HTML",
            "source_text": "Responsive HTML5 frontend without inline <script> or inline handlers",
            "mandatory": True,
            "specialist": _spec("mobile"),
            "deliverables": [],
            "expected_kind": "html",
            "acceptance_criteria": ["Valid HTML5 structure, CSP-safe static checks, zero inline script/onclick"],
            "verification_method": "html_static_and_http_e2e",
            "status": "PENDING",
            "evidence": [],
        })
    if needs_css:
        reqs.append({
            "id": "REQ-WEB-CSS",
            "source_text": "Stylesheet with balanced braces and responsive layout",
            "mandatory": True,
            "specialist": _spec("mobile"),
            "deliverables": [],
            "expected_kind": "css",
            "acceptance_criteria": ["Balanced CSS braces, non-trivial styling >= 250 chars"],
            "verification_method": "css_static_check",
            "status": "PENDING",
            "evidence": [],
        })
    if needs_js:
        reqs.append({
            "id": "REQ-WEB-JS",
            "source_text": "Safe vanilla JavaScript frontend without innerHTML/eval/document.write",
            "mandatory": True,
            "specialist": _spec("mobile"),
            "deliverables": [],
            "expected_kind": "js",
            "acceptance_criteria": ["Passes node --check and zero unsafe DOM/JS sinks"],
            "verification_method": "node_check_and_static_security",
            "status": "PENDING",
            "evidence": [],
        })
    if needs_ps1:
        reqs.append({
            "id": "REQ-STARTUP-PS1",
            "source_text": "Windows PowerShell startup script (loopback 127.0.0.1 only)",
            "mandatory": True,
            "specialist": _spec("release"),
            "deliverables": [],
            "expected_kind": "ps1",
            "acceptance_criteria": ["Parses cleanly with PowerShell Parser, zero 0.0.0.0 / Invoke-Expression"],
            "verification_method": "powershell_parser_check",
            "status": "PENDING",
            "evidence": [],
        })
    if needs_readme:
        reqs.append({
            "id": "REQ-DOC-README",
            "source_text": "Clear README documentation covering features, startup, and tests",
            "mandatory": True,
            "specialist": _spec("documentation"),
            "deliverables": [],
            "expected_kind": "md",
            "acceptance_criteria": ["README.md present and >= 180 chars"],
            "verification_method": "doc_non_empty",
            "status": "PENDING",
            "evidence": [],
        })

    # Always mandatory for code projects: automated tests + deterministic security
    reqs.append({
        "id": "REQ-TESTS",
        "source_text": "Automated unittest suite with real assertions executed in isolated sandbox",
        "mandatory": True,
        "specialist": _spec("quality"),
        "deliverables": [],
        "expected_kind": "tests",
        "acceptance_criteria": ["At least one tests/test_*.py file executes >= 1 passing unittest inside sandbox"],
        "verification_method": "docker_sandbox_unittest",
        "status": "PENDING",
        "evidence": [],
    })
    reqs.append({
        "id": "REQ-SECURITY",
        "source_text": "Zero forbidden primitives (eval/exec/shell=True/0.0.0.0/innerHTML/secrets), strict scope isolation",
        "mandatory": True,
        "specialist": _spec("security"),
        "deliverables": [],
        "expected_kind": "security",
        "acceptance_criteria": ["All deliverables pass deterministic security gate and scope confinement"],
        "verification_method": "deterministic_security_gate",
        "status": "PENDING",
        "evidence": [],
    })

    # Extract concrete business capability requirements from the natural-language goal
    for cap_key, trigger_terms, code_tokens, desc in _BUSINESS_CAPABILITY_RULES:
        if any(term in low for term in trigger_terms):
            reqs.append({
                "id": f"REQ-BIZ-{cap_key.upper()}",
                "source_text": desc,
                "mandatory": True,
                "specialist": _spec("development"),
                "deliverables": [],
                "expected_kind": "business_capability",
                "capability": cap_key,
                "behavior_tokens": list(code_tokens),
                "requires_negative_test": cap_key == "input_validation",
                "acceptance_criteria": [
                    f"Business capability `{cap_key}` is implemented in project code AND covered by executed passing unit tests"
                ],
                "verification_method": "behavioral_code_and_test_matrix",
                "status": "PENDING",
                "evidence": [],
            })

    # Extract explicit named filenames mentioned in the user's goal
    explicit_files: list[str] = []
    for m in re.finditer(r"(?<![A-Za-z0-9_./-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:py|html|css|js|ps1|md|json|txt|csv))(?![A-Za-z0-9_-])", raw):
        cand = m.group(1).strip()
        if cand.startswith("http") or cand in explicit_files:
            continue
        if len(cand) <= 80:
            explicit_files.append(cand)
    for idx, fname in enumerate(explicit_files[:12], 1):
        reqs.append({
            "id": f"REQ-FILE-{idx:02d}",
            "source_text": f"Explicitly requested deliverable `{fname}`",
            "mandatory": True,
            "specialist": _spec("development"),
            "deliverables": [fname],
            "expected_kind": "explicit_file",
            "expected_file": fname,
            "acceptance_criteria": [f"Deliverable matching `{fname}` is produced and passes independent verification"],
            "verification_method": "independent_file_verification",
            "status": "PENDING",
            "evidence": [],
        })

    return {
        "schema_version": 2,
        "generated_at": _now_iso(),
        "project": project_slug,
        "goal_sha256": _sha256_text(raw),
        "goal_text": raw,
        "requirements": reqs,
    }


def _check_symbol_extension_coherence(target_file: str, required_symbols: list[str]) -> list[str]:
    """Reject incoherent contracts (e.g. Python class/def symbols required on a `.json` file)."""
    ext = Path(target_file).suffix.lower()
    issues: list[str] = []
    for sym in required_symbols:
        s = sym.strip()
        if not s:
            continue
        if ext == ".json":
            if s.startswith(("def ", "class ", "import ", "<")) or re.fullmatch(r"[A-Z][a-zA-Z0-9]+", s):
                issues.append(f"incoherent symbol {s!r} for JSON data file {target_file!r}")
        elif ext == ".py":
            if s.startswith(("<", "@media", "/", ".")):
                issues.append(f"incoherent non-Python symbol {s!r} for Python file {target_file!r}")
        elif ext == ".css":
            if s.startswith(("def ", "class ", "import ", "<html", "<!doctype")):
                issues.append(f"incoherent non-CSS symbol {s!r} for CSS file {target_file!r}")
        elif ext == ".html":
            if s.startswith(("def ", "class ", "import ")):
                issues.append(f"incoherent Python symbol {s!r} for HTML file {target_file!r}")
    return issues


def validate_and_normalize_plan(
    raw_plan: dict[str, Any],
    *,
    project_root: Path,
    project_slug: str,
    explicit_specialist: str | None = None,
    goal_text: str = "",
    confidential: bool = False,
    manifest: dict[str, Any] | None = None,
    strict_dependencies: bool = True,
) -> dict[str, Any]:
    """Deterministically validate, normalize, and seal a coordinator-generated project plan.

    - Supports up to MAX_PLAN_MISSIONS (36) missions executed in bounded topological batches.
    - Explicitly REJECTS unknown or self-referential dependencies (never silently drops them).
    - Rejects cycles, protected kit paths, Windows reserved names, unsupported extensions,
      and file-type/symbol incoherence.
    - Binds sealed plan to `goal_sha256` and `scope_config_sha256`.
    """
    if not isinstance(raw_plan, dict):
        raise ValueError("coordinator plan must be a JSON object")
    raw_missions = raw_plan.get("missions")
    if not isinstance(raw_missions, list) or not 1 <= len(raw_missions) <= MAX_PLAN_MISSIONS:
        raise ValueError(f"coordinator plan must define 1..{MAX_PLAN_MISSIONS} bounded missions")

    catalog = team_config.role_catalog()
    by_name = {spec.name: spec for spec in catalog.values()}
    by_role = {role: spec for role, spec in catalog.items()}

    def _resolve_spec_name(val: str | None, fallback_query: str) -> str:
        if explicit_specialist:
            return specialist_dispatch.resolve_specialist(explicit_specialist).name
        if isinstance(val, str):
            v = val.strip()
            if v in by_name:
                return v
            if v in by_role:
                return by_role[v].name
        picks = specialist_dispatch.select_specialists(fallback_query, include_verifier=False, max_specialists=1)
        return picks[0]["name"] if picks else "tel99-dev"

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    id_remap: dict[str, str] = {}

    for idx, item in enumerate(raw_missions, 1):
        if not isinstance(item, dict):
            raise ValueError(f"mission #{idx} must be a JSON object")
        orig_id = str(item.get("id") or f"m-{idx:02d}")
        mid = _safe_mission_id(orig_id, idx)
        while mid in seen_ids:
            mid = f"{mid[:36]}-{idx}"
        seen_ids.add(mid)
        id_remap[orig_id] = mid

        raw_tf = str(item.get("target_file") or "").replace("\\", "/").strip()
        if raw_tf.startswith("./"):
            raw_tf = raw_tf[2:]
        tf = raw_tf
        if not autonomy_runtime._safe_rel_path(tf):
            raise ValueError(f"unsafe target_file in mission {mid}: {tf!r}")
        local_deterministic_tools.safe_subpath(
            project_root, tf, blocked_top_dirs=RESERVED_PROJECT_TOP_DIRS
        )
        ext = Path(tf).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"unsupported file extension in mission {mid}: {tf!r}")
        if tf in seen_files:
            raise ValueError(f"duplicate target_file in plan: {tf!r}")
        seen_files.add(tf)

        obj = str(item.get("objective") or "").strip()
        if len(obj) < 15:
            raise ValueError(f"mission {mid} objective too short")
        spec_name = _resolve_spec_name(item.get("specialist") or item.get("role"), f"{tf} {obj}")
        req_syms = [
            str(s).strip() for s in (item.get("required_symbols") or [])
            if isinstance(s, str) and s.strip()
        ][:12]
        coh_issues = _check_symbol_extension_coherence(tf, req_syms)
        if coh_issues:
            raise ValueError("; ".join(coh_issues))

        assess = mission_planner.assess_and_decompose_mission(
            {"id": mid, "path": tf, "estimated_lines": int(item.get("estimated_lines") or 60), "objective": obj[:250]},
            max_safe_lines=85,
        )
        raw_deps = item.get("dependencies")
        if raw_deps is None:
            raw_deps = []
        if not isinstance(raw_deps, list):
            raise ValueError(f"mission {mid} dependencies must be a list")

        normalized.append({
            "id": mid,
            "specialist": spec_name,
            "target_file": tf,
            "raw_deps": list(raw_deps),
            "objective": obj[:3500],
            "required_symbols": req_syms,
            "task_profile": assess.get("recommended_profile", "module"),
            "priority": f"P{min(idx, 9)}",
            "max_attempts": 4,
        })

    # Ensure mandatory deliverable classes implied by goal/manifest are covered when omitted
    g_low = (goal_text or "").lower()
    if g_low:
        def _append_std_mission(mid_base: str, spec_name: str, target_file: str, objective: str, req_syms: list[str]) -> None:
            if target_file in seen_files or len(normalized) >= MAX_PLAN_MISSIONS:
                return
            mid = mid_base
            while mid in seen_ids:
                mid = f"{mid}-extra"
            seen_ids.add(mid)
            seen_files.add(target_file)
            normalized.append({
                "id": mid,
                "specialist": spec_name,
                "target_file": target_file,
                "raw_deps": [],
                "objective": objective,
                "required_symbols": req_syms,
                "task_profile": "module",
                "priority": f"P{min(len(normalized) + 1, 9)}",
                "max_attempts": 4,
            })

        if ("html" in g_low or "interface web" in g_low) and not any(m["target_file"].endswith(".html") for m in normalized):
            _append_std_mission(
                "ui-html", "tel99-mobile", "web/index.html",
                f"Create clean responsive HTML5 UI web/index.html linking /styles.css and /app.js (defer), ZERO inline <script> or onclick/onerror, implementing all required UI views for {project_slug}.",
                ["<!doctype", "/styles.css", "/app.js"],
            )
        if ("styles.css" in g_low or "css" in g_low or "interface web" in g_low) and not any(m["target_file"].endswith(".css") for m in normalized):
            _append_std_mission(
                "ui-css", "tel99-mobile", "web/styles.css",
                f"Create clean responsive CSS stylesheet web/styles.css (ZERO CSS comments, balanced braces, @media mobile breakpoint, >= 400 chars) styling {project_slug}.",
                ["@media"],
            )
        if ("app.js" in g_low or ".js" in g_low or "interface web" in g_low) and not any(m["target_file"].endswith(".js") for m in normalized):
            _append_std_mission(
                "ui-js", "tel99-mobile", "web/app.js",
                f"Create safe vanilla JS frontend web/app.js wiring the HTML controls to the local HTTP API using fetch, createElement, textContent, and replaceChildren (NEVER innerHTML, eval, or document.write).",
                ["DOMContentLoaded", "fetch"],
            )
        if any(m["target_file"].endswith(".py") for m in normalized) and not any(
            m["target_file"].startswith("tests/test_") and m["target_file"].endswith(".py") for m in normalized
        ):
            _append_std_mission(
                "unit-tests", "tel99-verifier", "tests/test_app.py",
                f"Write comprehensive unittest suite testing core functionality, strict data validation (invalid/bool/negative values), and edge cases for {project_slug}.",
                ["unittest"],
            )
        if ("readme" in g_low or "documentation" in g_low) and not any(m["target_file"].lower().endswith("readme.md") for m in normalized):
            _append_std_mission(
                "project-readme", "tel99-documentation", "README.md",
                f"Write concise README.md documenting {project_slug}: features, architecture, startup command, and how to run tests.",
                [],
            )
        if ("start.ps1" in g_low or ".ps1" in g_low) and not any(m["target_file"].endswith(".ps1") for m in normalized):
            _append_std_mission(
                "startup-ps1", "tel99-release", "start.ps1",
                f"Write concise Windows PowerShell startup script start.ps1 launching the local Python loopback server for {project_slug} (127.0.0.1 only, NEVER 0.0.0.0).",
                [],
            )

    id_set = {m["id"] for m in normalized}
    by_id_raw = {m["id"]: m for m in normalized}

    non_test_py_ids = [
        m["id"] for m in normalized
        if m["target_file"].endswith(".py") and not m["target_file"].startswith("tests/")
    ]
    web_html_ids = [m["id"] for m in normalized if m["target_file"].endswith(".html")]
    test_ids = [m["id"] for m in normalized if m["target_file"].startswith("tests/")]

    # Validate dependencies STRICTLY (reject unknown or self-referential deps; never drop silently)
    graph: dict[str, list[str]] = {}
    for m in normalized:
        deps: list[str] = []
        for raw_d in m.pop("raw_deps"):
            if not isinstance(raw_d, str) or not raw_d.strip():
                raise ValueError(f"invalid dependency entry in mission {m['id']}: {raw_d!r}")
            mapped = id_remap.get(raw_d, _safe_mission_id(raw_d, 0))
            if mapped == m["id"]:
                raise ValueError(f"self-referential dependency in mission {m['id']}")
            if mapped not in id_set:
                if strict_dependencies:
                    raise ValueError(f"unknown dependency {raw_d!r} in mission {m['id']}")
                continue
            if mapped not in deps:
                deps.append(mapped)
        tf = m["target_file"]
        if tf.startswith("tests/") and tf.endswith(".py"):
            # Only auto-wire non-test Python leaves not already depended on, capped to <= 18 total direct deps
            referenced_py = {
                id_remap.get(str(d), _safe_mission_id(str(d), 0))
                for other in normalized
                if other["id"] in non_test_py_ids
                for d in other.get("dependencies", [])
            }
            leaf_py = [pid for pid in non_test_py_ids if pid not in referenced_py] or non_test_py_ids[-16:]
            for pid in leaf_py:
                if len(deps) >= 18:
                    break
                if pid != m["id"] and pid not in deps:
                    deps.append(pid)
        elif tf.endswith(".js"):
            for hid in web_html_ids:
                if len(deps) >= 18:
                    break
                if hid != m["id"] and hid not in deps:
                    deps.append(hid)
        elif tf.lower().endswith("readme.md") or tf.endswith(".ps1"):
            for tid in (test_ids or non_test_py_ids[-16:]):
                if len(deps) >= 18:
                    break
                if tid != m["id"] and tid not in deps:
                    deps.append(tid)
        if len(deps) > 18:
            raise ValueError(f"mission {m['id']} has >18 direct dependencies ({len(deps)}); split via intermediate modules")
        m["dependencies"] = deps
        graph[m["id"]] = deps

    try:
        topo_order = list(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise ValueError(f"dependency cycle in coordinator plan: {exc}") from exc

    # Validate server_entry if provided
    server_entry = str(raw_plan.get("server_entry") or "").replace("\\", "/").strip() or None
    if server_entry:
        if server_entry.startswith("./"):
            server_entry = server_entry[2:]
        local_deterministic_tools.safe_subpath(
            project_root, server_entry, blocked_top_dirs=RESERVED_PROJECT_TOP_DIRS
        )
        if not server_entry.endswith(".py"):
            raise ValueError(f"server_entry must be a .py file: {server_entry!r}")
        if server_entry not in seen_files:
            raise ValueError(f"server_entry {server_entry!r} is not listed in plan deliverables")

    contracts: list[dict[str, Any]] = []
    meta_by_id: dict[str, dict[str, Any]] = {}
    ws_str = str(project_root.resolve())

    for mid in topo_order:
        m = by_id_raw[mid]
        # Keep per-contract allowed_paths <= 20 (required by autonomy_runtime.validate_project_file_contract)
        dep_paths = [by_id_raw[d]["target_file"] for d in m["dependencies"] if d in by_id_raw]
        contract_allowed = list(dict.fromkeys([m["target_file"], *dep_paths]))[:20]
        contract = {
            "id": m["id"],
            "owner": "project-file",
            "project": project_slug,
            "specialist": m["specialist"],
            "priority": m["priority"],
            "dependencies": m["dependencies"],
            "objective": m["objective"],
            "workspace_root": ws_str,
            "allowed_paths": contract_allowed,
            "target_file": m["target_file"],
            "task_profile": m["task_profile"],
            "max_attempts": m["max_attempts"],
        }
        validate_project_file_contract(contract)
        contracts.append(contract)
        meta_by_id[mid] = {
            "required_symbols": m["required_symbols"],
            "target_file": m["target_file"],
            "specialist": m["specialist"],
        }

    plan = {
        "schema_version": 2,
        "plan_revision": 1,
        "plan_revisions": [],
        "generated_at": _now_iso(),
        "project": project_slug,
        "workspace_root": ws_str,
        "goal": goal_text,
        "goal_sha256": _sha256_text(goal_text),
        "scope_config_sha256": _scope_config_hash(
            explicit_specialist=explicit_specialist, confidential=confidential
        ),
        "summary": str(raw_plan.get("summary") or "")[:400],
        "startup_command": str(raw_plan.get("startup_command") or "")[:300],
        "server_entry": server_entry,
        "test_command": str(raw_plan.get("test_command") or "python -B -m unittest discover -s tests -v")[:300],
        "execution_order": topo_order,
        "contracts": contracts,
        "approvals": seal(contracts),
        "mission_meta": meta_by_id,
    }
    if manifest is not None:
        v_plan = verify_plan_independent(plan, manifest)
        plan["plan_verification"] = v_plan
    return plan


def verify_plan_independent(plan: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Independent deterministic plan verifier executed BEFORE sealing/running contracts."""
    issues: list[str] = []
    contracts = list(plan.get("contracts") or [])
    if not contracts:
        return {"ok": False, "issues": ["plan has zero contracts"], "requirement_mapping": {}}

    files = [c["target_file"] for c in contracts]
    file_set = set(files)
    meta_by_id = plan.get("mission_meta") or {}

    # Check symbol/extension coherence and supported extensions across all contracts
    for c in contracts:
        tf = c["target_file"]
        ext = Path(tf).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            issues.append(f"unsupported file extension: {tf}")
        syms = (meta_by_id.get(c["id"]) or {}).get("required_symbols") or []
        issues.extend(_check_symbol_extension_coherence(tf, syms))

    # Map each requirement in manifest to concrete deliverables
    req_mapping: dict[str, list[str]] = {}
    for req in manifest.get("requirements") or []:
        rid = req["id"]
        kind = req.get("expected_kind")
        matched: list[str] = []
        if kind == "python_core":
            matched = [f for f in files if f.endswith(".py") and not f.startswith("tests/")]
        elif kind == "http_server":
            if plan.get("server_entry") and plan["server_entry"] in file_set:
                matched = [plan["server_entry"]]
            else:
                matched = [f for f in files if f.endswith(".py") and any(k in f.lower() for k in ("server", "app", "web", "api", "http"))]
        elif kind == "html":
            matched = [f for f in files if f.endswith(".html")]
        elif kind == "css":
            matched = [f for f in files if f.endswith(".css")]
        elif kind == "js":
            matched = [f for f in files if f.endswith(".js")]
        elif kind == "ps1":
            matched = [f for f in files if f.endswith(".ps1")]
        elif kind == "md":
            matched = [f for f in files if f.lower().endswith("readme.md") or f.endswith(".md")]
        elif kind == "tests":
            matched = [f for f in files if f.startswith("tests/") and f.endswith(".py")]
        elif kind == "security":
            matched = list(files)
        elif kind == "explicit_file":
            exp = str(req.get("expected_file") or "")
            matched = [f for f in files if f == exp or f.endswith("/" + exp) or Path(f).name == Path(exp).name]
        elif kind == "business_capability":
            matched = [f for f in files if f.endswith(".py") and not f.startswith("tests/")]
        req_mapping[rid] = matched
        if req.get("mandatory") and not matched:
            issues.append(f"mandatory requirement {rid} ({req.get('source_text', '')[:80]}) has no deliverable in plan")

    if any(f.endswith(".py") and not f.startswith("tests/") for f in files) and not any(
        f.startswith("tests/") and f.endswith(".py") for f in files
    ):
        issues.append("Python deliverables planned without any tests/test_*.py deliverable")

    if any(f.endswith(".html") for f in files) and not plan.get("server_entry"):
        # Infer candidate server_entry if unique obvious Python server exists, otherwise flag
        py_non_test = [f for f in files if f.endswith(".py") and not f.startswith("tests/")]
        if not py_non_test:
            issues.append("HTML UI planned without any Python server_entry")

    return {
        "ok": not issues,
        "issues": list(dict.fromkeys(issues)),
        "requirement_mapping": req_mapping,
    }


def _extract_python_ast_symbols(tree: ast.AST) -> set[str]:
    """Extract defined/imported Python symbols strictly from AST (NEVER comments or docstrings)."""
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                symbols.add(alias.asname or alias.name.split(".")[0])
                symbols.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                symbols.add(node.module.split(".")[0])
            for alias in node.names:
                symbols.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    symbols.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            symbols.add(node.target.id)
    return symbols


# ---------------------------------------------------------------------------
# Independent Deliverable & Post-Build E2E Verification
# ---------------------------------------------------------------------------

def verify_delivered_file(
    project_root: Path,
    target_rel: str,
    *,
    required_symbols: list[str] | None = None,
    require_sandbox: bool = True,
    sandbox_image: str = DEFAULT_SANDBOX_IMAGE,
) -> dict[str, Any]:
    """Independent, objective, deterministic verifier for ANY delivered project file.

    - Enforces hardened path confinement (Windows reserved names, symlinks, protected kit dirs).
    - Rejects unsupported extensions explicitly.
    - Checks `.py` required symbols strictly via AST (never comment substring match).
    - Runs Python import and `unittest` checks inside Docker OS sandbox when `require_sandbox=True` (fail-closed).
    """
    verifiers_run: list[str] = ["path_confinement", "secret_scan"]
    try:
        target = local_deterministic_tools.safe_subpath(
            project_root, target_rel, blocked_top_dirs=RESERVED_PROJECT_TOP_DIRS
        )
    except ValueError as exc:
        return {
            "ok": False, "security_ok": False, "sandbox_used": False,
            "error": f"scope violation: {exc}", "checks_passed": [], "verifiers_run": verifiers_run,
        }

    ext = target.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {
            "ok": False, "security_ok": False, "sandbox_used": False,
            "error": f"unsupported file extension {ext!r} for {target_rel}",
            "checks_passed": [], "verifiers_run": verifiers_run,
        }

    if not target.is_file():
        return {
            "ok": False, "security_ok": True, "sandbox_used": False,
            "error": f"missing target file {target_rel}", "checks_passed": [], "verifiers_run": verifiers_run,
        }

    text = target.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return {
            "ok": False, "security_ok": True, "sandbox_used": False,
            "error": f"empty file {target_rel}", "checks_passed": [], "verifiers_run": verifiers_run,
        }

    checks: list[str] = ["exists", "scope_confined"]
    if not local_deterministic_tools.detect_secret_leak(text)["safe"]:
        return {
            "ok": False, "security_ok": False, "sandbox_used": False,
            "error": "security: secret token pattern detected", "checks_passed": checks, "verifiers_run": verifiers_run,
        }
    checks.append("no_secret_leak")
    sandbox_used = False

    if ext == ".py":
        verifiers_run.extend(["deterministic_security_gate", "ast_symbol_verifier"])
        sec = local_deterministic_tools.deterministic_security_gate(
            text, kind="python", allowed_root=project_root, target_rel_path=target_rel
        )
        if not sec["ok"]:
            return {
                "ok": False, "security_ok": sec["security_ok"], "sandbox_used": False,
                "error": "; ".join(sec["issues"]), "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        checks.extend(["ast_syntax", "deterministic_security_gate"])

        if target.parent != project_root.resolve():
            init_py = target.parent / "__init__.py"
            if not init_py.exists():
                init_py.write_text("", encoding="utf-8")

        tree = ast.parse(text)
        ast_symbols = _extract_python_ast_symbols(tree)
        missing_syms = [s for s in (required_symbols or []) if s not in ast_symbols]
        if missing_syms:
            return {
                "ok": False, "security_ok": True, "sandbox_used": False,
                "error": f"missing required AST symbols in {target_rel}: {', '.join(missing_syms)}",
                "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        if required_symbols:
            checks.append("required_symbols_ast")

        norm_rel = target_rel.replace("\\", "/")
        is_test = target.name.startswith("test_") or "tests/" in norm_rel
        if is_test:
            verifiers_run.append("docker_sandbox_unittest" if require_sandbox else "host_unittest")
            res = _exec_python_isolated(
                project_root,
                ["-m", "unittest", norm_rel, "-v"],
                timeout=35,
                require_sandbox=require_sandbox,
                sandbox_image=sandbox_image,
            )
            sandbox_used = bool(res.get("sandbox_used"))
            if res.get("sandbox_unavailable") or res.get("error"):
                return {
                    "ok": False, "security_ok": True, "sandbox_used": sandbox_used,
                    "error": res.get("error") or "sandbox_unavailable",
                    "checks_passed": checks, "verifiers_run": verifiers_run,
                }
            combined = ((res.get("stdout") or "") + "\n" + (res.get("stderr") or "")).strip()
            if res["returncode"] != 0:
                return {
                    "ok": False, "security_ok": True, "sandbox_used": sandbox_used,
                    "error": f"unittest failed (rc={res['returncode']}): {combined[-300:]}",
                    "checks_passed": checks, "verifiers_run": verifiers_run,
                }
            if "Ran 0 tests" in combined or "Ran " not in combined:
                return {
                    "ok": False, "security_ok": True, "sandbox_used": sandbox_used,
                    "error": "unittest executed 0 tests; must include real assertions",
                    "checks_passed": checks, "verifiers_run": verifiers_run,
                }
            checks.append("unittest_passed_sandbox" if sandbox_used else "unittest_passed")
        else:
            verifiers_run.append("docker_sandbox_import" if require_sandbox else "host_import")
            mod_rel = norm_rel[:-3].replace("/", ".")
            res = _exec_python_isolated(
                project_root,
                ["-c", f"import importlib; importlib.import_module({mod_rel!r})"],
                timeout=20,
                require_sandbox=require_sandbox,
                sandbox_image=sandbox_image,
            )
            sandbox_used = bool(res.get("sandbox_used"))
            if res.get("sandbox_unavailable") or res.get("error"):
                return {
                    "ok": False, "security_ok": True, "sandbox_used": sandbox_used,
                    "error": res.get("error") or "sandbox_unavailable",
                    "checks_passed": checks, "verifiers_run": verifiers_run,
                }
            if res["returncode"] != 0:
                err_txt = ((res.get("stderr") or "") or (res.get("stdout") or "")).strip()
                return {
                    "ok": False, "security_ok": True, "sandbox_used": sandbox_used,
                    "error": f"import {mod_rel} failed: {err_txt[-260:]}",
                    "checks_passed": checks, "verifiers_run": verifiers_run,
                }
            checks.append("isolated_import_ok_sandbox" if sandbox_used else "isolated_import_ok")

    elif ext == ".html":
        verifiers_run.append("html_static_security")
        low = text.lower()
        if "<script>" in low or "javascript:" in low or "onerror=" in low or "onclick=" in low:
            return {
                "ok": False, "security_ok": False, "sandbox_used": False,
                "error": "security: inline <script>, javascript: URI, or inline event handler forbidden",
                "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        if "<html" not in low or "<body" not in low:
            return {
                "ok": False, "security_ok": True, "sandbox_used": False,
                "error": "HTML missing <html> or <body> structure", "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        missing_syms = [s for s in (required_symbols or []) if s.lower() not in low]
        if missing_syms:
            return {
                "ok": False, "security_ok": True, "sandbox_used": False,
                "error": f"HTML missing required IDs/tokens: {', '.join(missing_syms)}",
                "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        checks.extend(["html_structure", "csp_safe_static"])

    elif ext == ".css":
        verifiers_run.append("css_static_check")
        no_comments = re.sub(r"/\*[\s\S]*?\*/", "", text)
        o_cnt, c_cnt = no_comments.count("{"), no_comments.count("}")
        if o_cnt == 0 or o_cnt != c_cnt:
            return {
                "ok": False, "security_ok": True, "sandbox_used": False,
                "error": f"Unbalanced braces: {{={o_cnt} }}={c_cnt}",
                "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        if len(text) < 250:
            return {
                "ok": False, "security_ok": True, "sandbox_used": False,
                "error": "CSS too short (< 250 chars)", "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        checks.extend(["css_balanced_braces", "css_size_ok"])

    elif ext == ".js":
        verifiers_run.append("js_node_check_and_security")
        for bad in ("eval(", "new Function(", "document.write("):
            if bad in text:
                return {
                    "ok": False, "security_ok": False, "sandbox_used": False,
                    "error": f"security: forbidden JS construct {bad}",
                    "checks_passed": checks, "verifiers_run": verifiers_run,
                }
        if ".innerHTML" in text:
            return {
                "ok": False, "security_ok": False, "sandbox_used": False,
                "error": "security: use textContent/createElement instead of .innerHTML",
                "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        proc = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True, timeout=10, check=False)
        if proc.returncode != 0:
            return {
                "ok": False, "security_ok": True, "sandbox_used": False,
                "error": f"node --check failed: {(proc.stderr or proc.stdout).strip()[:260]}",
                "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        missing_syms = [s for s in (required_symbols or []) if s not in text]
        if missing_syms:
            return {
                "ok": False, "security_ok": True, "sandbox_used": False,
                "error": f"JS missing required tokens: {', '.join(missing_syms)}",
                "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        checks.extend(["node_check_ok", "js_security_static"])

    elif ext == ".ps1":
        verifiers_run.append("powershell_parser_check")
        if "0.0.0.0" in text or "Invoke-Expression" in text or "iex " in text.lower():
            return {
                "ok": False, "security_ok": False, "sandbox_used": False,
                "error": "security: forbidden PowerShell construct (0.0.0.0 / Invoke-Expression)",
                "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        if shutil.which("powershell") or shutil.which("pwsh"):
            ps_bin = "pwsh" if shutil.which("pwsh") else "powershell"
            ps_check = (
                "$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
                f"'{str(target)}', [ref]$null, [ref]$e) | Out-Null; "
                "if ($e -and $e.Count -gt 0) { Write-Error ($e[0].Message); exit 1 }"
            )
            proc = subprocess.run([ps_bin, "-NoProfile", "-Command", ps_check], capture_output=True, text=True, timeout=15, check=False)
            if proc.returncode != 0:
                return {
                    "ok": False, "security_ok": True, "sandbox_used": False,
                    "error": f"PowerShell syntax error: {(proc.stderr or proc.stdout).strip()[:240]}",
                    "checks_passed": checks, "verifiers_run": verifiers_run,
                }
        checks.append("ps1_syntax_ok")

    elif ext == ".md":
        verifiers_run.append("markdown_doc_check")
        if len(text.strip()) < 180:
            return {
                "ok": False, "security_ok": True, "sandbox_used": False,
                "error": "README.md too short (< 180 chars)", "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        checks.append("doc_non_empty")

    elif ext == ".json":
        verifiers_run.append("json_parse_check")
        try:
            json.loads(text)
        except ValueError as exc:
            return {
                "ok": False, "security_ok": True, "sandbox_used": False,
                "error": f"Invalid JSON: {exc}", "checks_passed": checks, "verifiers_run": verifiers_run,
            }
        checks.append("valid_json")

    else:
        # Other explicitly allowlisted text formats (.txt, .csv, .toml, .yml, .yaml)
        verifiers_run.append("text_deliverable_check")
        checks.append("text_non_empty")

    return {
        "ok": True,
        "security_ok": True,
        "sandbox_used": sandbox_used,
        "error": None,
        "checks_passed": checks,
        "verifiers_run": verifiers_run,
        "file_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


def _discover_api_routes(server_path: Path) -> list[str]:
    if not server_path.is_file():
        return []
    txt = server_path.read_text(encoding="utf-8", errors="replace")
    routes = re.findall(r"""['"](/api/[A-Za-z0-9_/-]+)['"]""", txt)
    out: list[str] = []
    for r in routes:
        if r not in out and not r.endswith("/"):
            out.append(r)
    return out[:6]


def _run_post_build_verification(
    project_root: Path,
    plan: dict[str, Any],
    *,
    require_sandbox: bool = True,
    sandbox_image: str = DEFAULT_SANDBOX_IMAGE,
) -> dict[str, Any]:
    """Run real independent sandboxed test suite + full HTTP E2E probe after Runtime completes."""
    contracts = list(plan.get("contracts") or [])
    has_python = any(c["target_file"].endswith(".py") for c in contracts)
    has_web = any(c["target_file"].endswith(".html") for c in contracts)
    srv_rel = plan.get("server_entry")
    verifiers_run: list[str] = []

    report: dict[str, Any] = {
        "tests_required": has_python,
        "tests_ok": not has_python,
        "tests_sandbox_used": False,
        "server_required": bool(srv_rel or has_web),
        "server_probe": None,
        "server_e2e_ok": not (srv_rel or has_web),
        "verifiers_run": verifiers_run,
    }

    tests_dir = project_root / "tests"
    if tests_dir.is_dir():
        verifiers_run.append("docker_sandbox_unittest_suite" if require_sandbox else "host_unittest_suite")
        res = _exec_python_isolated(
            project_root,
            ["-m", "unittest", "discover", "-s", "tests", "-v"],
            timeout=50,
            require_sandbox=require_sandbox,
            sandbox_image=sandbox_image,
        )
        report["tests_sandbox_used"] = bool(res.get("sandbox_used"))
        out = ((res.get("stdout") or "") + "\n" + (res.get("stderr") or "")).strip()
        report["tests_rc"] = res.get("returncode")
        report["tests_output"] = (res.get("error") or out)[-1400:]
        report["tests_ok"] = (
            res.get("error") is None
            and not res.get("sandbox_unavailable")
            and res.get("returncode") == 0
            and "Ran 0 tests" not in out
            and "Ran " in out
        )
    else:
        report["tests_output"] = "no tests/ directory found"
        report["tests_ok"] = not has_python

    # Real HTTP E2E probe inside isolated sandbox (--network none loopback 127.0.0.1)
    if srv_rel and (project_root / srv_rel).is_file():
        verifiers_run.append("docker_sandbox_http_e2e" if require_sandbox else "host_http_e2e")
        api_routes = _discover_api_routes(project_root / srv_rel)
        probe_script = (
            "import importlib.util, json, re, socket, subprocess, sys, threading, time\n"
            "from http.client import HTTPConnection\n"
            "from pathlib import Path\n"
            f"srv_rel = {srv_rel!r}\n"
            f"api_routes = {api_routes!r}\n"
            "root = Path.cwd()\n"
            "p = root / srv_rel\n"
            "spec = importlib.util.spec_from_file_location('srv_probe', str(p))\n"
            "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
            "fn = getattr(mod, 'make_server', None) or getattr(mod, 'create_server', None) or getattr(mod, 'build_server', None)\n"
            "srv = None; child = None; port = None\n"
            "try:\n"
            "    if callable(fn):\n"
            "        for args, kwargs in [((root,), {'host': '127.0.0.1', 'port': 0}), ((), {'host': '127.0.0.1', 'port': 0}), (('127.0.0.1', 0), {}), ((0,), {})]:\n"
            "            try:\n"
            "                srv = fn(*args, **kwargs); break\n"
            "            except TypeError:\n"
            "                continue\n"
            "        if srv is not None:\n"
            "            port = srv.server_port\n"
            "            threading.Thread(target=srv.serve_forever, daemon=True).start()\n"
            "            time.sleep(0.15)\n"
            "    if port is None:\n"
            "        s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()\n"
            "        child = subprocess.Popen([sys.executable, '-B', str(p), '--host', '127.0.0.1', '--port', str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            "        for _ in range(25):\n"
            "            time.sleep(0.12)\n"
            "            try:\n"
            "                c = HTTPConnection('127.0.0.1', port, timeout=1); c.request('GET', '/'); c.getresponse().read(); c.close(); break\n"
            "            except OSError:\n"
            "                continue\n"
            "    issues = []\n"
            "    c = HTTPConnection('127.0.0.1', port, timeout=5)\n"
            "    c.request('GET', '/'); r = c.getresponse(); body = r.read().decode('utf-8', errors='replace'); c.close()\n"
            "    if r.status != 200 or not body.strip(): issues.append(f'GET / returned {r.status}')\n"
            "    assets = {}\n"
            "    for ref in sorted(set(re.findall(r'(?:href|src)=[\"\\'](/[A-Za-z0-9_./-]+\\.(?:css|js))[\"\\']', body))):\n"
            "        ca = HTTPConnection('127.0.0.1', port, timeout=5); ca.request('GET', ref); ra = ca.getresponse(); ba = ra.read(); ca.close()\n"
            "        assets[ref] = {'status': ra.status, 'bytes': len(ba)}\n"
            "        if ra.status != 200 or not ba.strip(): issues.append(f'static asset {ref} returned {ra.status}')\n"
            "    cn = HTTPConnection('127.0.0.1', port, timeout=5); cn.request('GET', '/__tel99_missing_404__'); rn = cn.getresponse(); rn.read(); cn.close()\n"
            "    if rn.status != 404: issues.append(f'unknown route expected 404, got {rn.status}')\n"
            "    api_results = []\n"
            "    for route in api_routes:\n"
            "        cg = HTTPConnection('127.0.0.1', port, timeout=5); cg.request('GET', route); rg = cg.getresponse(); bg = rg.read(); cg.close()\n"
            "        body_str = bg.decode('utf-8', errors='replace').strip()\n"
            "        json_valid = None\n"
            "        if rg.status == 200 and (body_str.startswith('{') or body_str.startswith('[')):\n"
            "            try:\n"
            "                json.loads(body_str); json_valid = True\n"
            "            except ValueError:\n"
            "                json_valid = False; issues.append(f'GET {route} returned invalid JSON')\n"
            "        api_results.append({'method': 'GET', 'route': route, 'status': rg.status, 'bytes': len(bg), 'json_valid': json_valid})\n"
            "        if rg.status == 404 or rg.status >= 500: issues.append(f'GET {route} returned {rg.status}')\n"
            "    if api_routes:\n"
            "        cp = HTTPConnection('127.0.0.1', port, timeout=5)\n"
            "        cp.request('POST', api_routes[0], body=b'{invalid', headers={'Content-Type': 'application/json'})\n"
            "        rp = cp.getresponse(); rp.read(); cp.close()\n"
            "        api_results.append({'method': 'POST_INVALID_JSON', 'route': api_routes[0], 'status': rp.status})\n"
            "        if rp.status not in (400, 405, 415, 422): issues.append(f'invalid JSON POST expected 400/405/422, got {rp.status}')\n"
            "    print(json.dumps({'probed': True, 'ok': not issues, 'http_status': r.status, 'bytes': len(body), 'static_assets': assets, 'negative_404_status': rn.status, 'api_probes': api_results, 'issues': issues}))\n"
            "except Exception as exc:\n"
            "    print(json.dumps({'probed': False, 'ok': False, 'issues': [f'{type(exc).__name__}: {exc}']}))\n"
            "finally:\n"
            "    if srv is not None:\n"
            "        try: srv.shutdown(); srv.server_close()\n"
            "        except Exception: pass\n"
            "    if child is not None:\n"
            "        try: child.terminate(); child.wait(timeout=3)\n"
            "        except Exception: child.kill()\n"
        )
        p2 = _exec_python_isolated(
            project_root,
            ["-c", probe_script],
            timeout=25,
            require_sandbox=require_sandbox,
            sandbox_image=sandbox_image,
        )
        if p2.get("sandbox_unavailable") or p2.get("error"):
            report["server_probe"] = {
                "probed": False,
                "ok": False,
                "sandbox_used": bool(p2.get("sandbox_used")),
                "issues": [p2.get("error") or "sandbox_unavailable"],
            }
            report["server_e2e_ok"] = False
        else:
            try:
                lines = [ln for ln in (p2.get("stdout") or "").strip().splitlines() if ln.strip()]
                parsed = json.loads(lines[-1])
                parsed["sandbox_used"] = bool(p2.get("sandbox_used"))
                report["server_probe"] = parsed
                report["server_e2e_ok"] = bool(parsed.get("probed") and parsed.get("ok"))
            except Exception:
                report["server_probe"] = {
                    "probed": False,
                    "ok": False,
                    "sandbox_used": bool(p2.get("sandbox_used")),
                    "rc": p2.get("returncode"),
                    "stderr": (p2.get("stderr") or "")[-300:],
                    "issues": ["server probe produced unparseable output"],
                }
                report["server_e2e_ok"] = False
    elif report["server_required"]:
        report["server_probe"] = {
            "probed": False,
            "ok": False,
            "issues": [f"required server_entry missing: {srv_rel!r}"],
        }
        report["server_e2e_ok"] = False

    return report


# ---------------------------------------------------------------------------
# Model Invocation & Coordinator Planning (all 12 official roles)
# ---------------------------------------------------------------------------

def _call_model(
    *,
    system: str,
    prompt: str,
    hybrid: bool,
    confidential: bool,
    attempt: int,
    role: str,
    response_format: str | None = None,
    estimated_lines: int = 75,
    allow_continue: bool = False,
) -> tuple[str, str, str, int, dict]:
    """Invoke local Ollama (CAS-leased, concurrence=1) or optional free Groq mentor ($0.00)."""
    policy = local_deterministic_tools.check_cloud_escalation_policy(
        confidential=confidential, allow_cloud=hybrid, prompt_text=f"{system}\n{prompt}"
    )
    use_cloud = bool(hybrid and policy["allowed"] and (attempt >= 2 or role == "coordination"))
    if use_cloud and provider_router.load_local_provider_key("GROQ_API_KEY"):
        mentor = (
            "qwen/qwen3.8-27b" if role in ("development", "mobile", "market_data")
            else ("openai/gpt-oss-120b" if attempt in (1, 2) else "openai/gpt-oss-20b")
        )
        ad = provider_router.OpenAICompatFreeCloudAdapter(
            provider="groq",
            model=mentor,
            timeout=60,
            max_tokens=2048,
            confidential=False,
            fallback_ollama_model=LOCAL_MODEL,
        )
        out = ad.complete(system=system, prompt=prompt, response_format=response_format)
        meta = dict(ad.last_metadata)
        prov = str(meta.get("provider_used") or "groq")
        mdl = str(meta.get("model_used") or mentor)
        return out, prov, mdl, (1 if prov == "groq" else 0), meta

    eng = ide_coordination.probe_local_engines()
    resident = LOCAL_MODEL in ((eng.get("ollama") or {}).get("loaded_models") or [])
    budget = ollama_native.compute_adaptive_budget(
        LOCAL_MODEL,
        task_profile="module",
        estimated_lines=estimated_lines,
        available_memory_mib=eng.get("available_memory_mib"),
        model_is_resident=resident,
    )
    provider = ollama_native.OllamaNativeProvider(
        model=LOCAL_MODEL,
        timeout=budget["timeout"],
        max_tokens=budget["max_tokens"],
        keep_alive="120s",
        task_profile=budget["effective_profile"],
        num_ctx=budget["num_ctx"],
        num_thread=budget["num_thread"],
    )
    if allow_continue and response_format is None:
        out = provider.complete_with_continuation(system=system, prompt=prompt, max_continuations=1)
    else:
        out = provider.complete(system=system, prompt=prompt, response_format=response_format)
    meta = dict(provider.last_metadata)
    meta["adaptive_budget"] = budget
    return out, "ollama", LOCAL_MODEL, 0, meta


def generate_plan_with_coordinator(
    *,
    goal_text: str,
    project_root: Path,
    project_slug: str,
    manifest: dict[str, Any] | None = None,
    hybrid: bool = False,
    confidential: bool = False,
    explicit_specialist: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask `tel99-coordination` to decompose the user's goal using ALL 12 official TEL99 specialists."""
    coord = specialist_dispatch.resolve_specialist("coordination")
    all_specs = "|".join(spec.name for spec in team_config.role_catalog().values())
    manifest_summary = [
        {"id": r["id"], "mandatory": r["mandatory"], "source": r["source_text"][:140]}
        for r in ((manifest or {}).get("requirements") or [])
    ]
    sys_p = (
        f"{coord.full_prompt()}\n"
        "You are designing a complete, working, stdlib-only local software project for TEL99 agents.\n"
        "Output ONLY a valid JSON object (no markdown prose outside JSON) with exact keys:\n"
        '{"summary": str, "startup_command": str, "server_entry": str_or_empty, "test_command": str, "missions": [\n'
        f'  {{"id": "kebab-id", "specialist": "{all_specs}", '
        '"target_file": "relative/path.ext", "dependencies": ["prior-id"], "estimated_lines": 60, '
        '"required_symbols": ["exact_ast_symbol_or_token"], "objective": "Exact concise contract (interfaces, routes, validation, <=350 chars)"}\n'
        "]}\n"
        "Rules:\n"
        f"- Cover EVERY mandatory requirement cleanly (1..{MAX_PLAN_MISSIONS} focused files, no unnecessary bloat).\n"
        "- All dependencies MUST reference existing mission IDs in this plan (no unknown or cyclic IDs).\n"
        "- required_symbols MUST match the file type (Python AST names for .py, HTML/JS tokens for web, empty [] for .json/.md/.ps1).\n"
        "- Python 3.12 stdlib only; loopback 127.0.0.1 only (NEVER 0.0.0.0).\n"
        "- Web UI: separate `web/index.html` (NO inline <script>), `web/styles.css`, `web/app.js` (NO innerHTML).\n"
        "- Include `tests/test_*.py` unittest file. State exact function names, routes, and HTML IDs.\n"
    )
    existing_files = [
        str(p.relative_to(project_root)).replace("\\", "/")
        for p in sorted(project_root.rglob("*"))
        if p.is_file() and not any(part.lower() in RESERVED_PROJECT_TOP_DIRS for part in p.relative_to(project_root).parts)
    ][:30]
    usr_p = (
        f"Project slug: {project_slug}\n"
        f"Workspace directory: {project_root}\n"
        f"Existing files: {existing_files}\n"
        f"Requirements manifest to cover:\n{json.dumps(manifest_summary, ensure_ascii=False)}\n"
        f"User goal:\n{goal_text}\n"
    )

    last_err = ""
    for att in range(1, 4):
        prompt_now = (
            usr_p if att == 1
            else f"{usr_p}\nPrevious plan validation error: {last_err}\nFix the JSON plan and return ONLY valid JSON."
        )
        t0 = time.monotonic()
        raw, prov, mdl, cc, _meta = _call_model(
            system=sys_p,
            prompt=prompt_now,
            hybrid=hybrid,
            confidential=confidential,
            attempt=att,
            role="coordination",
            response_format="json",
            estimated_lines=75,
        )
        dur = round(time.monotonic() - t0, 2)
        try:
            cleaned = local_deterministic_tools.extract_clean_json(raw)
            parsed = json.loads(cleaned)
            plan = validate_and_normalize_plan(
                parsed,
                project_root=project_root,
                project_slug=project_slug,
                explicit_specialist=explicit_specialist,
                goal_text=goal_text,
                confidential=confidential,
                manifest=manifest,
                strict_dependencies=True,
            )
            if manifest is not None and not (plan.get("plan_verification") or {}).get("ok", True):
                v_issues = (plan.get("plan_verification") or {}).get("issues") or []
                raise ValueError("independent plan verification failed: " + "; ".join(v_issues[:4]))
            print(json.dumps({"coordinator_plan": "ok", "att": att, "missions": len(plan["contracts"]), "s": dur, "model": mdl}), flush=True)
            trace = {
                "agent": coord.name,
                "llm_called": True,
                "provider": prov,
                "model": mdl,
                "cloud_calls": cc,
                "attempts": att,
                "duration_seconds": dur,
            }
            return plan, trace
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {str(exc)[:260]}"
            print(json.dumps({"coordinator_plan": "retry", "att": att, "s": dur, "err": last_err}), flush=True)
    raise RuntimeError(f"Coordinator failed to produce valid plan after 3 attempts: {last_err}")


def _build_dependency_context(project_root: Path, deps: list[str], meta_by_id: dict[str, dict]) -> str:
    """Provide exact AST signatures + concise excerpts of already-delivered dependency files."""
    parts: list[str] = []
    cg = context_engine.build_code_graph(project_root)
    files_map = cg.get("files") or {}
    for dep_id in deps:
        rel = (meta_by_id.get(dep_id) or {}).get("target_file")
        if not rel:
            continue
        p = project_root / rel
        if not p.is_file():
            continue
        if rel in files_map and (files_map[rel].get("functions") or files_map[rel].get("classes")):
            sigs = [f"{fn['name']}({', '.join(fn['args'])})" for fn in files_map[rel].get("functions", [])[:12]]
            cls = [c["name"] for c in files_map[rel].get("classes", [])[:6]]
            parts.append(f"- {rel} [AST]: classes={cls} functions={sigs}")
        excerpt = p.read_text(encoding="utf-8", errors="replace").strip()
        if len(excerpt) > 1400:
            excerpt = excerpt[:1400] + "\n... [truncated]"
        parts.append(f"--- Existing dependency file `{rel}` ---\n{excerpt}")
    return "\n\n".join(parts)[:3000]


def _requeue_ledger_missions(camp_dir: Path, mission_ids: list[str], reason: str) -> list[str]:
    """Reset specified mission IDs in Runtime ledger to ACK while preserving all other ACCEPTED missions."""
    from scripts.agents.automation.local_codex import exclusive
    from scripts.agents.protocol.store import FileStore
    requeued: list[str] = []
    if not mission_ids:
        return requeued
    camp_dir.mkdir(parents=True, exist_ok=True)
    with exclusive(camp_dir / "runtime.lock"):
        st = FileStore(camp_dir / "ledger")
        for mid in mission_ids:
            old = st.read(f"kilo-local/{mid}")
            if old:
                hist = list(old.get("recovery_history") or [])
                hist.append({"recovered_at": time.time(), "previous_status": old.get("status"), "reason": reason})
                upd = {**old, "status": "ACK", "execution_status": "NOT_STARTED", "at": time.time(), "recovery_history": hist}
                upd.pop("result", None)
                upd.pop("verification", None)
                st.put_cas(f"kilo-local/{mid}", upd, old)
                requeued.append(mid)
    return requeued


def _apply_plan_revision(
    old_plan: dict[str, Any],
    new_plan: dict[str, Any],
    camp_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a versioned sealed revision, preserving unaffected ACCEPTED contracts and invalidating changed ones."""
    old_approvals = old_plan.get("approvals") or {}
    new_approvals = new_plan.get("approvals") or {}
    changed: set[str] = {
        mid for mid, sha in new_approvals.items()
        if old_approvals.get(mid) != sha
    }
    # Transitive dependent invalidation
    dep_map = {c["id"]: list(c.get("dependencies") or []) for c in new_plan.get("contracts") or []}
    growing = True
    while growing:
        growing = False
        for mid, deps in dep_map.items():
            if mid not in changed and any(d in changed for d in deps):
                changed.add(mid)
                growing = True

    preserved = sorted(mid for mid in new_approvals if mid not in changed and mid in old_approvals)
    invalidated = sorted(changed)
    if invalidated:
        _requeue_ledger_missions(camp_dir, invalidated, reason="sealed_plan_revision")

    revs = list(old_plan.get("plan_revisions") or [])
    revs.append({
        "revision": int(old_plan.get("plan_revision") or 1),
        "replaced_at": _now_iso(),
        "goal_sha256": old_plan.get("goal_sha256"),
        "preserved_missions": preserved,
        "invalidated_missions": invalidated,
    })
    new_plan["plan_revision"] = int(old_plan.get("plan_revision") or 1) + 1
    new_plan["plan_revisions"] = revs
    return new_plan, {"preserved": preserved, "invalidated": invalidated}


def _inspect_behavioral_evidence(
    project_root: Path,
    plan: dict[str, Any],
    post_ver: dict[str, Any],
) -> dict[str, Any]:
    """Read delivered app & test code + executed unittest output to verify real business behavior."""
    app_blob_parts: list[str] = []
    test_blob_parts: list[str] = []
    has_negative_assertion = False
    for c in plan.get("contracts") or []:
        tf = c["target_file"]
        p = project_root / tf
        if not p.is_file():
            continue
        txt = p.read_text(encoding="utf-8", errors="replace").lower()
        if tf.startswith("tests/") and tf.endswith(".py"):
            test_blob_parts.append(txt)
            if any(neg in txt for neg in ("assertraises", "400", "404", "422", "valueerror", "invalid")):
                has_negative_assertion = True
        elif tf.endswith((".py", ".js", ".html")):
            app_blob_parts.append(txt)
    tests_out = str(post_ver.get("tests_output") or "").lower()
    passing_test_lines = [ln.strip() for ln in tests_out.splitlines() if " ... ok" in ln]
    return {
        "app_blob": "\n".join(app_blob_parts),
        "test_blob": "\n".join(test_blob_parts) + "\n" + tests_out,
        "passing_tests_count": len(passing_test_lines),
        "has_negative_assertion": has_negative_assertion,
    }


def _update_manifest_with_results(
    manifest: dict[str, Any],
    plan: dict[str, Any],
    statuses: dict[str, str],
    post_ver: dict[str, Any],
    *,
    project_root: Path | None = None,
) -> tuple[dict[str, Any], bool]:
    """Update requirements_manifest.json with objective technical + behavioral verification evidence."""
    v_plan = verify_plan_independent(plan, manifest)
    mapping = v_plan.get("requirement_mapping") or {}
    id_by_file = {c["target_file"]: c["id"] for c in plan.get("contracts") or []}
    beh = (
        _inspect_behavioral_evidence(project_root, plan, post_ver)
        if project_root is not None
        else {"app_blob": "", "test_blob": "", "passing_tests_count": 0, "has_negative_assertion": False}
    )
    all_mandatory_ok = True

    for req in manifest.get("requirements") or []:
        rid = req["id"]
        kind = req.get("expected_kind")
        delivs = list(mapping.get(rid) or [])
        req["deliverables"] = delivs
        evidence: list[str] = []
        ok = False
        if kind == "tests":
            ok = bool(post_ver.get("tests_ok")) and bool(delivs) and all(
                statuses.get(id_by_file.get(f, "")) == "ACCEPTED" for f in delivs
            )
            evidence.append(f"tests_ok={post_ver.get('tests_ok')} sandbox={post_ver.get('tests_sandbox_used')} passing_cases={beh['passing_tests_count']}")
        elif kind == "http_server":
            ok = bool(post_ver.get("server_e2e_ok")) and bool(delivs) and all(
                statuses.get(id_by_file.get(f, "")) == "ACCEPTED" for f in delivs
            )
            sp = post_ver.get("server_probe") or {}
            evidence.append(f"server_e2e_ok={post_ver.get('server_e2e_ok')} http_status={sp.get('http_status')}")
        elif kind == "security":
            ok = bool(delivs) and all(statuses.get(id_by_file.get(f, "")) == "ACCEPTED" for f in delivs)
            evidence.append(f"accepted_deliverables={sum(1 for f in delivs if statuses.get(id_by_file.get(f, '')) == 'ACCEPTED')}/{len(delivs)}")
        elif kind == "business_capability":
            tokens = [str(t).lower() for t in (req.get("behavior_tokens") or [])]
            code_hits = [t for t in tokens if t in beh["app_blob"]]
            test_hits = [t for t in tokens if t in beh["test_blob"]]
            neg_ok = (not req.get("requires_negative_test")) or bool(beh["has_negative_assertion"])
            files_accepted = bool(delivs) and all(statuses.get(id_by_file.get(f, "")) == "ACCEPTED" for f in delivs)
            ok = bool(files_accepted and post_ver.get("tests_ok") and code_hits and test_hits and neg_ok)
            evidence.append(
                f"code_hits={code_hits[:4]} test_hits={test_hits[:4]} tests_ok={post_ver.get('tests_ok')} neg_test={beh['has_negative_assertion']}"
            )
        else:
            ok = bool(delivs) and all(statuses.get(id_by_file.get(f, "")) == "ACCEPTED" for f in delivs)
            evidence.extend(f"{f}:{statuses.get(id_by_file.get(f, ''))}" for f in delivs)
        req["status"] = "VERIFIED" if ok else "FAILED"
        req["evidence"] = evidence
        if req.get("mandatory") and not ok:
            all_mandatory_ok = False

    manifest["updated_at"] = _now_iso()
    manifest["all_mandatory_verified"] = all_mandatory_ok
    return manifest, all_mandatory_ok


def _identify_implicated_missions(plan: dict[str, Any], post_ver: dict[str, Any]) -> list[str]:
    """Identify which mission(s) caused a post-build integration failure (bounded targeted repair)."""
    contracts = list(plan.get("contracts") or [])
    implicated: list[str] = []
    blob = f"{post_ver.get('tests_output') or ''}\n{json.dumps(post_ver.get('server_probe') or {})}"

    if not post_ver.get("server_e2e_ok") and plan.get("server_entry"):
        for c in contracts:
            if c["target_file"] == plan["server_entry"]:
                implicated.append(c["id"])
    for c in contracts:
        tf = c["target_file"]
        stem = Path(tf).name
        if (tf in blob or stem in blob) and c["id"] not in implicated:
            implicated.append(c["id"])
    if not implicated and not post_ver.get("tests_ok"):
        for c in contracts:
            if c["target_file"].startswith("tests/"):
                implicated.append(c["id"])
    return implicated[:3]


# ---------------------------------------------------------------------------
# Main Autonomous Project Orchestration
# ---------------------------------------------------------------------------

def run_autonomous_project(
    *,
    goal_text: str,
    project_dir: Path,
    hybrid: bool = False,
    confidential: bool = False,
    explicit_specialist: str | None = None,
    resume_rejected: bool = False,
    allow_plan_revision: bool = False,
    require_sandbox: bool = True,
    sandbox_image: str = DEFAULT_SANDBOX_IMAGE,
    max_replan_rounds: int = MAX_REPLAN_ROUNDS,
    plan_override: dict[str, Any] | None = None,
    custom_executor=None,
) -> dict[str, Any]:
    """End-to-end autonomous project delivery via existing TEL99 Runtime, CAS, OS Sandbox, Memory, and Verifiers."""
    started = time.monotonic()
    inj = local_deterministic_tools.detect_prompt_injection(goal_text)
    if not inj["safe"]:
        return {"ok": False, "status": "BLOCKED", "reason": "prompt_injection_detected", "matches": inj["matches"]}

    kit = ensure_isolated_project_kit(project_dir)
    slug = kit.profile["project"]
    camp_dir = kit.state / f"campaign-{slug}"
    plan_path = kit.artifacts / "project_plan.json"
    manifest_path = kit.artifacts / "requirements_manifest.json"
    delivery_path = kit.artifacts / "delivery_report.json"
    attempts_dir = kit.artifacts / "attempts"
    staging_root = kit.artifacts / "staging"
    runner_lock_path = kit.state / "project_runner.lock"
    runner_pid_path = kit.state / "project_runner.pid.json"

    # Exclusive non-blocking per-project lock prevents duplicate concurrent runners
    try:
        lock_ctx = local_deterministic_tools.file_lock(runner_lock_path, timeout_s=0.15)
        lock_ctx.__enter__()
    except TimeoutError:
        return {
            "ok": False,
            "status": "LOCKED",
            "project": slug,
            "workspace_root": str(kit.root),
            "reason": "project_runner_already_active",
        }

    try:
        local_deterministic_tools.write_json_atomic_locked(
            runner_pid_path, {"pid": os.getpid(), "started_at": _now_iso(), "project": slug}
        )
        attempts_dir.mkdir(parents=True, exist_ok=True)
        staging_root.mkdir(parents=True, exist_ok=True)

        # Build / load persistent Requirements Manifest BEFORE planning
        goal_sha = _sha256_text(goal_text)
        scope_sha = _scope_config_hash(explicit_specialist=explicit_specialist, confidential=confidential)
        manifest = build_requirements_manifest(
            goal_text, project_slug=slug, explicit_specialist=explicit_specialist
        )
        local_deterministic_tools.write_json_atomic_locked(manifest_path, manifest)

        # Honest attribution: ONLY real LLM calls enter agents_called; deterministic verifiers tracked separately
        prior_delivery: dict[str, Any] = {}
        if delivery_path.is_file():
            try:
                prior_delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                prior_delivery = {}
        agents_called: set[str] = set(prior_delivery.get("agents_called") or [])
        deterministic_verifiers_run: set[str] = set(prior_delivery.get("deterministic_verifiers_run") or [])
        revision_summary: dict[str, Any] | None = None

        if plan_override is not None:
            new_plan = validate_and_normalize_plan(
                plan_override,
                project_root=kit.root,
                project_slug=slug,
                explicit_specialist=explicit_specialist,
                goal_text=goal_text,
                confidential=confidential,
                manifest=manifest,
                strict_dependencies=True,
            )
            if plan_path.is_file():
                old_plan = json.loads(plan_path.read_text(encoding="utf-8"))
                if (
                    old_plan.get("goal_sha256") and old_plan.get("goal_sha256") != goal_sha
                    and not allow_plan_revision
                ):
                    return {
                        "ok": False, "status": "BLOCKED", "project": slug,
                        "reason": "goal_or_scope_mismatch",
                        "expected_goal_sha256": old_plan.get("goal_sha256"),
                        "provided_goal_sha256": goal_sha,
                    }
                if allow_plan_revision:
                    new_plan, revision_summary = _apply_plan_revision(old_plan, new_plan, camp_dir)
            plan = new_plan
            coord_trace = {"agent": "tel99-coordination", "llm_called": False, "provider": "provided_plan", "model": "override", "cloud_calls": 0}
            local_deterministic_tools.write_json_atomic_locked(plan_path, plan)
        elif plan_path.is_file():
            old_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            old_goal_sha = old_plan.get("goal_sha256") or _sha256_text(old_plan.get("goal") or "")
            old_scope_sha = old_plan.get("scope_config_sha256")
            goal_changed = bool(goal_text.strip()) and old_goal_sha != goal_sha
            scope_changed = bool(old_scope_sha) and old_scope_sha != scope_sha
            if (goal_changed or scope_changed) and not allow_plan_revision:
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "project": slug,
                    "workspace_root": str(kit.root),
                    "reason": "goal_or_scope_mismatch",
                    "detail": "Existing sealed plan bound to a different goal or scope; pass --revise-plan to create a versioned revision.",
                    "expected_goal_sha256": old_goal_sha,
                    "provided_goal_sha256": goal_sha,
                }
            if (goal_changed or scope_changed) and allow_plan_revision:
                new_plan, coord_trace = generate_plan_with_coordinator(
                    goal_text=goal_text,
                    project_root=kit.root,
                    project_slug=slug,
                    manifest=manifest,
                    hybrid=hybrid,
                    confidential=confidential,
                    explicit_specialist=explicit_specialist,
                )
                if coord_trace.get("llm_called"):
                    agents_called.add(coord_trace["agent"])
                plan, revision_summary = _apply_plan_revision(old_plan, new_plan, camp_dir)
                plan["coordinator_trace"] = coord_trace
                local_deterministic_tools.write_json_atomic_locked(plan_path, plan)
            else:
                plan = old_plan
                coord_trace = plan.get("coordinator_trace") or {"agent": "tel99-coordination", "llm_called": False, "resumed": True}
        else:
            plan, coord_trace = generate_plan_with_coordinator(
                goal_text=goal_text,
                project_root=kit.root,
                project_slug=slug,
                manifest=manifest,
                hybrid=hybrid,
                confidential=confidential,
                explicit_specialist=explicit_specialist,
            )
            if coord_trace.get("llm_called"):
                agents_called.add(coord_trace["agent"])
            plan["coordinator_trace"] = coord_trace
            local_deterministic_tools.write_json_atomic_locked(plan_path, plan)

        # Independent plan check before execution
        plan_ver = verify_plan_independent(plan, manifest)
        deterministic_verifiers_run.add("independent_plan_verifier")
        if not plan_ver["ok"]:
            return {
                "ok": False,
                "status": "BLOCKED",
                "project": slug,
                "workspace_root": str(kit.root),
                "reason": "plan_verification_failed",
                "issues": plan_ver["issues"],
                "plan_verification": plan_ver,
            }

        contracts = plan["contracts"]
        approvals = plan["approvals"]
        meta_by_id = plan["mission_meta"]
        mem_store = MemoryStore(kit.memory)
        traj_rec = metacognition.TrajectoryRecorder(kit.artifacts)
        flib = metacognition.FailureLibrary(kit.artifacts, memory_root=kit.memory)

        missions_report: dict[str, Any] = dict(prior_delivery.get("missions") or {})
        total_cloud_calls = int(coord_trace.get("cloud_calls") or 0)
        pending_memory_entries: list[Entry] = []
        integration_feedback: dict[str, str] = {}

        def _default_executor(m: dict) -> dict:
            nonlocal total_cloud_calls
            mid = m["id"]
            target_rel = m["target_file"]
            target_path = local_deterministic_tools.safe_subpath(
                kit.root, target_rel, blocked_top_dirs=RESERVED_PROJECT_TOP_DIRS
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            spec_name = m["specialist"]
            role = next((r for r, s in team_config.role_catalog().items() if s.name == spec_name), "development")
            req_syms = (meta_by_id.get(mid) or {}).get("required_symbols") or []

            ctx = mentor_curriculum.build_two_layer_generalist_context(
                agent_role=role,
                target_domain=role,
                skills_dir=SKILLS_DIR,
                memory_dir=kit.memory if kit.memory.is_dir() else SHARED_MEM_DIR,
                objective=m["objective"],
            )
            dep_ctx = _build_dependency_context(kit.root, m.get("dependencies") or [], meta_by_id)
            ext = target_path.suffix.lower()

            # Backup existing valid file into staging before attempting modifications
            m_stage = staging_root / mid
            m_stage.mkdir(parents=True, exist_ok=True)
            backup_path = m_stage / "_backup" / target_rel
            had_existing = target_path.is_file()
            if had_existing:
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_path, backup_path)

            attempts_log: list[dict] = []
            prior_hashes: list[str] = []
            last_code = ""
            prev_code = ""
            last_ver: dict[str, Any] = {"ok": False, "error": "not run", "checks_passed": []}
            max_att = int(m.get("max_attempts") or 4)
            infra_failures = 0
            model_attempt = 0
            m_t0 = time.monotonic()

            while model_attempt < max_att:
                while (camp_dir / "pause.request").exists() and not (camp_dir / "stop.request").exists():
                    time.sleep(1.5)
                if (camp_dir / "stop.request").exists():
                    raise autonomy_runtime.Blocked("stopped by operator request")

                model_attempt += 1
                extra_int = integration_feedback.get(mid) or ""
                sys_p = smart_repair.build_structured_reasoning_prompt(
                    role=spec_name,
                    objective=f"Produce complete, clean, working file `{target_rel}` for project `{slug}`.",
                    constraints=[
                        "Output ONLY the complete file content inside a single code block (zero explanatory prose outside).",
                        "ZERO unnecessary comments or verbose docstrings; keep concise and syntactically complete.",
                        "Security: loopback 127.0.0.1 only (NEVER 0.0.0.0), NO eval/exec/os.system/pickle.loads/shell=True/inline <script>/innerHTML.",
                        "Python 3.12 stdlib only; always check `isinstance(x, bool)` before `int`/`float`.",
                    ],
                )
                if model_attempt == 1 and not extra_int:
                    usr_p = (
                        f"Target file: {target_rel}\n"
                        f"Required symbols/tokens: {req_syms}\n"
                        f"Specification:\n{m['objective']}\n\n"
                        + (f"Project dependencies (MATCH EXACT SIGNATURES/ROUTES/IDS):\n{dep_ctx}\n\n" if dep_ctx else "")
                        + f"{ctx['context_text']}"
                    )
                else:
                    prev_err = extra_int if (model_attempt == 1 and extra_int) else str(last_ver.get("error") or "verification failed")
                    diff = smart_repair.compute_bounded_diff(prev_code, last_code) if prev_code else ""
                    seed_code = last_code or (target_path.read_text(encoding="utf-8", errors="replace") if target_path.is_file() else "")
                    usr_p = (
                        f"Target file: {target_rel}\n"
                        f"Required symbols/tokens: {req_syms}\n"
                        f"Specification:\n{m['objective']}\n\n"
                        + (f"Project dependencies:\n{dep_ctx}\n\n" if dep_ctx else "")
                        + smart_repair.build_smart_repair_prompt(
                            previous_code=seed_code,
                            exact_error=prev_err,
                            passed_checks=last_ver.get("checks_passed", []),
                            failed_checks=[prev_err[:120]],
                            contract_constraints=[
                                f"Keep complete valid `{target_rel}` with zero comments/truncation",
                                f"Ensure required symbols/tokens exist: {req_syms}",
                            ],
                            prior_attempts=attempts_log,
                            memory_lessons=[],
                            previous_diff=diff,
                            target_file=target_rel,
                            role=spec_name,
                        )
                    )

                t0 = time.monotonic()
                is_infra_err = False
                try:
                    raw, prov, mdl, cc, _meta = _call_model(
                        system=sys_p,
                        prompt=usr_p,
                        hybrid=hybrid,
                        confidential=confidential,
                        attempt=model_attempt,
                        role=role,
                        estimated_lines=80 if ext in (".html", ".css", ".js", ".py") else 45,
                        allow_continue=ext in (".html", ".css", ".js", ".py"),
                    )
                    agents_called.add(spec_name)
                    total_cloud_calls += cc
                    code = ollama_native.extract_code_block(raw)
                    if ext == ".py":
                        code = local_deterministic_tools.strip_trailing_example_blocks(code)
                    fp = smart_repair.code_fingerprint(code)
                    repeated = smart_repair.detect_repeated_attempt(code, prior_hashes)
                    prior_hashes.append(fp)

                    # Write candidate to staging first, then atomic promote to target for sandboxed verification
                    staged_candidate = m_stage / target_rel
                    staged_candidate.parent.mkdir(parents=True, exist_ok=True)
                    staged_candidate.write_text(code, encoding="utf-8")
                    tmp_promote = target_path.parent / f".{target_path.name}.{os.getpid()}.tmp"
                    tmp_promote.write_text(code, encoding="utf-8")
                    os.replace(tmp_promote, target_path)

                    ver = verify_delivered_file(
                        kit.root,
                        target_rel,
                        required_symbols=req_syms,
                        require_sandbox=require_sandbox,
                        sandbox_image=sandbox_image,
                    )
                    deterministic_verifiers_run.update(ver.get("verifiers_run") or [])
                    if not ver.get("ok") and had_existing and backup_path.is_file():
                        shutil.copy2(backup_path, target_path)
                    if repeated and not ver["ok"]:
                        ver["error"] = f"REPEATED_ATTEMPT: {ver.get('error')}"
                except ProviderError as exc:
                    is_infra_err = True
                    infra_failures += 1
                    prov, mdl, cc = "infra_error", LOCAL_MODEL, 0
                    code, fp, repeated = "", "", False
                    ver = {"ok": False, "security_ok": True, "error": f"ProviderError: {str(exc)[:200]}", "checks_passed": []}
                except Exception as exc:
                    prov, mdl, cc = "error", LOCAL_MODEL, 0
                    code, fp, repeated = "", "", False
                    ver = {"ok": False, "security_ok": True, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "checks_passed": []}

                entry_log = {
                    "attempt": model_attempt,
                    "infra_error": is_infra_err,
                    "infra_failures": infra_failures,
                    "provider": prov,
                    "model": mdl,
                    "cloud_calls": cc,
                    "seconds": round(time.monotonic() - t0, 2),
                    "code_sha256": fp,
                    "repeated": repeated,
                    "ok": bool(ver.get("ok")),
                    "sandbox_used": bool(ver.get("sandbox_used")),
                    "error": ver.get("error"),
                    "checks_passed": ver.get("checks_passed", []),
                    "recorded_at": _now_iso(),
                }
                attempts_log.append(entry_log)
                # Persist per-attempt history immediately (crash-safe)
                local_deterministic_tools.write_json_atomic_locked(
                    attempts_dir / f"{mid}.json",
                    {"mission_id": mid, "target_file": target_rel, "specialist": spec_name, "attempts": attempts_log},
                )
                print(json.dumps({"project": slug, "mission": mid, "file": target_rel, "role": spec_name, "att": model_attempt, "model": mdl, "ok": ver.get("ok"), "err": ver.get("error")}), flush=True)

                if ver.get("ok"):
                    last_code = code
                    last_ver = ver
                    break

                if is_infra_err:
                    # Do NOT burn a model attempt for transient infra errors up to MAX_INFRA_RETRIES
                    if infra_failures <= MAX_INFRA_RETRIES:
                        model_attempt -= 1
                        time.sleep(min(2.0, 0.5 * infra_failures))
                        continue
                    last_ver = ver
                    break

                prev_code = last_code
                last_code = code
                last_ver = ver

            repaired = bool(last_ver.get("ok") and sum(1 for a in attempts_log if not a.get("infra_error")) > 1)
            m_dur = round(time.monotonic() - m_t0, 2)
            last_mdl = attempts_log[-1]["model"] if attempts_log else LOCAL_MODEL

            traj_rec.record(
                project=slug,
                mission_id=mid,
                objective=m["objective"][:400],
                model=last_mdl,
                role=spec_name,
                tools_used=[{"tool": "autonomy_runtime", "contract": "project-file"}, {"tool": "verify_delivered_file", "target": target_rel}],
                decisions=[f"specialist={spec_name}", f"deps={m.get('dependencies')}"],
                errors=[str(a["error"]) for a in attempts_log if a.get("error")],
                repairs=attempts_log[1:],
                tests=[{"ok": bool(last_ver.get("ok")), "checks_passed": last_ver.get("checks_passed", [])}],
                artifacts=[target_rel],
                verdict="SUCCESS" if last_ver.get("ok") else "FAILURE",
                duration_seconds=m_dur,
                cost_usd=0.0,
            )
            if any(a.get("error") for a in attempts_log):
                first_err = next((str(a["error"]) for a in attempts_log if a.get("error")), "unknown")
                err_low = first_err.lower()
                if "security" in err_low or "forbidden" in err_low or "scope" in err_low:
                    meta_cat = "PERMISSION_ERROR"
                elif "providererror" in err_low or "timed out" in err_low or "unavailable" in err_low or "busy" in err_low:
                    meta_cat = "ENGINE_ERROR"
                elif "unbalanced" in err_low or "never closed" in err_low or "unterminated" in err_low:
                    meta_cat = "TRUNCATED_OUTPUT"
                elif "repeated_attempt" in err_low:
                    meta_cat = "INEFFECTIVE_REPAIR"
                elif "unittest" in err_low or "assertion" in err_low or "missing required" in err_low:
                    meta_cat = "VERIFICATION_ERROR"
                else:
                    meta_cat = "PROGRAMMING_ERROR"
                try:
                    flib.record_failure(
                        project=slug,
                        mission_id=mid,
                        category=meta_cat,
                        context_summary=f"{slug}:{target_rel}",
                        cause=first_err[:240],
                        cause_confirmed=bool(last_ver.get("ok")),
                        evidence=f"attempts={len(attempts_log)} ok={bool(last_ver.get('ok'))}",
                        attempts=attempts_log,
                        validated_solution=f"Repaired on attempt {len(attempts_log)}" if repaired else "",
                        preventive_measure="Use AST dependency context + sandboxed deterministic verifier feedback",
                        model=last_mdl,
                        role=spec_name,
                    )
                except (OSError, ValueError):
                    pass

            # Stage memory lesson ONLY — never promote before full post-build integration verification passes!
            if last_ver.get("ok"):
                eid = f"{'fix' if repaired else 'proc'}-{mid}"
                pending_memory_entries.append(
                    Entry(
                        id=eid,
                        project=slug,
                        kind="fix" if repaired else "procedure",
                        title=f"{'Repaired' if repaired else 'Delivered'} {target_rel}",
                        body=f"{spec_name} delivered {target_rel} ({', '.join(last_ver.get('checks_passed', []))}) in {len(attempts_log)} attempt(s).",
                        tags=(mid, target_rel, role),
                        source=f"{slug}/{mid}",
                        author=spec_name,
                        verified=True,
                        verified_by="tel99-independent-verifier",
                        confidence=0.95 if repaired else 0.9,
                    )
                )

            artifact_text = target_path.read_text(encoding="utf-8", errors="replace") if target_path.is_file() else ""
            file_sha = hashlib.sha256(artifact_text.encode("utf-8")).hexdigest()
            missions_report[mid] = {
                "id": mid,
                "target_file": target_rel,
                "specialist": spec_name,
                "model_used": last_mdl,
                "attempts": len(attempts_log),
                "infra_failures": infra_failures,
                "repaired": repaired,
                "status": "ACCEPTED" if last_ver.get("ok") else "REJECTED",
                "sandbox_used": bool(last_ver.get("sandbox_used")),
                "file_sha256": file_sha,
                "checks_passed": last_ver.get("checks_passed", []),
                "error": last_ver.get("error"),
                "duration_seconds": m_dur,
                "attempts_log": attempts_log,
            }
            return {
                "artifact": artifact_text,
                "sha256": file_sha,
                "specialist_id": spec_name,
                "model": last_mdl,
                "target_file": target_rel,
                "attempts": len(attempts_log),
                "repaired": repaired,
            }

        def _independent_verifier(m: dict, result: dict) -> dict:
            mid = m["id"]
            target_rel = m["target_file"]
            req_syms = (meta_by_id.get(mid) or {}).get("required_symbols") or []
            ver = verify_delivered_file(
                kit.root,
                target_rel,
                required_symbols=req_syms,
                require_sandbox=require_sandbox,
                sandbox_image=sandbox_image,
            )
            deterministic_verifiers_run.update(ver.get("verifiers_run") or [])
            try:
                target_path = local_deterministic_tools.safe_subpath(
                    kit.root, target_rel, blocked_top_dirs=RESERVED_PROJECT_TOP_DIRS
                )
                art_sha = (
                    hashlib.sha256(target_path.read_text(encoding="utf-8", errors="replace").encode("utf-8")).hexdigest()
                    if target_path.is_file()
                    else result.get("sha256")
                )
            except ValueError:
                art_sha = result.get("sha256")
            ok = bool(ver.get("ok"))
            passed_names = list(ver.get("checks_passed") or [])
            checks = [{"name": name, "ok": True} for name in passed_names] if (ok and passed_names) else [{"name": "independent_verify", "ok": ok}]
            return {
                "verifier": "tel99-independent-project-verifier",
                "ok": ok,
                "security_ok": bool(ver.get("security_ok", True)),
                "sandbox_used": bool(ver.get("sandbox_used")),
                "project": m["project"],
                "target_file": target_rel,
                "artifact_sha256": art_sha,
                "error": ver.get("error"),
                "checks": checks,
                "checks_passed": passed_names,
            }

        if resume_rejected:
            from scripts.agents.automation.local_codex import exclusive
            from scripts.agents.protocol.store import FileStore
            camp_dir.mkdir(parents=True, exist_ok=True)
            to_requeue: list[str] = []
            with exclusive(camp_dir / "runtime.lock"):
                st = FileStore(camp_dir / "ledger")
                for c in contracts:
                    old = st.read(f"kilo-local/{c['id']}")
                    if old and old.get("status") in ("REJECTED", "BLOCKED"):
                        to_requeue.append(c["id"])
            _requeue_ledger_missions(camp_dir, to_requeue, reason="operator_resume_rejected")

        # Keep Runtime shared_memory_root isolated in staging until full integration verification succeeds
        staging_mem = camp_dir / "staged_memory"
        rt = Runtime(
            camp_dir,
            executor=custom_executor or _default_executor,
            verifier=_independent_verifier,
            shared_memory_root=staging_mem,
            auto_recover_local_crash=True,
        )

        def _run_batched_queue() -> None:
            if len(contracts) <= 20:
                rt.run_queue(contracts, approvals, max_tasks=len(contracts))
                return
            by_id_c = {c["id"]: c for c in contracts}
            idx = 0
            while idx < len(contracts):
                window_ids: list[str] = []
                window_set: set[str] = set()
                progressed_chunk = 0
                while idx < len(contracts):
                    cand = contracts[idx]
                    needed = [d for d in cand.get("dependencies") or [] if d in by_id_c and d not in window_set]
                    add_count = len(needed) + (0 if cand["id"] in window_set else 1)
                    if window_ids and len(window_ids) + add_count > 20:
                        break
                    for d in needed:
                        window_ids.append(d)
                        window_set.add(d)
                    if cand["id"] not in window_set:
                        window_ids.append(cand["id"])
                        window_set.add(cand["id"])
                    idx += 1
                    progressed_chunk += 1
                    if progressed_chunk >= RUNTIME_BATCH_SIZE:
                        break
                window = [by_id_c[mid] for mid in window_ids]
                rt.run_queue(window, approvals, max_tasks=len(window))

        replan_rounds_used = 0
        replan_history: list[dict[str, Any]] = []
        _run_batched_queue()

        while True:
            statuses = {c["id"]: rt.state(c).get("status") for c in contracts}
            accepted = sum(1 for s in statuses.values() if s == "ACCEPTED")
            all_accepted = accepted == len(contracts) and len(contracts) > 0
            post_ver = _run_post_build_verification(
                kit.root, plan, require_sandbox=require_sandbox, sandbox_image=sandbox_image
            )
            deterministic_verifiers_run.update(post_ver.get("verifiers_run") or [])
            tests_ok = bool(post_ver.get("tests_ok"))
            server_e2e_ok = bool(post_ver.get("server_e2e_ok"))
            manifest, all_mandatory_verified = _update_manifest_with_results(
                manifest, plan, statuses, post_ver, project_root=kit.root
            )

            if all_accepted and tests_ok and server_e2e_ok and all_mandatory_verified:
                break
            if replan_rounds_used >= max(0, int(max_replan_rounds)):
                break

            implicated = _identify_implicated_missions(plan, post_ver)
            # Also implicate REJECTED/BLOCKED missions or core+test missions when mandatory business capabilities failed
            failed_reqs = [r for r in manifest.get("requirements") or [] if r.get("mandatory") and r.get("status") != "VERIFIED"]
            if not all_accepted:
                for c in contracts:
                    if statuses.get(c["id"]) in ("REJECTED", "BLOCKED") and c["id"] not in implicated:
                        implicated.append(c["id"])
            if failed_reqs and not implicated:
                for c in contracts:
                    if c["target_file"].endswith(".py") and c["id"] not in implicated:
                        implicated.append(c["id"])
            implicated = implicated[:4]
            if not implicated:
                break
            replan_rounds_used += 1
            failed_req_summary = "; ".join(f"{r['id']}({r.get('source_text', '')[:60]})" for r in failed_reqs[:4])
            int_err = (
                f"Integration/business verification failed (round {replan_rounds_used}): "
                f"tests_ok={tests_ok} ({str(post_ver.get('tests_output') or '')[-180:]}); "
                f"server_e2e_ok={server_e2e_ok} ({json.dumps(post_ver.get('server_probe') or {})[:180]}); "
                f"unverified_reqs=[{failed_req_summary}]"
            )
            for mid in implicated:
                integration_feedback[mid] = int_err
            _requeue_ledger_missions(camp_dir, implicated, reason=f"integration_replan_round_{replan_rounds_used}")
            replan_history.append({
                "round": replan_rounds_used,
                "implicated_missions": implicated,
                "failed_requirements": [r["id"] for r in failed_reqs],
                "reason": int_err[:400],
                "at": _now_iso(),
            })
            _run_batched_queue()

        # Persist final requirement coverage matrix
        local_deterministic_tools.write_json_atomic_locked(manifest_path, manifest)

        overall_ok = bool(all_accepted and tests_ok and server_e2e_ok and all_mandatory_verified)
        final_status = "DELIVERED" if overall_ok else ("PARTIAL" if accepted > 0 else "BLOCKED")

        # Memory Promotion Gate: promote verified lessons ONLY when full integration verification passes!
        promoted_lessons = 0
        if overall_ok:
            for entry in pending_memory_entries:
                if mem_store.get(slug, entry.id) is None:
                    mem_store.record(entry, actor="autonomous-project-runner-verified")
                    promoted_lessons += 1

        # Programmatic Tool Calling (Anthropic §5.3): 0-LLM deterministic check on generated files
        ptc_files: dict[str, str] = {}
        for c in contracts:
            rel_f = str(c.get("target_file") or "")
            fp = kit.root / rel_f
            if rel_f and fp.is_file() and fp.stat().st_size <= 256_000:
                try:
                    ptc_files[rel_f] = fp.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
        ptc_ver = None
        if ptc_files:
            try:
                from scripts.agents.automation import evolution_lab as _ev_lab
                ptc_ver = _ev_lab.run_programmatic_tool_batch(ptc_files)
            except Exception as exc:
                ptc_ver = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        delivery = {
            "schema_version": 2,
            "status": final_status,
            "ok": overall_ok,
            "project": slug,
            "workspace_root": str(kit.root),
            "ptc_verification": ptc_ver,
            "goal": goal_text,
            "goal_sha256": goal_sha,
            "plan_revision": int(plan.get("plan_revision") or 1),
            "revision_summary": revision_summary,
            "replan_rounds_used": replan_rounds_used,
            "replan_history": replan_history,
            "finished_at": _now_iso(),
            "duration_seconds": round(time.monotonic() - started, 2),
            "coordinator_trace": coord_trace,
            "agents_called": sorted(agents_called),
            "agents_mobilized": sorted(agents_called),
            "deterministic_verifiers_run": sorted(deterministic_verifiers_run),
            "sandbox_required": bool(require_sandbox),
            "all_mandatory_requirements_verified": all_mandatory_verified,
            "promoted_memory_lessons": promoted_lessons,
            "missions_accepted": accepted,
            "missions_total": len(contracts),
            "runtime_statuses": statuses,
            "cloud_calls": total_cloud_calls,
            "cost_usd": 0.0,
            "startup_command": plan.get("startup_command"),
            "server_entry": plan.get("server_entry"),
            "test_command": plan.get("test_command"),
            "post_build_verification": post_ver,
            "deliverables": [
                {
                    "file": c["target_file"],
                    "specialist": c["specialist"],
                    "status": statuses.get(c["id"]),
                    "sha256": (missions_report.get(c["id"]) or {}).get("file_sha256"),
                }
                for c in contracts
            ],
            "missions": missions_report,
        }
        local_deterministic_tools.write_json_atomic_locked(delivery_path, delivery)
        return delivery
    finally:
        runner_pid_path.unlink(missing_ok=True)
        lock_ctx.__exit__(None, None, None)


def _is_runner_active(project_root: Path) -> bool:
    lock_p = project_root / "state" / "project_runner.lock"
    if not lock_p.exists():
        return False
    try:
        with local_deterministic_tools.file_lock(lock_p, timeout_s=0.05):
            return False
    except TimeoutError:
        return True
    except OSError:
        return False


def get_project_progress(project_dir: Path) -> dict[str, Any]:
    """Read LIVE durable progress (Runtime ledger + manifest + attempts + delivery report)."""
    root = project_dir.resolve()
    plan_p = root / "artifacts" / "project_plan.json"
    manifest_p = root / "artifacts" / "requirements_manifest.json"
    deliv_p = root / "artifacts" / "delivery_report.json"
    attempts_dir = root / "artifacts" / "attempts"
    kit_p = root / "project.json"
    runner_active = _is_runner_active(root)

    out: dict[str, Any] = {
        "workspace_root": str(root),
        "initialized": kit_p.is_file(),
        "plan_exists": plan_p.is_file(),
        "manifest_exists": manifest_p.is_file(),
        "delivery_exists": deliv_p.is_file(),
        "runner_active": runner_active,
    }
    slug = None
    camp = None
    if kit_p.is_file():
        prof = json.loads(kit_p.read_text(encoding="utf-8"))
        slug = prof["project"]
        camp = root / "state" / f"campaign-{slug}"
        out["project"] = slug
        out["paused"] = (camp / "pause.request").exists()
        out["stopped"] = (camp / "stop.request").exists()

    # Live Runtime ledger inspection (works BEFORE delivery_report.json exists!)
    live_statuses: dict[str, str] = {}
    contracts: list[dict[str, Any]] = []
    if plan_p.is_file():
        plan = json.loads(plan_p.read_text(encoding="utf-8"))
        contracts = list(plan.get("contracts") or [])
        out["goal"] = plan.get("goal")
        out["plan_revision"] = int(plan.get("plan_revision") or 1)
        out["startup_command"] = plan.get("startup_command")
        out["missions_total"] = len(contracts)
        if camp is not None and (camp / "ledger").is_dir():
            from scripts.agents.protocol.store import FileStore
            st = FileStore(camp / "ledger")
            for c in contracts:
                rec = st.read(f"kilo-local/{c['id']}")
                live_statuses[c["id"]] = (rec or {}).get("status") or "PENDING"
        else:
            for c in contracts:
                live_statuses[c["id"]] = "PENDING"
        accepted_live = sum(1 for s in live_statuses.values() if s == "ACCEPTED")
        out["missions_accepted"] = accepted_live
        out["runtime_statuses"] = live_statuses
        out["deliverables"] = [
            {"file": c["target_file"], "specialist": c["specialist"], "status": live_statuses.get(c["id"])}
            for c in contracts
        ]
        if out.get("stopped"):
            out["status"] = "STOPPED"
        elif out.get("paused"):
            out["status"] = "PAUSED"
        elif runner_active:
            out["status"] = "RUNNING"
        elif accepted_live == len(contracts) and contracts:
            out["status"] = "ACCEPTED_PENDING_POST_VERIFY"
        elif accepted_live > 0:
            out["status"] = "PARTIAL"
        else:
            out["status"] = "PENDING"

    if manifest_p.is_file():
        mf = json.loads(manifest_p.read_text(encoding="utf-8"))
        reqs = mf.get("requirements") or []
        out["requirements_summary"] = {
            "total": len(reqs),
            "mandatory": sum(1 for r in reqs if r.get("mandatory")),
            "verified": sum(1 for r in reqs if r.get("status") == "VERIFIED"),
            "all_mandatory_verified": bool(mf.get("all_mandatory_verified")),
        }

    if attempts_dir.is_dir():
        att_counts: dict[str, int] = {}
        for ap_file in sorted(attempts_dir.glob("*.json")):
            try:
                ad = json.loads(ap_file.read_text(encoding="utf-8"))
                att_counts[ap_file.stem] = len(ad.get("attempts") or [])
            except (OSError, ValueError):
                continue
        out["attempts_recorded"] = att_counts

    if deliv_p.is_file() and not runner_active:
        d = json.loads(deliv_p.read_text(encoding="utf-8"))
        out.update({
            "status": d.get("status"),
            "ok": d.get("ok"),
            "missions_accepted": d.get("missions_accepted"),
            "missions_total": d.get("missions_total"),
            "runtime_statuses": d.get("runtime_statuses"),
            "agents_called": d.get("agents_called", d.get("agents_mobilized")),
            "agents_mobilized": d.get("agents_mobilized"),
            "deterministic_verifiers_run": d.get("deterministic_verifiers_run"),
            "startup_command": d.get("startup_command"),
            "deliverables": d.get("deliverables"),
            "post_build_verification": d.get("post_build_verification"),
        })
    return out


def control_project(project_dir: Path, action: str) -> dict[str, Any]:
    """Pause, resume, or cleanly stop an autonomous project campaign without losing checkpoints."""
    kit = project_kit.load(project_dir)
    camp = kit.state / f"campaign-{kit.profile['project']}"
    camp.mkdir(parents=True, exist_ok=True)
    pause_f = camp / "pause.request"
    stop_f = camp / "stop.request"
    if action == "pause":
        pause_f.write_text(_now_iso() + "\n", encoding="utf-8")
    elif action == "stop":
        stop_f.write_text(_now_iso() + "\n", encoding="utf-8")
    elif action == "resume":
        pause_f.unlink(missing_ok=True)
        stop_f.unlink(missing_ok=True)
    else:
        raise ValueError(f"unknown control action: {action!r}")
    return {
        "ok": True,
        "project": kit.profile["project"],
        "action": action,
        "paused": pause_f.exists(),
        "stopped": stop_f.exists(),
        "runner_active": _is_runner_active(kit.root),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", type=Path, required=True, help="Isolated local target project directory")
    ap.add_argument("--task", type=str, default="", help="Project goal/specification for the autonomous team")
    ap.add_argument("--role", type=str, default=None, help="Optional explicit specialist role")
    ap.add_argument("--hybrid", action="store_true", help="Allow free Groq mentor escalation ($0.00, non-confidential only)")
    ap.add_argument("--confidential", action="store_true", help="Force 100% local Ollama execution")
    ap.add_argument("--resume-rejected", action="store_true", help="Requeue REJECTED/BLOCKED missions while strictly preserving ACCEPTED ones")
    ap.add_argument("--revise-plan", action="store_true", help="Allow creating a versioned sealed plan revision when goal/scope changed")
    ap.add_argument("--progress", action="store_true", help="Print live durable progress and deliverables")
    ap.add_argument("--control", choices=["pause", "resume", "stop"], default=None, help="Pause/resume/stop project run")
    ap.add_argument("--resume-process", action="store_true", help="Clear pause/stop markers and resume an exited project using its stored sealed goal")
    args = ap.parse_args(argv)

    if args.progress:
        print(json.dumps(get_project_progress(args.project), indent=2, ensure_ascii=False))
        return 0
    if args.control and not args.resume_process:
        print(json.dumps(control_project(args.project, args.control), indent=2, ensure_ascii=False))
        return 0

    task_text = args.task.strip()
    if args.resume_process:
        ctrl = control_project(args.project, "resume")
        if ctrl.get("runner_active"):
            print(json.dumps({**ctrl, "restarted": False, "note": "runner already active; pause/stop markers cleared"}, indent=2, ensure_ascii=False))
            return 0
        plan_p = args.project.resolve() / "artifacts" / "project_plan.json"
        if not task_text and plan_p.is_file():
            task_text = str(json.loads(plan_p.read_text(encoding="utf-8")).get("goal") or "").strip()
        if not task_text:
            print(json.dumps({**ctrl, "ok": False, "error": "no stored goal found in project_plan.json to resume"}, indent=2, ensure_ascii=False))
            return 2

    if not task_text:
        print(json.dumps({"ok": False, "error": "--task is required to run an autonomous project"}, indent=2))
        return 2

    delivery = run_autonomous_project(
        goal_text=task_text,
        project_dir=args.project,
        hybrid=args.hybrid,
        confidential=args.confidential,
        explicit_specialist=args.role,
        resume_rejected=args.resume_rejected,
        allow_plan_revision=args.revise_plan,
        require_sandbox=True,
    )
    print(json.dumps({
        "status": delivery.get("status"),
        "ok": delivery.get("ok"),
        "project": delivery.get("project"),
        "workspace_root": delivery.get("workspace_root"),
        "plan_revision": delivery.get("plan_revision"),
        "missions_accepted": delivery.get("missions_accepted"),
        "missions_total": delivery.get("missions_total"),
        "agents_called": delivery.get("agents_called"),
        "deterministic_verifiers_run": delivery.get("deterministic_verifiers_run"),
        "all_mandatory_requirements_verified": delivery.get("all_mandatory_requirements_verified"),
        "startup_command": delivery.get("startup_command"),
        "post_build_verification": delivery.get("post_build_verification"),
        "deliverables": delivery.get("deliverables"),
        "reason": delivery.get("reason"),
    }, indent=2, ensure_ascii=False))
    return 0 if delivery.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
