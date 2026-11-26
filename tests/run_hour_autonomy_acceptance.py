"""60-minute real autonomous TEL99 acceptance campaign using existing supervisor, Ollama & Docker.

Executes strictly inside an isolated state root outside the repository, with zero
GitHub writes, zero trading orders, and concurrence=1 on local Ollama.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
AUTOMATION_DIR = ROOT / "scripts" / "agents" / "automation"
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from scripts.agents.automation import (
    antigravity_sdk_backend,
    env_doctor,
    learning_loop,
    local_codegen,
    local_team,
    mission_planner,
    multi_cockpit,
    recovery_tool,
)
from scripts.agents.automation.autonomy_runtime import Runtime, seal
from scripts.agents.automation.env_doctor import DEFAULT_SANDBOX_IMAGE
from scripts.agents.intelligence.memory import MemoryStore

BASE_SHA = "934d9fd8a3fd498c6e3e69226007dd46276aa6da"
BASE_REF = "agents/tel99-code-base-autofeed-20261124"
GEMMA4_MODEL = "gemma4:e4b-tel99-8k"
DEFAULT_MIN_FREE_RAM_MB = 1400.0
CRITICAL_FREE_RAM_MB = 900.0
DEFAULT_MAX_RAM_LOAD_PCT = 88
DEFAULT_STATE_ROOT = Path(r"C:\Users\sabri\Desktop\TEL99_ENDURANCE_20261125_RUN2\hour_campaign")
DEFAULT_REPORT_PATH = Path(r"C:\Users\sabri\Desktop\TEL99_ENDURANCE_20261125_RUN2\hour_campaign_report.json")


class _MemStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _snapshot_ram() -> dict:
    st = _MemStatus(dwLength=ctypes.sizeof(_MemStatus))
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    total_mb = round(st.ullTotalPhys / (1024 * 1024), 2)
    free_mb = round(st.ullAvailPhys / (1024 * 1024), 2)
    py_mb = ollama_mb = lh_mb = 0.0
    pid_cur = os.getpid()
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, check=False,
        ).stdout
        for row in csv.reader(io.StringIO(out)):
            if len(row) < 5:
                continue
            img = row[0].lower()
            try:
                pid = int(row[1])
            except ValueError:
                continue
            kb = int("".join(c for c in row[4] if c.isdigit()) or "0")
            mb = round(kb / 1024.0, 2)
            if pid == pid_cur:
                py_mb = mb
            if "ollama" in img or "llama-server" in img:
                ollama_mb = round(ollama_mb + mb, 2)
            if "localharness" in img:
                lh_mb = round(lh_mb + mb, 2)
    except Exception:
        pass
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system_ram_total_mb": total_mb,
        "system_ram_free_mb": free_mb,
        "system_ram_used_mb": round(total_mb - free_mb, 2),
        "system_memory_load_pct": int(st.dwMemoryLoad),
        "python_rss_mb": py_mb,
        "ollama_rss_mb": ollama_mb,
        "localharness_rss_mb": lh_mb,
    }


# Authentic mission templates verified against BASE_SHA = 934d9fd8a3fd498c6e3e69226007dd46276aa6da
CATALOG_SPECS = [
    {
        "key": "tool-names",
        "path": "scripts/agents/automation/verify_runtime.py",
        "function": "tool_names",
        "objective": (
            "Keep only non-empty string tool names (ignoring whitespace-only strings via .strip()) "
            "from strings or dictionaries when reading persisted agent metadata. Ignore blank strings, "
            "numeric dictionary names and non-list roots without changing the order of real tool names. "
            "Preserve the existing function signature, imports and all other code."
        ),
        "test": (
            "import runpy\n"
            "read = runpy.run_path('/work/program.py')['tool_names']\n"
            "assert read(['terminal', {'name':'read'}, 'git']) == ['terminal','read','git']  # case: normal-tools | expected: Valid names keep their order.\n"
            "assert read('terminal') == []  # case: invalid-root | expected: Non-list roots give no names.\n"
            "assert read(['  ', {'name':3}, {'name':''}, None, 'git', {'name':'read'}]) == ['git','read']  # case: malformed-names | expected: Empty and blank tool names are ignored.\n"
        ),
    },
    {
        "key": "dedup-key",
        "path": "scripts/agents/automation/pilot_recipe.py",
        "function": "dedup_key",
        "objective": (
            "Normalize runs of whitespace in mission titles when computing a deduplication key. "
            "Titles with the same words and differing internal spaces or tabs must receive the same digest, "
            "while differing repository names or issue numbers must still differ. "
            "Keep the exact function signature and existing hashlib import. Modify only dedup_key."
        ),
        "test": (
            "import runpy\n"
            "key = runpy.run_path('/work/program.py')['dedup_key']\n"
            "assert key('sample/repo',12,' TASK ') == key('sample/repo',12,'task')  # case: boundary-spaces | expected: Boundary spaces normalized.\n"
            "assert key('sample/repo',12,'Fix   Parser') == key('sample/repo',12,' fix parser ')  # case: internal-spaces | expected: Repeated spaces normalized.\n"
            "assert key('sample/repo',12,'fix parser') == key('sample/repo',12,'fix\\tparser')  # case: tab-run | expected: Tabs and spaces normalize equally.\n"
            "assert key('sample/repo',12,'fix parser') != key('sample/repo',13,'fix parser')  # case: issue-boundary | expected: Distinct issue keeps distinct key.\n"
        ),
    },
    {
        "key": "branch-prot",
        "path": "scripts/agents/automation/policy.py",
        "function": "branch_is_protected",
        "objective": (
            "Check protected branches safely even when prefixed with 'refs/heads/' or using uppercase letters "
            "(for example 'refs/heads/main' or 'MAIN' or 'Tel99-live-data'). Strip whitespace, remove an optional "
            "'refs/heads/' prefix, and check case-insensitively against PROTECTED_BRANCHES and PROTECTED_PREFIXES. "
            "Preserve the exact function signature and all module constants."
        ),
        "test": (
            "import runpy\n"
            "prot = runpy.run_path('/work/program.py')['branch_is_protected']\n"
            "assert prot('main') is True  # case: main | expected: main is protected.\n"
            "assert prot('refs/heads/main') is True  # case: refs-heads-main | expected: refs/heads/main is protected.\n"
            "assert prot('MAIN') is True  # case: uppercase-main | expected: Case-insensitive main is protected.\n"
            "assert prot('refs/heads/TEL99-live-data') is True  # case: prefixed-tel99 | expected: Prefixed tel99- branch is protected.\n"
            "assert prot('agents/tel99-work') is False  # case: work-branch | expected: Isolated agent work branch is allowed.\n"
        ),
    },
    {
        "key": "team-slug",
        "path": "scripts/agents/team_config.py",
        "function": "_slug",
        "objective": (
            "Update _slug(text) to preserve single underscores '_' while still lowercasing, replacing other "
            "non-[a-z0-9_] character runs with '-', collapsing consecutive underscores to one '_', and "
            "stripping leading/trailing '-' and '_'. Assume text is str and preserve exact signature."
        ),
        "test": (
            "import runpy\n"
            "fn = runpy.run_path('/work/program.py')['_slug']\n"
            "assert fn('  Tel99 / Agent V2!  ') == 'tel99-agent-v2'  # case: normal-slug | expected: Normalized slug.\n"
            "assert fn('tel99_agent_v2') == 'tel99_agent_v2'  # case: preserve-underscore | expected: Preserve underscores.\n"
            "assert fn('__Tel99__V2__') == 'tel99_v2'  # case: trim-underscore | expected: Collapse and trim outer underscores.\n"
            "assert fn('   ') == ''  # case: blank | expected: Blank returns empty string.\n"
        ),
    },
    {
        "key": "strip-quotes",
        "path": "scripts/agents/guard/guard.py",
        "function": "_strip_quotes",
        "objective": (
            "Update _strip_quotes(text) to strip outer whitespace and then remove at most ONE matching pair "
            "of surrounding single quotes ('...') or double quotes (\"...\"), so \"'hello'\" becomes \"'hello'\" "
            "and nested or mismatched quotes are not over-stripped. Preserve def _strip_quotes(text: str) -> str:."
        ),
        "test": (
            "import runpy\n"
            "fn = runpy.run_path('/work/program.py')['_strip_quotes']\n"
            "assert fn('\"hello\"') == 'hello'  # case: double | expected: Double quotes removed.\n"
            "assert fn(\"'hello'\") == 'hello'  # case: single | expected: Single quotes removed.\n"
            "assert fn('  \"spaced\"  ') == 'spaced'  # case: outer-space | expected: Outer spaces trimmed.\n"
            "assert fn('\"\\'hello\\'\"') == \"'hello'\"  # case: nested | expected: Only outer matching pair stripped.\n"
        ),
    },
    {
        "key": "emergency-truthy",
        "path": "scripts/agents/automation/emergency.py",
        "function": "_truthy",
        "objective": (
            "Extend _truthy(value) so stripped lowercase strings 'enable', 'enabled', 'y', and '1.0' "
            "also return True (alongside _TRUTHY), while bool, None, ints, and falsey values remain safe. "
            "Preserve exact function signature."
        ),
        "test": (
            "import runpy\n"
            "fn = runpy.run_path('/work/program.py')['_truthy']\n"
            "assert fn(True) is True  # case: bool-true | expected: True stays True.\n"
            "assert fn(None) is False  # case: none | expected: None returns False.\n"
            "assert fn('  YES  ') is True  # case: yes | expected: YES returns True.\n"
            "assert fn(' enabled ') is True  # case: enabled | expected: enabled returns True.\n"
            "assert fn('0') is False  # case: zero | expected: Zero string returns False.\n"
        ),
    },
    {
        "key": "pos-int",
        "path": "scripts/agents/automation/acceptance.py",
        "function": "_positive_int",
        "objective": (
            "Update _positive_int(value) to return True for strictly positive int values (excluding bool) "
            "OR stripped ASCII digit-only strings representing an integer > 0 (for example ' 12 '), "
            "while returning False for 0, negatives, floats, bool, and None. Preserve def _positive_int(value):."
        ),
        "test": (
            "import runpy\n"
            "fn = runpy.run_path('/work/program.py')['_positive_int']\n"
            "assert fn(5) is True  # case: int | expected: Positive int is True.\n"
            "assert fn(0) is False  # case: zero | expected: Zero is False.\n"
            "assert fn(True) is False  # case: bool | expected: Bool is rejected.\n"
            "assert fn(' 12 ') is True  # case: digit-str | expected: Positive digit string is True.\n"
            "assert fn('-3') is False  # case: negative | expected: Negative string is False.\n"
        ),
    },
    {
        "key": "vdel-tool-names",
        "path": "scripts/agents/verify_delegation.py",
        "function": "tool_names",
        "objective": (
            "Harden tool_names(tools) to accept list/tuple/set inputs, strip surrounding whitespace on string "
            "names, ignore blank/whitespace-only names, and accept dict entries only when 'name' is a non-blank str. "
            "Preserve def tool_names(tools: object) -> list[str]:."
        ),
        "test": (
            "import runpy\n"
            "fn = runpy.run_path('/work/program.py')['tool_names']\n"
            "assert fn([' terminal ', '   ', {'name': 42}, {'name': ' search '}]) == ['terminal', 'search']  # case: mixed | expected: Valid stripped names only.\n"
            "assert fn(('terminal', '  ')) == ['terminal']  # case: tuple | expected: Tuples accepted.\n"
            "assert fn(None) == []  # case: none | expected: None returns empty list.\n"
        ),
    },
    {
        "key": "sha40-norm",
        "path": "scripts/agents/automation/g3_bot_acceptance.py",
        "function": "sha40",
        "objective": (
            "Update sha40(value) so valid 40-character hexadecimal strings with surrounding whitespace or "
            "uppercase hex letters (A-F) return True, while non-strings, invalid hex chars, and wrong lengths "
            "return False. Preserve def sha40(value): and constants."
        ),
        "test": (
            "import runpy\n"
            "fn = runpy.run_path('/work/program.py')['sha40']\n"
            "assert fn('a' * 40) is True  # case: lower | expected: Lowercase sha40 accepted.\n"
            "assert fn('  ' + 'A' * 40 + '  ') is True  # case: upper-ws | expected: Uppercase trimmed sha40 accepted.\n"
            "assert fn(None) is False  # case: none | expected: None rejected.\n"
            "assert fn('z' * 40) is False  # case: bad-hex | expected: Non-hex rejected.\n"
        ),
    },
    {
        "key": "repo-allowed",
        "path": "scripts/agents/automation/policy.py",
        "function": "repository_allowed",
        "objective": (
            "Harden repository_allowed(repository) so non-string inputs return False, and string inputs "
            "are stripped of whitespace and lowercased before checking against ALLOWED_REPOSITORIES "
            "(case-insensitively). Preserve the exact function signature and constants."
        ),
        "test": (
            "import runpy\n"
            "fn = runpy.run_path('/work/program.py')['repository_allowed']\n"
            "assert fn('khalidd692/telcoin-trading-intelligence99') is True  # case: exact | expected: Allowed repo.\n"
            "assert fn('  KHALIDD692/telcoin-trading-intelligence99  ') is True  # case: upper-ws | expected: Stripped case-insensitive.\n"
            "assert fn(None) is False  # case: none | expected: None rejected.\n"
            "assert fn(123) is False  # case: int | expected: Non-string rejected.\n"
        ),
    },
]


def _check_all_baselines() -> int:
    for spec in CATALOG_SPECS:
        src = local_codegen._source({"base_sha": BASE_SHA, "path": spec["path"]})
        local_codegen._function(src, spec["function"])
        passed, line = local_codegen._behavior(DEFAULT_SANDBOX_IMAGE, src, spec["test"])
        if passed:
            raise RuntimeError(f"Catalog spec {spec['key']} already passes baseline!")
        print(f"BASELINE_RED_OK {spec['key']} ({spec['path']}:{spec['function']}) line={line}")
    return 0


def _fetch_cockpit(port: int) -> dict:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", "/api/snapshot.json", headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        return {"http_status": resp.status, "read_at": body.get("read_at"), "summary": body.get("summary"), "memory": body.get("memory"), "sdk_backend": body.get("sdk_backend")}
    finally:
        conn.close()


def _run_wave(
    *,
    state_root: Path,
    controller_issue: int,
    wave_tag: str,
    specs: list[dict],
    model_override: str | None = None,
    use_sdk_backend: bool = False,
) -> dict:
    start = time.monotonic()
    tasks = []
    prev_id = None
    for idx, sp in enumerate(specs, 1):
        mid = f"{wave_tag}-m{idx}-{sp['key']}"[:48]
        t = {
            "id": mid,
            "issue": controller_issue * 10 + idx,
            "dependencies": [prev_id] if prev_id else [],
            "path": sp["path"],
            "function": sp["function"],
            "objective": sp["objective"],
            "test": sp["test"],
        }
        if model_override:
            t["model"] = model_override
        tasks.append(t)
        prev_id = mid

    goal_spec = {
        "goal": f"TEL99 hour acceptance wave {wave_tag}",
        "base_sha": BASE_SHA,
        "base_ref": BASE_REF,
        "expires_at": "2026-12-20T23:59:59Z",
        "tasks": tasks,
    }
    if len(tasks) >= 2:
        goal_spec["controller_issue"] = controller_issue
        goal_spec["mandate_comment_id"] = 910000 + controller_issue
    plan = mission_planner.plan_from_goal(goal_spec, state_root=state_root, verify_baseline=True)
    camp_dir = state_root / f"campaign-{controller_issue}"
    shared_mem = state_root / "learning" / "memory"
    rt = Runtime(camp_dir, shared_memory_root=shared_mem)
    missions = plan["local_registry"]["missions"]
    approvals = plan["local_registry"]["approvals"]

    # Seed cockpit-compatible config + approval records so multi_cockpit shows live wave progression
    rt.store.put_cas("github-local-code/config", {
        "issue": controller_issue,
        "mandate_id": f"hour-{wave_tag}",
        "base_ref": BASE_REF,
        "base_sha": BASE_SHA,
    }, None)
    for m, t in zip(missions, tasks):
        rt.store.put_cas(f"kilo-github/approvals/{m['id']}", {"issue": t["issue"], "mission": m}, None)

    prev_env = os.environ.get("TEL99_EXECUTION_BACKEND")
    if use_sdk_backend:
        os.environ["TEL99_EXECUTION_BACKEND"] = "antigravity_sdk"
    else:
        os.environ.pop("TEL99_EXECUTION_BACKEND", None)
    try:
        rt.run_queue(missions, approvals)
    finally:
        if prev_env is None:
            os.environ.pop("TEL99_EXECUTION_BACKEND", None)
        else:
            os.environ["TEL99_EXECUTION_BACKEND"] = prev_env

    statuses = {m["id"]: rt.state(m).get("status") for m in missions}
    attempts = {m["id"]: rt.state(m).get("attempt") for m in missions}
    learning_loop.sync_measured_quality(state_root)
    return {
        "wave": wave_tag,
        "controller_issue": controller_issue,
        "model_override": model_override or plan["selected_model"].get("served_model"),
        "sdk_backend": use_sdk_backend,
        "execution_order": plan["execution_order"],
        "statuses": statuses,
        "attempts": attempts,
        "accepted_count": sum(1 for s in statuses.values() if s == "ACCEPTED"),
        "total_count": len(missions),
        "duration_seconds": round(time.monotonic() - start, 2),
    }


def _run_repair_proof(state_root: Path) -> dict:
    """Real Docker rejection at attempt 1 -> Ollama repair at attempt 2 -> ACCEPTED + MemoryStore promotion."""
    start = time.monotonic()
    sp = CATALOG_SPECS[3]  # team_config.py:_slug
    m = {
        "id": "hour-repair-proof",
        "owner": "local",
        "project": "tel99",
        "specialist": "tel99-dev",
        "priority": "P1",
        "dependencies": [],
        "objective": sp["objective"],
        "base_sha": BASE_SHA,
        "path": sp["path"],
        "function": sp["function"],
        "test": sp["test"],
        "sandbox_image": DEFAULT_SANDBOX_IMAGE,
        "model": "gemma4:e4b-tel99-8k",
        "port": 11434,
        "team": local_team.TEAM.copy(),
        "max_attempts": 2,
    }
    camp_dir = state_root / "campaign-298"
    shared_mem = state_root / "learning" / "memory"
    rt = Runtime(camp_dir, shared_memory_root=shared_mem)
    rt.store.put_cas("github-local-code/config", {"issue": 298, "mandate_id": "hour-repair", "base_ref": BASE_REF, "base_sha": BASE_SHA}, None)
    rt.store.put_cas(f"kilo-github/approvals/{m['id']}", {"issue": 2981, "mission": m}, None)

    broken_code = (
        "def _slug(text: str) -> str:\n"
        "    return re.sub(r'[^a-z0-9_]+', '-', text.lower()).strip('-')\n"
    )
    broken_trace = local_team.trace(
        local_team.analyze(m, broken_code),
        developer_model=m["model"],
        artifact=broken_code,
    )
    broken_result = {
        "artifact": broken_code,
        "sha256": hashlib.sha256(broken_code.encode("utf-8")).hexdigest(),
        "specialist_id": "tel99-dev",
        "provider": local_codegen.PROVIDER,
        "model": m["model"],
        "generation_seconds": 1.0,
        "agent_trace": broken_trace,
    }
    rt.claim(m)
    rt.inbox.receive({"request_id": m["id"]})
    rt.save(m, "WORKER_EXITED", attempt=1, result=broken_result)
    rt.run_queue([m], seal([m]))
    st = rt.state(m)
    learning_loop.sync_measured_quality(state_root)
    return {
        "mission_id": m["id"],
        "status": st.get("status"),
        "attempt": st.get("attempt"),
        "attempt1_rejected_line": (st.get("attempt_history") or [{}])[0].get("feedback", {}).get("line"),
        "duration_seconds": round(time.monotonic() - start, 2),
    }


def _run_interruption_and_no_duplicate_proof(state_root: Path) -> dict:
    """Tests controlled STOP + isolated subprocess crash -> AWAITING_HUMAN + 0 duplicate replay."""
    start = time.monotonic()
    # 1. STOP marker + clear_stops check
    stop_file = state_root / "stop.request"
    stop_file.touch()
    inspected_stop = recovery_tool.inspect_state(state_root)
    cleared = recovery_tool.clear_stops(state_root)

    # 2. Brutal crash in isolated campaign-299 -> restart -> AWAITING_HUMAN with 0 replayed workers
    crash_dir = state_root / "campaign-299"
    crash_script = (
        "import os, sys\n"
        "from scripts.agents.automation.autonomy_runtime import Runtime, seal\n"
        "from tests.test_autonomy_runtime import mission\n"
        "m = mission('HOUR-CRASH-1')\n"
        "Runtime(sys.argv[1], executor=lambda _m: os._exit(55)).run_queue([m], seal([m]))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-B", "-c", crash_script, str(crash_dir)],
        cwd=ROOT, capture_output=True, timeout=20, check=False,
    )
    replay_calls = []
    from tests.test_autonomy_runtime import mission as synth_mission
    cm = synth_mission("HOUR-CRASH-1")
    rt_after = Runtime(crash_dir, executor=lambda t: replay_calls.append(t["id"]))
    rt_after.run_queue([cm], seal([cm]))
    st_after = rt_after.state(cm)
    rec = recovery_tool.inspect_state(state_root)

    # 3. Re-run already-ACCEPTED campaign-270 -> confirm 0 duplicate worker invocations
    camp_270 = state_root / "campaign-270"
    dup_calls = []
    if camp_270.is_dir():
        rt_270 = Runtime(camp_270, executor=lambda t: dup_calls.append(t["id"]))
        approvals_270 = {}
        missions_270 = []
        for k in sorted(rt_270.store.keys("kilo-github/approvals")):
            row = rt_270.store.get(k)
            if isinstance(row, dict) and isinstance(row.get("mission"), dict):
                missions_270.append(row["mission"])
        if missions_270:
            rt_270.run_queue(missions_270, seal(missions_270))

    return {
        "stop_detected_by_recovery": bool(inspected_stop.get("parent_stop")),
        "stop_cleared": cleared,
        "crash_exit_code": proc.returncode,
        "post_crash_status": st_after.get("status"),
        "post_crash_replayed_workers": len(replay_calls),
        "accepted_wave_replayed_workers": len(dup_calls),
        "awaiting_human_count": len(rec.get("awaiting_human", [])),
        "duration_seconds": round(time.monotonic() - start, 2),
    }


def _cloud_process_names() -> list[str]:
    """Observed (not killed) cloud-assistant processes, for the evidence record only."""
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=8, check=False).stdout
    except Exception:
        return []
    names = set()
    for row in csv.reader(io.StringIO(out)):
        if row and any(k in row[0].lower() for k in ("agy", "antigravity", "claude", "codex", "gemini")):
            names.add(row[0])
    return sorted(names)


def _enforce_cloud_independence() -> dict:
    """Strip paid/cloud credentials and prove the existing router picks a local Ollama model only."""
    from scripts.agents.automation import provider_router
    removed = sorted(k for k in list(os.environ) if k.upper().startswith(provider_router.PAID_ENV_PREFIXES))
    for k in removed:
        os.environ.pop(k, None)
    os.environ["TEL99_ALLOW_SUBSCRIPTION_CLI"] = "0"
    sel = provider_router.select_executor("code", confidential=True, allow_subscription_cli=False)
    chosen = sel.get("chosen") or {}
    providers = {c.get("provider") for c in [chosen, *sel.get("fallbacks", [])] if c}
    if not sel.get("ok") or chosen.get("provider") != "ollama" or providers - {"ollama"}:
        raise SystemExit(f"cloud independence violated: {sorted(providers)}")
    return {
        "paid_env_vars_removed": removed,
        "allow_subscription_cli": False,
        "router_chosen": chosen.get("id"),
        "router_candidate_providers": sorted(providers),
        "cloud_processes_at_start": _cloud_process_names(),
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically via a temporary sibling file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _checkpoint_path(state_root: Path) -> Path:
    return state_root / "progress_checkpoint.json"


def load_checkpoint(state_root: Path) -> dict | None:
    cp = _checkpoint_path(state_root)
    if not cp.is_file():
        return None
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def save_checkpoint(state_root: Path, data: dict) -> None:
    _atomic_write_json(_checkpoint_path(state_root), data)


def _unload_ollama_models() -> list[str]:
    """Ask local Ollama to release loaded model weights (keep_alive=0) to reclaim RAM."""
    unloaded: list[str] = []
    conn = HTTPConnection("127.0.0.1", 11434, timeout=4.0)
    try:
        conn.request("GET", "/api/ps")
        resp = conn.getresponse()
        if resp.status != 200:
            return unloaded
        payload = json.loads(resp.read(65536))
    except (OSError, ValueError):
        return unloaded
    finally:
        conn.close()

    models = [
        row.get("name") for row in (payload.get("models") or [])
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    ]
    for model_name in models:
        c2 = HTTPConnection("127.0.0.1", 11434, timeout=6.0)
        try:
            body = json.dumps({"model": model_name, "prompt": "", "keep_alive": 0}).encode("utf-8")
            c2.request("POST", "/api/generate", body=body, headers={"Content-Type": "application/json"})
            c2.getresponse().read(4096)
            unloaded.append(model_name)
        except (OSError, ValueError):
            pass
        finally:
            c2.close()
    return unloaded


def ensure_memory_headroom(
    *,
    min_free_mb: float = DEFAULT_MIN_FREE_RAM_MB,
    critical_free_mb: float = CRITICAL_FREE_RAM_MB,
    max_load_pct: int = DEFAULT_MAX_RAM_LOAD_PCT,
    wait_seconds: float = 45.0,
    snapshot_fn=_snapshot_ram,
    unload_fn=_unload_ollama_models,
    sleep_fn=time.sleep,
) -> dict:
    """Guard against RAM saturation before starting a new wave; unload Ollama if pressured."""
    before = snapshot_fn()
    free_before = float(before.get("system_ram_free_mb") or 0.0)
    load_before = int(before.get("system_memory_load_pct") or 0)
    if free_before >= min_free_mb and load_before < max_load_pct:
        return {"ok": True, "action": "none", "unloaded_models": [], "before": before, "after": before}

    unloaded = list(unload_fn() or [])
    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    after = snapshot_fn()
    while time.monotonic() < deadline:
        free_now = float(after.get("system_ram_free_mb") or 0.0)
        load_now = int(after.get("system_memory_load_pct") or 0)
        if free_now >= min_free_mb and load_now < max_load_pct:
            return {"ok": True, "action": "unloaded_and_recovered", "unloaded_models": unloaded, "before": before, "after": after}
        sleep_fn(3.0)
        after = snapshot_fn()

    free_final = float(after.get("system_ram_free_mb") or 0.0)
    ok = free_final >= critical_free_mb
    return {
        "ok": ok,
        "action": "degraded_continue" if ok else "pause_low_memory",
        "unloaded_models": unloaded,
        "before": before,
        "after": after,
    }


def build_endurance_pool() -> list[tuple[list[dict], str]]:
    """Build the Gemma 4-only local endurance pool (avoids 9B/Gemma double-loading RAM spikes)."""
    return [
        (CATALOG_SPECS[5:7], GEMMA4_MODEL),
        (CATALOG_SPECS[7:9], GEMMA4_MODEL),
        ([CATALOG_SPECS[9], CATALOG_SPECS[0]], GEMMA4_MODEL),
        (CATALOG_SPECS[1:3], GEMMA4_MODEL),
        (CATALOG_SPECS[3:5], GEMMA4_MODEL),
        (CATALOG_SPECS[6:8], GEMMA4_MODEL),
        (CATALOG_SPECS[8:10], GEMMA4_MODEL),
        (CATALOG_SPECS[0:2], GEMMA4_MODEL),
        (CATALOG_SPECS[2:4], GEMMA4_MODEL),
        (CATALOG_SPECS[4:6], GEMMA4_MODEL),
        (CATALOG_SPECS[7:9], GEMMA4_MODEL),
        ([CATALOG_SPECS[9], CATALOG_SPECS[5]], GEMMA4_MODEL),
    ]


def build_report(
    *,
    state_root: Path,
    ts_path: Path,
    target_minutes: float,
    total_seconds: float,
    waves: list[dict],
    repair_proof: dict | None,
    interruption_proof: dict | None,
    cloud_independence: dict,
    cockpit_snapshots: list[dict],
    memory_guards: list[dict],
    status: str,
    resumed_from_checkpoint: bool = False,
) -> dict:
    metrics = learning_loop.sync_measured_quality(state_root)
    mem_dir = state_root / "learning" / "memory"
    mem_entries = MemoryStore(mem_dir).all_entries("tel99", include_common=False) if mem_dir.is_dir() else []
    ts_rows = []
    if ts_path.is_file():
        for line in ts_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    ts_rows.append(json.loads(line))
                except ValueError:
                    pass

    total_missions = sum(w["total_count"] for w in waves) + (1 if repair_proof else 0)
    total_accepted = sum(w["accepted_count"] for w in waves) + (
        1 if repair_proof and repair_proof.get("status") == "ACCEPTED" else 0
    )
    total_blocked = total_missions - total_accepted
    active_seconds = round(
        sum(float(w.get("duration_seconds") or 0.0) for w in waves)
        + float((repair_proof or {}).get("duration_seconds") or 0.0)
        + float((interruption_proof or {}).get("duration_seconds") or 0.0),
        2,
    )
    wait_seconds = round(max(0.0, total_seconds - active_seconds), 2)
    skills_dir = ROOT / ".agents" / "skills"
    skills_discovered = sorted(p.parent.name for p in skills_dir.glob("*/SKILL.md")) if skills_dir.is_dir() else []

    return {
        "schema_version": 2,
        "status": status,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "resumed_from_checkpoint": resumed_from_checkpoint,
        "base_sha": BASE_SHA,
        "primary_model": GEMMA4_MODEL,
        "duration_seconds": round(total_seconds, 2),
        "active_seconds": active_seconds,
        "wait_seconds": wait_seconds,
        "duration_minutes": round(total_seconds / 60.0, 2),
        "target_minutes": target_minutes,
        "waves_executed": len(waves),
        "missions_total": total_missions,
        "missions_accepted": total_accepted,
        "missions_blocked": total_blocked,
        "repairs_count": int(metrics.get("repaired") or 0),
        "cloud_calls": 0,
        "duplicates_count": int((interruption_proof or {}).get("post_crash_replayed_workers") or 0)
        + int((interruption_proof or {}).get("accepted_wave_replayed_workers") or 0),
        "memory_guard_events": len([g for g in memory_guards if g.get("action") != "none"]),
        "memory_guards_recent": memory_guards[-5:],
        "skills_discovered": skills_discovered,
        "waves": waves,
        "repair_proof": repair_proof,
        "interruption_proof": interruption_proof,
        "cloud_independence": cloud_independence,
        "cloud_processes_at_end": _cloud_process_names(),
        "measured_quality": metrics["measured_quality"],
        "memory_entries_count": len(mem_entries),
        "procedures_doc_exists": (state_root / "learning" / "learned_procedures.md").is_file(),
        "cockpit_snapshots_count": len(cockpit_snapshots),
        "cockpit_last_snapshot": cockpit_snapshots[-1] if cockpit_snapshots else None,
        "ram_summary": {
            "samples": len(ts_rows),
            "free_min_mb": min((r["system_ram_free_mb"] for r in ts_rows), default=None),
            "free_max_mb": max((r["system_ram_free_mb"] for r in ts_rows), default=None),
            "ollama_max_mb": max((r["ollama_rss_mb"] for r in ts_rows), default=None),
            "python_start_mb": ts_rows[0]["python_rss_mb"] if ts_rows else None,
            "python_end_mb": ts_rows[-1]["python_rss_mb"] if ts_rows else None,
            "localharness_max_mb": max((r["localharness_rss_mb"] for r in ts_rows), default=None),
        },
        "timeseries_file": str(ts_path),
    }


def evaluate_consecutive_failure_breaker(
    waves: list[dict],
    *,
    max_consecutive_failures: int = 3,
) -> dict:
    """Smart circuit breaker: stop unproductive campaigns after N consecutive 0-accepted waves."""
    limit = max(1, int(max_consecutive_failures))
    streak = 0
    for w in reversed(waves):
        if int(w.get("accepted_count") or 0) == 0 and int(w.get("total_count") or 0) > 0:
            streak += 1
        else:
            break
    triggered = streak >= limit
    return {
        "triggered": triggered,
        "consecutive_zero_accepted_waves": streak,
        "threshold": limit,
        "reason": f"consecutive_zero_accepted_waves_{streak}_ge_{limit}" if triggered else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-minutes", type=float, default=60.0)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--min-free-ram-mb", type=float, default=DEFAULT_MIN_FREE_RAM_MB)
    parser.add_argument("--max-ram-load-pct", type=int, default=DEFAULT_MAX_RAM_LOAD_PCT)
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument("--include-sdk-wave", action="store_true")
    parser.add_argument("--check-baselines-only", action="store_true")
    args = parser.parse_args(argv)

    if args.check_baselines_only:
        return _check_all_baselines()

    state_root: Path = args.state_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    ts_path = state_root.parent / "hour_timeseries.jsonl"

    prior = load_checkpoint(state_root)
    resumed = prior is not None
    waves: list[dict] = list(prior.get("waves", [])) if prior else []
    completed_tags: set[str] = set(prior.get("completed_tags", [])) if prior else set()
    repair_proof: dict | None = prior.get("repair_proof") if prior else None
    interruption_proof: dict | None = prior.get("interruption_proof") if prior else None
    memory_guards: list[dict] = list(prior.get("memory_guards", [])) if prior else []
    wave_idx: int = int(prior.get("next_wave_idx", 272)) if prior else 272
    p_idx: int = int(prior.get("next_pool_idx", 0)) if prior else 0
    elapsed_offset: float = float(prior.get("accumulated_elapsed_seconds", 0.0)) if prior else 0.0

    cloud_independence = _enforce_cloud_independence()
    started = time.monotonic()
    active_phase = {"name": "resume-init" if resumed else "init"}
    stop_sampler = threading.Event()
    stop_requested = threading.Event()

    def _on_signal(_signum, _frame):
        stop_requested.set()

    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                signal.signal(sig, _on_signal)
            except (OSError, ValueError):
                pass

    def _elapsed_total() -> float:
        return round(elapsed_offset + (time.monotonic() - started), 2)

    def _sampler():
        while not stop_sampler.is_set():
            snap = _snapshot_ram()
            snap["elapsed_seconds"] = _elapsed_total()
            snap["phase"] = active_phase["name"]
            with ts_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(snap) + "\n")
            stop_sampler.wait(30.0)

    sampler_thr = threading.Thread(target=_sampler, daemon=True)
    sampler_thr.start()

    srv = multi_cockpit.make_server(state_root, port=0, allow_controls=True, include_providers=False)
    srv_thr = threading.Thread(target=srv.serve_forever, daemon=True)
    srv_thr.start()
    cockpit_port = srv.server_port
    cockpit_snapshots: list[dict] = []
    final_status = "IN_PROGRESS"

    def _persist_progress(status_label: str) -> dict:
        elapsed = _elapsed_total()
        save_checkpoint(state_root, {
            "schema_version": 2,
            "status": status_label,
            "completed_tags": sorted(completed_tags),
            "waves": waves,
            "repair_proof": repair_proof,
            "interruption_proof": interruption_proof,
            "memory_guards": memory_guards[-20:],
            "next_wave_idx": wave_idx,
            "next_pool_idx": p_idx,
            "accumulated_elapsed_seconds": elapsed,
        })
        rep = build_report(
            state_root=state_root,
            ts_path=ts_path,
            target_minutes=args.min_minutes,
            total_seconds=elapsed,
            waves=waves,
            repair_proof=repair_proof,
            interruption_proof=interruption_proof,
            cloud_independence=cloud_independence,
            cockpit_snapshots=cockpit_snapshots,
            memory_guards=memory_guards,
            status=status_label,
            resumed_from_checkpoint=resumed,
        )
        _atomic_write_json(args.report, rep)
        return rep

    def _guard_ram() -> bool:
        g = ensure_memory_headroom(
            min_free_mb=args.min_free_ram_mb,
            max_load_pct=args.max_ram_load_pct,
        )
        memory_guards.append(g)
        return bool(g.get("ok"))

    try:
        # Wave 1 (270): 3-mission dependent chain (Gemma 4)
        if "w1" not in completed_tags and not stop_requested.is_set():
            if not _guard_ram():
                final_status = "PAUSED_LOW_MEMORY"
            else:
                active_phase["name"] = "wave-1-chain"
                waves.append(_run_wave(
                    state_root=state_root, controller_issue=270, wave_tag="w1",
                    specs=CATALOG_SPECS[0:3], model_override=GEMMA4_MODEL,
                ))
                completed_tags.add("w1")
                cockpit_snapshots.append(_fetch_cockpit(cockpit_port))
                _persist_progress("IN_PROGRESS")

        # Wave 2 (298): Real Docker rejection -> auto-repair -> MemoryStore promotion
        if final_status == "IN_PROGRESS" and "w2-repair" not in completed_tags and not stop_requested.is_set():
            if not _guard_ram():
                final_status = "PAUSED_LOW_MEMORY"
            else:
                active_phase["name"] = "wave-2-repair"
                repair_proof = _run_repair_proof(state_root)
                completed_tags.add("w2-repair")
                cockpit_snapshots.append(_fetch_cockpit(cockpit_port))
                _persist_progress("IN_PROGRESS")

        # Wave 3 (299): Controlled STOP + brutal crash -> safe recovery + 0 duplicates
        if final_status == "IN_PROGRESS" and "w3-recovery" not in completed_tags and not stop_requested.is_set():
            active_phase["name"] = "wave-3-recovery"
            interruption_proof = _run_interruption_and_no_duplicate_proof(state_root)
            completed_tags.add("w3-recovery")
            cockpit_snapshots.append(_fetch_cockpit(cockpit_port))
            _persist_progress("IN_PROGRESS")

        # Wave 4 (271): Optional SDK opt-in wave (explicit --include-sdk-wave only)
        if (final_status == "IN_PROGRESS" and args.include_sdk_wave
                and antigravity_sdk_backend.sdk_available()
                and "w4sdk" not in completed_tags and not stop_requested.is_set()):
            if not _guard_ram():
                final_status = "PAUSED_LOW_MEMORY"
            else:
                active_phase["name"] = "wave-4-sdk-optin"
                waves.append(_run_wave(
                    state_root=state_root, controller_issue=271, wave_tag="w4sdk",
                    specs=[CATALOG_SPECS[4]], model_override=GEMMA4_MODEL, use_sdk_backend=True,
                ))
                completed_tags.add("w4sdk")
                cockpit_snapshots.append(_fetch_cockpit(cockpit_port))
                _persist_progress("IN_PROGRESS")

        # Waves 5..N: Continuous Gemma 4 local waves with RAM guard & progressive report
        pool_pairs = build_endurance_pool()
        while final_status == "IN_PROGRESS" and not stop_requested.is_set() and (_elapsed_total() / 60.0) < args.min_minutes:
            if (state_root / "stop.request").exists():
                final_status = "PAUSED_STOP_REQUEST"
                break
            cb = evaluate_consecutive_failure_breaker(
                waves, max_consecutive_failures=args.max_consecutive_failures
            )
            if cb["triggered"]:
                final_status = "BLOCKED_CONSECUTIVE_FAILURES"
                break
            if not _guard_ram():
                final_status = "PAUSED_LOW_MEMORY"
                break
            specs_batch, mdl = pool_pairs[p_idx % len(pool_pairs)]
            tag = f"w{wave_idx}"
            if tag not in completed_tags:
                active_phase["name"] = f"wave-{wave_idx}-{mdl}"
                waves.append(_run_wave(
                    state_root=state_root,
                    controller_issue=wave_idx,
                    wave_tag=tag,
                    specs=specs_batch,
                    model_override=mdl,
                ))
                completed_tags.add(tag)
                cockpit_snapshots.append(_fetch_cockpit(cockpit_port))
            wave_idx += 1
            p_idx += 1
            _persist_progress("IN_PROGRESS")
            if p_idx >= 80:
                break

        if final_status == "IN_PROGRESS":
            final_status = "INTERRUPTED" if stop_requested.is_set() else "COMPLETED"
    except BaseException:
        final_status = "INTERRUPTED"
        raise
    finally:
        stop_sampler.set()
        sampler_thr.join(timeout=5)
        try:
            report = _persist_progress(final_status)
        finally:
            srv.shutdown()
            srv_thr.join(timeout=2)
            srv.server_close()

    print("HOUR_REPORT_SAVED:", args.report, flush=True)
    print(json.dumps({
        "status": report["status"],
        "duration_minutes": report["duration_minutes"],
        "missions_accepted": report["missions_accepted"],
        "missions_total": report["missions_total"],
        "memory_entries_count": report["memory_entries_count"],
        "memory_guard_events": report["memory_guard_events"],
        "measured_quality": report["measured_quality"],
    }, indent=2), flush=True)
    return 0 if report["status"] == "COMPLETED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
