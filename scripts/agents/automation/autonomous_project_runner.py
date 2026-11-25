"""TEL99 Autonomous Multi-Agent Project Runner (REUSE-FIRST, zero new supervisor).

Connects `launch-tel99.ps1` directly to existing TEL99 autonomous infrastructure:
- `project_kit` (isolated project workspace, state, memory, artifacts)
- `autonomy_runtime.Runtime.run_queue` + `project-file` sealed contracts (CAS claims, Inbox ACKs, zero replay)
- `mission_planner.assess_and_decompose_mission` + `TopologicalSorter` DAG ordering
- `specialist_dispatch` (12 official TEL99 roles selected on demand)
- `context_engine` (AST code graph + SQLite FTS5 hybrid memory + structured JSON validation)
- `mentor_curriculum` (2-layer generalist + specialized role Skill context)
- `local_deterministic_tools` (deterministic security gate + atomic file-locked JSON)
- `smart_repair` (root-cause error diagnostics, bounded diff, SHA-256 anti-repetition)
- `metacognition` (`TrajectoryRecorder`, `FailureLibrary`, secret scrubbing)
- `ollama_native.OllamaNativeProvider` (concurrence=1 CAS lease) + optional free Groq mentors (`--hybrid`, $0.00)

Domain-agnostic: contains ZERO project-specific code templates. The agents themselves design,
code, test, independently verify, repair, learn, and deliver any authorized local project.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
from graphlib import CycleError, TopologicalSorter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agents import project_kit, specialist_dispatch, team_config
from scripts.agents.automation import (
    autonomy_runtime,
    context_engine,
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
from scripts.agents.native.provider import ProviderError

LOCAL_MODEL = "gemma4:e4b-tel99-8k"
SKILLS_DIR = ROOT / ".agents" / "skills"
SHARED_MEM_DIR = Path.home() / "Desktop" / "TEL99_BENCHMARK_120_STATE" / "memory"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify_project(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)[:44]
    if not slug or slug == "synthetic" or len(slug) < 2:
        slug = "tel99-project"
    return slug


def _safe_mission_id(raw: str, idx: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9-]+", "-", str(raw or "")).strip("-")[:40]
    return cleaned or f"m-{idx:02d}"


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
        # Existing empty or partially initialized folder: create kit dirs & project.json atomically
        for sub in ("state", "memory", "artifacts"):
            (project_dir / sub).mkdir(parents=True, exist_ok=True)
        local_deterministic_tools.write_json_atomic_locked(project_dir / "project.json", profile)
        return project_kit.load(project_dir)
    return project_kit.install(project_dir, profile)


def validate_and_normalize_plan(
    raw_plan: dict[str, Any],
    *,
    project_root: Path,
    project_slug: str,
    explicit_specialist: str | None = None,
    goal_text: str = "",
) -> dict[str, Any]:
    """Deterministically validate, normalize, and seal a coordinator-generated project plan."""
    if not isinstance(raw_plan, dict):
        raise ValueError("coordinator plan must be a JSON object")
    raw_missions = raw_plan.get("missions")
    if not isinstance(raw_missions, list) or not 1 <= len(raw_missions) <= 12:
        raise ValueError("coordinator plan must define 1..12 bounded missions")

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

    # First pass: sanitize IDs, target files, and build allowed_paths
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
        # Assess mission size via existing mission_planner
        assess = mission_planner.assess_and_decompose_mission(
            {"id": mid, "path": tf, "estimated_lines": int(item.get("estimated_lines") or 60), "objective": obj[:250]},
            max_safe_lines=85,
        )
        normalized.append({
            "id": mid,
            "specialist": spec_name,
            "target_file": tf,
            "raw_deps": list(item.get("dependencies") or []),
            "objective": obj[:3500],
            "required_symbols": req_syms,
            "task_profile": assess.get("recommended_profile", "module"),
            "priority": f"P{min(idx, 9)}",
            "max_attempts": 4,
        })

    allowed_paths = [m["target_file"] for m in normalized]
    id_set = {m["id"] for m in normalized}

    # Verify requested deliverable types from goal_text are actually planned (generic completeness gate)
    g_low = (goal_text or "").lower()
    if g_low:
        missing_types: list[str] = []
        if ("html" in g_low or "interface web" in g_low) and not any(p.endswith(".html") for p in allowed_paths):
            missing_types.append("web/index.html")
        if ("styles.css" in g_low or "css" in g_low) and not any(p.endswith(".css") for p in allowed_paths):
            missing_types.append("web/styles.css")
        if ("app.js" in g_low or ".js" in g_low) and not any(p.endswith(".js") for p in allowed_paths):
            missing_types.append("web/app.js")
        if ("unittest" in g_low or "tests/" in g_low) and not any(p.startswith("tests/test_") and p.endswith(".py") for p in allowed_paths):
            missing_types.append("tests/test_*.py")
        if ("readme" in g_low or "documentation" in g_low) and not any(p.lower().endswith("readme.md") for p in allowed_paths):
            missing_types.append("README.md")
        if ("start.ps1" in g_low or ".ps1" in g_low) and not any(p.endswith(".ps1") for p in allowed_paths):
            missing_types.append("start.ps1")
        if missing_types:
            raise ValueError(f"coordinator plan omitted requested deliverables: {', '.join(missing_types)}")

    # Auto-wire missing dependencies so test/doc/frontend missions always receive prior code AST context
    non_test_py_ids = [
        m["id"] for m in normalized
        if m["target_file"].endswith(".py") and not m["target_file"].startswith("tests/")
    ]
    web_html_ids = [m["id"] for m in normalized if m["target_file"].endswith(".html")]
    test_ids = [m["id"] for m in normalized if m["target_file"].startswith("tests/")]

    # Resolve dependencies & verify acyclic DAG
    graph: dict[str, list[str]] = {}
    for m in normalized:
        deps: list[str] = []
        for raw_d in m.pop("raw_deps"):
            mapped = id_remap.get(str(raw_d), _safe_mission_id(str(raw_d), 0))
            if mapped in id_set and mapped != m["id"] and mapped not in deps:
                deps.append(mapped)
        tf = m["target_file"]
        if tf.startswith("tests/") and tf.endswith(".py"):
            for pid in non_test_py_ids:
                if pid != m["id"] and pid not in deps:
                    deps.append(pid)
        elif tf.endswith(".js"):
            for hid in web_html_ids:
                if hid != m["id"] and hid not in deps:
                    deps.append(hid)
        elif tf.lower().endswith("readme.md") or tf.endswith(".ps1"):
            for tid in (test_ids or non_test_py_ids):
                if tid != m["id"] and tid not in deps:
                    deps.append(tid)
        m["dependencies"] = deps
        graph[m["id"]] = deps

    try:
        topo_order = list(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise ValueError(f"dependency cycle in coordinator plan: {exc}") from exc

    by_id = {m["id"]: m for m in normalized}
    contracts: list[dict[str, Any]] = []
    meta_by_id: dict[str, dict[str, Any]] = {}
    ws_str = str(project_root.resolve())

    for mid in topo_order:
        m = by_id[mid]
        contract = {
            "id": m["id"],
            "owner": "project-file",
            "project": project_slug,
            "specialist": m["specialist"],
            "priority": m["priority"],
            "dependencies": m["dependencies"],
            "objective": m["objective"],
            "workspace_root": ws_str,
            "allowed_paths": allowed_paths,
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

    return {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "project": project_slug,
        "workspace_root": ws_str,
        "summary": str(raw_plan.get("summary") or "")[:400],
        "startup_command": str(raw_plan.get("startup_command") or "")[:300],
        "server_entry": str(raw_plan.get("server_entry") or "").replace("\\", "/").strip() or None,
        "test_command": str(raw_plan.get("test_command") or "python -B -m unittest discover -s tests -v")[:300],
        "execution_order": topo_order,
        "contracts": contracts,
        "approvals": seal(contracts),
        "mission_meta": meta_by_id,
    }


def verify_delivered_file(
    project_root: Path,
    target_rel: str,
    *,
    required_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Independent, objective, deterministic verifier for ANY delivered project file.

    Never relies on generator self-evaluation. Runs static security gate, syntax/AST/node/PS1
    checks, Python import checks, and REAL subprocess `unittest` execution for test files.
    """
    try:
        target = local_deterministic_tools.safe_subpath(project_root, target_rel)
    except ValueError as exc:
        return {"ok": False, "security_ok": False, "error": f"scope violation: {exc}", "checks_passed": []}

    if not target.is_file():
        return {"ok": False, "security_ok": True, "error": f"missing target file {target_rel}", "checks_passed": []}

    text = target.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return {"ok": False, "security_ok": True, "error": f"empty file {target_rel}", "checks_passed": []}

    checks: list[str] = ["exists", "scope_confined"]
    if not local_deterministic_tools.detect_secret_leak(text)["safe"]:
        return {"ok": False, "security_ok": False, "error": "security: secret token pattern detected", "checks_passed": checks}
    checks.append("no_secret_leak")

    ext = target.suffix.lower()
    env = provider_router.scrubbed_env()
    env["PYTHONPATH"] = str(project_root.resolve())
    env["PYTHONUTF8"] = "1"

    if ext == ".py":
        sec = local_deterministic_tools.deterministic_security_gate(
            text, kind="python", allowed_root=project_root, target_rel_path=target_rel
        )
        if not sec["ok"]:
            return {"ok": False, "security_ok": sec["security_ok"], "error": "; ".join(sec["issues"]), "checks_passed": checks}
        checks.extend(["ast_syntax", "deterministic_security_gate"])

        # Ensure parent package __init__.py exists for any Python subpackage inside the project
        if target.parent != project_root.resolve():
            init_py = target.parent / "__init__.py"
            if not init_py.exists():
                init_py.write_text("", encoding="utf-8")

        # Check required symbols via AST or text
        tree = ast.parse(text)
        defined = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        missing_syms = [s for s in (required_symbols or []) if s not in defined and s not in text]
        if missing_syms:
            return {
                "ok": False,
                "security_ok": True,
                "error": f"missing required symbols in {target_rel}: {', '.join(missing_syms)}",
                "checks_passed": checks,
            }
        if required_symbols:
            checks.append("required_symbols")

        is_test = target.name.startswith("test_") or "tests/" in target_rel.replace("\\", "/")
        if is_test:
            proc = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", str(target), "-v"],
                cwd=str(project_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            if proc.returncode != 0:
                return {
                    "ok": False,
                    "security_ok": True,
                    "error": f"unittest failed (rc={proc.returncode}): {combined[-260:]}",
                    "checks_passed": checks,
                }
            if "Ran 0 tests" in combined or "Ran " not in combined:
                return {
                    "ok": False,
                    "security_ok": True,
                    "error": "unittest executed 0 tests; must include real assertions",
                    "checks_passed": checks,
                }
            checks.append("unittest_passed")
        else:
            # Verify clean import in isolated subprocess (zero side effects, catches missing imports/runtime errors)
            mod_rel = target_rel.replace("\\", "/")[:-3].replace("/", ".")
            proc = subprocess.run(
                [sys.executable, "-B", "-c", f"import importlib; importlib.import_module({mod_rel!r})"],
                cwd=str(project_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if proc.returncode != 0:
                err_txt = ((proc.stderr or "") or (proc.stdout or "")).strip()
                return {
                    "ok": False,
                    "security_ok": True,
                    "error": f"import {mod_rel} failed: {err_txt[-260:]}",
                    "checks_passed": checks,
                }
            checks.append("isolated_import_ok")

    elif ext == ".html":
        low = text.lower()
        if "<script>" in low or "javascript:" in low or "onerror=" in low or "onclick=" in low:
            return {"ok": False, "security_ok": False, "error": "security: inline <script>, javascript: URI, or inline event handler forbidden", "checks_passed": checks}
        if "<html" not in low or "<body" not in low:
            return {"ok": False, "security_ok": True, "error": "HTML missing <html> or <body> structure", "checks_passed": checks}
        missing_syms = [s for s in (required_symbols or []) if s not in text]
        if missing_syms:
            return {"ok": False, "security_ok": True, "error": f"HTML missing required IDs/tokens: {', '.join(missing_syms)}", "checks_passed": checks}
        checks.extend(["html_structure", "csp_safe_static"])

    elif ext == ".css":
        no_comments = re.sub(r"/\*[\s\S]*?\*/", "", text)
        o_cnt, c_cnt = no_comments.count("{"), no_comments.count("}")
        if o_cnt == 0 or o_cnt != c_cnt:
            return {"ok": False, "security_ok": True, "error": f"Unbalanced braces: {{={o_cnt} }}={c_cnt}", "checks_passed": checks}
        if len(text) < 250:
            return {"ok": False, "security_ok": True, "error": "CSS too short (< 250 chars)", "checks_passed": checks}
        checks.extend(["css_balanced_braces", "css_size_ok"])

    elif ext == ".js":
        for bad in ("eval(", "new Function(", "document.write("):
            if bad in text:
                return {"ok": False, "security_ok": False, "error": f"security: forbidden JS construct {bad}", "checks_passed": checks}
        if ".innerHTML" in text:
            return {"ok": False, "security_ok": False, "error": "security: use textContent/createElement instead of .innerHTML", "checks_passed": checks}
        proc = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True, timeout=10, check=False)
        if proc.returncode != 0:
            return {"ok": False, "security_ok": True, "error": f"node --check failed: {(proc.stderr or proc.stdout).strip()[:260]}", "checks_passed": checks}
        missing_syms = [s for s in (required_symbols or []) if s not in text]
        if missing_syms:
            return {"ok": False, "security_ok": True, "error": f"JS missing required tokens: {', '.join(missing_syms)}", "checks_passed": checks}
        checks.extend(["node_check_ok", "js_security_static"])

    elif ext == ".ps1":
        if "0.0.0.0" in text or "Invoke-Expression" in text or "iex " in text.lower():
            return {"ok": False, "security_ok": False, "error": "security: forbidden PowerShell construct (0.0.0.0 / Invoke-Expression)", "checks_passed": checks}
        ps_check = (
            "$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
            f"'{str(target)}', [ref]$null, [ref]$e) | Out-Null; "
            "if ($e -and $e.Count -gt 0) { Write-Error ($e[0].Message); exit 1 }"
        )
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps_check], capture_output=True, text=True, timeout=15, check=False)
        if proc.returncode != 0:
            return {"ok": False, "security_ok": True, "error": f"PowerShell syntax error: {(proc.stderr or proc.stdout).strip()[:240]}", "checks_passed": checks}
        checks.append("ps1_syntax_ok")

    elif ext == ".md":
        if len(text.strip()) < 180:
            return {"ok": False, "security_ok": True, "error": "README.md too short (< 180 chars)", "checks_passed": checks}
        checks.append("doc_non_empty")

    elif ext == ".json":
        try:
            json.loads(text)
        except ValueError as exc:
            return {"ok": False, "security_ok": True, "error": f"Invalid JSON: {exc}", "checks_passed": checks}
        checks.append("valid_json")

    return {
        "ok": True,
        "security_ok": True,
        "error": None,
        "checks_passed": checks,
        "file_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


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
    hybrid: bool = False,
    confidential: bool = False,
    explicit_specialist: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask `tel99-coordination` to decompose the user's goal into a bounded multi-file DAG plan."""
    coord = specialist_dispatch.resolve_specialist("coordination")
    sys_p = (
        f"{coord.full_prompt()}\n"
        "You are designing a complete, working, stdlib-only local software project for TEL99 agents.\n"
        "Output ONLY a valid JSON object (no markdown prose outside JSON) with exact keys:\n"
        '{"summary": str, "startup_command": str, "server_entry": str_or_empty, "test_command": str, "missions": [\n'
        '  {"id": "kebab-id", "specialist": "tel99-dev|tel99-mobile|tel99-verifier|tel99-documentation|tel99-security|tel99-analyst", '
        '"target_file": "relative/path.ext", "dependencies": ["prior-id"], "estimated_lines": 60, '
        '"required_symbols": ["exact_func_or_id"], "objective": "Exact concise contract (interfaces, routes, validation, <=450 chars)"}\n'
        "]}\n"
        "Rules:\n"
        "- Decompose into 5 to 8 small, self-contained files (each <= 80 lines so local 7-9B models write clean code).\n"
        "- Python 3.12 stdlib only (sqlite3/json/http.server/unittest); loopback 127.0.0.1 only (NEVER 0.0.0.0).\n"
        "- Web UI if requested: separate `web/index.html` (NO inline <script>, NO onclick/onerror), `web/styles.css`, `web/app.js` (NO innerHTML, use textContent/createElement).\n"
        "- MUST include an automated `tests/test_*.py` unittest file testing core logic & validation, a `README.md`, and a Windows `start.ps1` startup script.\n"
        "- Every mission objective MUST state the EXACT function names, signatures, JSON keys, HTTP routes, and HTML element IDs so dependent files match 100%.\n"
    )
    existing_files = [
        str(p.relative_to(project_root)).replace("\\", "/")
        for p in sorted(project_root.rglob("*"))
        if p.is_file() and not any(part in {"state", "memory", "artifacts", "__pycache__"} for part in p.relative_to(project_root).parts)
    ][:30]
    usr_p = (
        f"Project slug: {project_slug}\n"
        f"Workspace directory: {project_root}\n"
        f"Existing files: {existing_files}\n"
        f"User goal:\n{goal_text}\n"
    )

    last_err = ""
    for att in range(1, 4):
        prompt_now = usr_p if att == 1 else f"{usr_p}\nPrevious JSON plan error: {last_err}\nFix the JSON structure and return ONLY valid JSON."
        t0 = time.monotonic()
        raw, prov, mdl, cc, _meta = _call_model(
            system=sys_p,
            prompt=prompt_now,
            hybrid=hybrid,
            confidential=confidential,
            attempt=att,
            role="coordination",
            response_format="json",
            estimated_lines=95,
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
            )
            trace = {
                "agent": coord.name,
                "provider": prov,
                "model": mdl,
                "cloud_calls": cc,
                "attempts": att,
                "duration_seconds": dur,
            }
            return plan, trace
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {str(exc)[:220]}"
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


def _run_post_build_verification(project_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Run real independent test suite + optional loopback server probe after Runtime completes."""
    env = provider_router.scrubbed_env()
    env["PYTHONPATH"] = str(project_root.resolve())
    env["PYTHONUTF8"] = "1"
    report: dict[str, Any] = {"tests_ok": False, "server_probe": None}

    tests_dir = project_root / "tests"
    if tests_dir.is_dir():
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        report["tests_rc"] = proc.returncode
        report["tests_output"] = out[-1200:]
        report["tests_ok"] = proc.returncode == 0 and "Ran 0 tests" not in out and "Ran " in out
    else:
        report["tests_output"] = "no tests/ directory found"

    # Optional live loopback HTTP probe if server_entry exists
    srv_rel = plan.get("server_entry")
    if srv_rel and (project_root / srv_rel).is_file():
        probe_code = (
            "import importlib.util, json, threading, time\n"
            "from http.client import HTTPConnection\n"
            "from pathlib import Path\n"
            f"p = Path({str(project_root / srv_rel)!r})\n"
            "spec = importlib.util.spec_from_file_location('srv_probe', str(p))\n"
            "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
            "fn = getattr(mod, 'make_server', None) or getattr(mod, 'create_server', None)\n"
            "if not callable(fn): print(json.dumps({'probed': False, 'reason': 'no make_server/create_server'})); raise SystemExit(0)\n"
            "try:\n"
            f"    srv = fn(Path({str(project_root)!r}), host='127.0.0.1', port=0)\n"
            "except TypeError:\n"
            "    srv = fn(host='127.0.0.1', port=0)\n"
            "port = srv.server_port\n"
            "t = threading.Thread(target=srv.serve_forever, daemon=True); t.start(); time.sleep(0.15)\n"
            "try:\n"
            "    c = HTTPConnection('127.0.0.1', port, timeout=5); c.request('GET', '/'); r = c.getresponse(); body = r.read(); c.close()\n"
            "    print(json.dumps({'probed': True, 'http_status': r.status, 'bytes': len(body)}))\n"
            "finally:\n"
            "    srv.shutdown(); srv.server_close()\n"
        )
        p2 = subprocess.run(
            [sys.executable, "-B", "-c", probe_code],
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        try:
            report["server_probe"] = json.loads((p2.stdout or "").strip().splitlines()[-1])
        except Exception:
            report["server_probe"] = {"probed": False, "rc": p2.returncode, "stderr": (p2.stderr or "")[-240:]}
    return report


def run_autonomous_project(
    *,
    goal_text: str,
    project_dir: Path,
    hybrid: bool = False,
    confidential: bool = False,
    explicit_specialist: str | None = None,
    plan_override: dict[str, Any] | None = None,
    custom_executor=None,
) -> dict[str, Any]:
    """End-to-end autonomous project delivery via existing TEL99 Runtime, CAS, Memory, and Verifiers."""
    started = time.monotonic()
    inj = local_deterministic_tools.detect_prompt_injection(goal_text)
    if not inj["safe"]:
        return {"ok": False, "status": "BLOCKED", "reason": "prompt_injection_detected", "matches": inj["matches"]}

    kit = ensure_isolated_project_kit(project_dir)
    slug = kit.profile["project"]
    camp_dir = kit.state / f"campaign-{slug}"
    plan_path = kit.artifacts / "project_plan.json"
    delivery_path = kit.artifacts / "delivery_report.json"

    # Resume existing sealed plan if present (NEVER resets accepted work!)
    if plan_override is not None:
        plan = validate_and_normalize_plan(
            plan_override, project_root=kit.root, project_slug=slug, explicit_specialist=explicit_specialist
        )
        coord_trace = {"agent": "tel99-coordination", "provider": "provided_plan", "model": "override", "cloud_calls": 0}
        local_deterministic_tools.write_json_atomic_locked(plan_path, plan)
    elif plan_path.is_file():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        coord_trace = plan.get("coordinator_trace") or {"agent": "tel99-coordination", "resumed": True}
    else:
        plan, coord_trace = generate_plan_with_coordinator(
            goal_text=goal_text,
            project_root=kit.root,
            project_slug=slug,
            hybrid=hybrid,
            confidential=confidential,
            explicit_specialist=explicit_specialist,
        )
        plan["goal"] = goal_text
        plan["coordinator_trace"] = coord_trace
        local_deterministic_tools.write_json_atomic_locked(plan_path, plan)

    contracts = plan["contracts"]
    approvals = plan["approvals"]
    meta_by_id = plan["mission_meta"]
    mem_store = MemoryStore(kit.memory)
    traj_rec = metacognition.TrajectoryRecorder(kit.artifacts)
    flib = metacognition.FailureLibrary(kit.artifacts, memory_root=kit.memory)

    prior_delivery: dict[str, Any] = {}
    if delivery_path.is_file():
        try:
            prior_delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prior_delivery = {}

    missions_report: dict[str, Any] = dict(prior_delivery.get("missions") or {})
    agents_mobilized: set[str] = set(prior_delivery.get("agents_mobilized") or ["tel99-coordination", "tel99-security", "tel99-verifier"])
    total_cloud_calls = int(coord_trace.get("cloud_calls") or 0)

    def _default_executor(m: dict) -> dict:
        nonlocal total_cloud_calls
        mid = m["id"]
        target_rel = m["target_file"]
        target_path = local_deterministic_tools.safe_subpath(kit.root, target_rel)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        spec_name = m["specialist"]
        agents_mobilized.add(spec_name)
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

        attempts_log: list[dict] = []
        prior_hashes: list[str] = []
        last_code = ""
        prev_code = ""
        last_ver: dict[str, Any] = {"ok": False, "error": "not run", "checks_passed": []}
        max_att = int(m.get("max_attempts") or 4)
        m_t0 = time.monotonic()

        for att in range(1, max_att + 1):
            # Honor operator pause/stop cleanly between attempts
            while (camp_dir / "pause.request").exists() and not (camp_dir / "stop.request").exists():
                time.sleep(1.5)
            if (camp_dir / "stop.request").exists():
                raise autonomy_runtime.Blocked("stopped by operator request")

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
            if att == 1:
                usr_p = (
                    f"Target file: {target_rel}\n"
                    f"Required symbols/tokens: {req_syms}\n"
                    f"Specification:\n{m['objective']}\n\n"
                    + (f"Project dependencies (MATCH EXACT SIGNATURES/ROUTES/IDS):\n{dep_ctx}\n\n" if dep_ctx else "")
                    + f"{ctx['context_text']}"
                )
            else:
                diff = smart_repair.compute_bounded_diff(prev_code, last_code) if prev_code else ""
                usr_p = (
                    f"Target file: {target_rel}\n"
                    f"Required symbols/tokens: {req_syms}\n"
                    f"Specification:\n{m['objective']}\n\n"
                    + (f"Project dependencies:\n{dep_ctx}\n\n" if dep_ctx else "")
                    + smart_repair.build_smart_repair_prompt(
                        previous_code=last_code,
                        exact_error=str(last_ver.get("error") or "verification failed"),
                        passed_checks=last_ver.get("checks_passed", []),
                        failed_checks=[str(last_ver.get("error") or "verify")[:90]],
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
            try:
                raw, prov, mdl, cc, meta = _call_model(
                    system=sys_p,
                    prompt=usr_p,
                    hybrid=hybrid,
                    confidential=confidential,
                    attempt=att,
                    role=role,
                    estimated_lines=80 if ext in (".html", ".css", ".js", ".py") else 45,
                    allow_continue=ext in (".html", ".css", ".js", ".py"),
                )
                total_cloud_calls += cc
                code = ollama_native.extract_code_block(raw)
                if ext == ".py":
                    code = local_deterministic_tools.strip_trailing_example_blocks(code)
                fp = smart_repair.code_fingerprint(code)
                repeated = smart_repair.detect_repeated_attempt(code, prior_hashes)
                prior_hashes.append(fp)
                target_path.write_text(code, encoding="utf-8")
                ver = verify_delivered_file(kit.root, target_rel, required_symbols=req_syms)
                if repeated and not ver["ok"]:
                    ver["error"] = f"REPEATED_ATTEMPT: {ver.get('error')}"
            except (ProviderError, Exception) as exc:
                prov, mdl, cc, meta = "error", LOCAL_MODEL, 0, {}
                code, fp, repeated = "", "", False
                ver = {"ok": False, "security_ok": True, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "checks_passed": []}

            attempts_log.append({
                "attempt": att,
                "provider": prov,
                "model": mdl,
                "cloud_calls": cc,
                "seconds": round(time.monotonic() - t0, 2),
                "code_sha256": fp,
                "repeated": repeated,
                "ok": bool(ver.get("ok")),
                "error": ver.get("error"),
                "checks_passed": ver.get("checks_passed", []),
            })
            prev_code = last_code
            last_code = code
            last_ver = ver
            print(json.dumps({"project": slug, "mission": mid, "file": target_rel, "role": spec_name, "att": att, "model": mdl, "ok": ver.get("ok"), "err": ver.get("error")}), flush=True)
            if ver.get("ok"):
                break

        repaired = bool(last_ver.get("ok") and len(attempts_log) > 1)
        m_dur = round(time.monotonic() - m_t0, 2)
        last_mdl = attempts_log[-1]["model"] if attempts_log else LOCAL_MODEL

        # Record trajectory, failure library & verified memory lesson
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
            elif "timed out" in err_low or "unavailable" in err_low or "busy" in err_low:
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
                    preventive_measure="Use AST dependency context + deterministic verifier feedback",
                    model=last_mdl,
                    role=spec_name,
                )
            except (OSError, ValueError):
                pass
        if last_ver.get("ok"):
            eid = f"{'fix' if repaired else 'proc'}-{mid}"
            if mem_store.get(slug, eid) is None:
                mem_store.record(
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
                    ),
                    actor="autonomous-project-runner",
                )

        artifact_text = target_path.read_text(encoding="utf-8", errors="replace") if target_path.is_file() else ""
        file_sha = hashlib.sha256(artifact_text.encode("utf-8")).hexdigest()
        missions_report[mid] = {
            "id": mid,
            "target_file": target_rel,
            "specialist": spec_name,
            "model_used": last_mdl,
            "attempts": len(attempts_log),
            "repaired": repaired,
            "status": "ACCEPTED" if last_ver.get("ok") else "REJECTED",
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
        ver = verify_delivered_file(kit.root, target_rel, required_symbols=req_syms)
        target_path = local_deterministic_tools.safe_subpath(kit.root, target_rel)
        art_sha = (
            hashlib.sha256(target_path.read_text(encoding="utf-8", errors="replace").encode("utf-8")).hexdigest()
            if target_path.is_file()
            else result.get("sha256")
        )
        ok = bool(ver.get("ok"))
        passed_names = list(ver.get("checks_passed") or [])
        checks = [{"name": name, "ok": True} for name in passed_names] if (ok and passed_names) else [{"name": "independent_verify", "ok": ok}]
        return {
            "verifier": "tel99-independent-project-verifier",
            "ok": ok,
            "security_ok": bool(ver.get("security_ok", True)),
            "project": m["project"],
            "target_file": target_rel,
            "artifact_sha256": art_sha,
            "error": ver.get("error"),
            "checks": checks,
            "checks_passed": passed_names,
        }

    rt = Runtime(
        camp_dir,
        executor=custom_executor or _default_executor,
        verifier=_independent_verifier,
        shared_memory_root=kit.memory,
        auto_recover_local_crash=True,
    )
    rt.run_queue(contracts, approvals)

    statuses = {c["id"]: rt.state(c).get("status") for c in contracts}
    accepted = sum(1 for s in statuses.values() if s == "ACCEPTED")
    post_ver = _run_post_build_verification(kit.root, plan)

    all_accepted = accepted == len(contracts) and len(contracts) > 0
    tests_ok = bool(post_ver.get("tests_ok")) or not any(c["target_file"].startswith("tests/") for c in contracts)
    overall_ok = all_accepted and tests_ok
    final_status = "DELIVERED" if overall_ok else ("PARTIAL" if accepted > 0 else "BLOCKED")

    delivery = {
        "schema_version": 1,
        "status": final_status,
        "ok": overall_ok,
        "project": slug,
        "workspace_root": str(kit.root),
        "goal": goal_text,
        "finished_at": _now_iso(),
        "duration_seconds": round(time.monotonic() - started, 2),
        "coordinator_trace": coord_trace,
        "agents_mobilized": sorted(agents_mobilized),
        "missions_accepted": accepted,
        "missions_total": len(contracts),
        "runtime_statuses": statuses,
        "cloud_calls": total_cloud_calls,
        "cost_usd": 0.0,
        "startup_command": plan.get("startup_command"),
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


def get_project_progress(project_dir: Path) -> dict[str, Any]:
    """Read durable progress, deliverables, and operator controls for an autonomous project."""
    root = project_dir.resolve()
    plan_p = root / "artifacts" / "project_plan.json"
    deliv_p = root / "artifacts" / "delivery_report.json"
    kit_p = root / "project.json"
    out: dict[str, Any] = {
        "workspace_root": str(root),
        "initialized": kit_p.is_file(),
        "plan_exists": plan_p.is_file(),
        "delivery_exists": deliv_p.is_file(),
    }
    if kit_p.is_file():
        prof = json.loads(kit_p.read_text(encoding="utf-8"))
        slug = prof["project"]
        camp = root / "state" / f"campaign-{slug}"
        out["project"] = slug
        out["paused"] = (camp / "pause.request").exists()
        out["stopped"] = (camp / "stop.request").exists()
    if deliv_p.is_file():
        d = json.loads(deliv_p.read_text(encoding="utf-8"))
        out.update({
            "status": d.get("status"),
            "ok": d.get("ok"),
            "missions_accepted": d.get("missions_accepted"),
            "missions_total": d.get("missions_total"),
            "runtime_statuses": d.get("runtime_statuses"),
            "agents_mobilized": d.get("agents_mobilized"),
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
    return {"ok": True, "project": kit.profile["project"], "action": action, "paused": pause_f.exists(), "stopped": stop_f.exists()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", type=Path, required=True, help="Isolated local target project directory")
    ap.add_argument("--task", type=str, default="", help="Project goal/specification for the autonomous team")
    ap.add_argument("--role", type=str, default=None, help="Optional explicit specialist role")
    ap.add_argument("--hybrid", action="store_true", help="Allow free Groq mentor escalation ($0.00, non-confidential only)")
    ap.add_argument("--confidential", action="store_true", help="Force 100% local Ollama execution")
    ap.add_argument("--progress", action="store_true", help="Print durable progress and deliverables")
    ap.add_argument("--control", choices=["pause", "resume", "stop"], default=None, help="Pause/resume/stop project run")
    args = ap.parse_args(argv)

    if args.progress:
        print(json.dumps(get_project_progress(args.project), indent=2, ensure_ascii=False))
        return 0
    if args.control:
        print(json.dumps(control_project(args.project, args.control), indent=2, ensure_ascii=False))
        return 0
    if not args.task.strip():
        print(json.dumps({"ok": False, "error": "--task is required to run an autonomous project"}, indent=2))
        return 2

    delivery = run_autonomous_project(
        goal_text=args.task.strip(),
        project_dir=args.project,
        hybrid=args.hybrid,
        confidential=args.confidential,
        explicit_specialist=args.role,
    )
    print(json.dumps({
        "status": delivery.get("status"),
        "ok": delivery.get("ok"),
        "project": delivery.get("project"),
        "workspace_root": delivery.get("workspace_root"),
        "missions_accepted": delivery.get("missions_accepted"),
        "missions_total": delivery.get("missions_total"),
        "agents_mobilized": delivery.get("agents_mobilized"),
        "startup_command": delivery.get("startup_command"),
        "post_build_verification": delivery.get("post_build_verification"),
        "deliverables": delivery.get("deliverables"),
    }, indent=2, ensure_ascii=False))
    return 0 if delivery.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
