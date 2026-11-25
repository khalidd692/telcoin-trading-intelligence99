"""Smart bounded repair & concise structured reasoning for local TEL99 agents.

Addresses three measured causes of local agent failure:
1. Blind retries repeating the same patch (prevented via SHA-256 attempt memory).
2. Oversized error dumps overflowing 8k context (errors bounded to <= 300 chars).
3. Verbose prompts hurting 7-9B local models (concise role-specific reasoning steps).
"""
from __future__ import annotations

import difflib
import hashlib
import re
from typing import Sequence

MAX_ERROR_CHARS = 300
MAX_CODE_CHARS = 2600
MAX_DIFF_LINES = 36
MAX_LESSONS = 3
MAX_PRIOR_ATTEMPTS = 4


def compute_bounded_diff(before_code: str, after_code: str, *, max_lines: int = MAX_DIFF_LINES) -> str:
    """Return a bounded unified diff between two consecutive candidate attempts."""
    diff = list(difflib.unified_diff(
        (before_code or "").splitlines(),
        (after_code or "").splitlines(),
        fromfile="prev_attempt",
        tofile="last_attempt",
        lineterm="",
        n=2,
    ))
    if len(diff) > max_lines:
        diff = diff[:max_lines] + ["... [diff truncated]"]
    return "\n".join(diff)


def build_self_critique_checklist(role: str, target_file: str) -> str:
    """Concise pre-verification self-critique checklist tailored to file type."""
    ext = target_file.rsplit(".", 1)[-1].lower() if "." in target_file else ""
    checks = ["All required exports/signatures present", "Edge cases (None, empty, invalid types) handled"]
    if ext == "py":
        checks.extend(["Stdlib-only imports & valid Python syntax", "No eval/exec/shell=True/0.0.0.0"])
    elif ext in ("js", "html", "css"):
        checks.extend(["Balanced braces/tags & valid ES6/DOM IDs", "No eval/new Function/document.write/inline script"])
    return f"Self-critique ({role} on {target_file}): " + "; ".join(checks) + "."


def suggest_repair_strategy(attempts_log: Sequence[dict], current_model: str) -> dict:
    """Recommend next repair action: targeted_patch, switch_local_model, or decompose_task."""
    if not attempts_log:
        return {"strategy": "targeted_patch", "reason": "initial repair"}
    repeated_count = sum(1 for row in attempts_log if row.get("repeated"))
    trunc_count = sum(1 for row in attempts_log if row.get("done_reason") == "length")
    if trunc_count >= 2:
        return {"strategy": "decompose_task", "reason": "repeated token-length truncation; split module"}
    if repeated_count >= 1 or len(attempts_log) >= 2:
        return {
            "strategy": "switch_local_model",
            "reason": f"model {current_model} stalled or repeated across {len(attempts_log)} attempts",
            "exclude_model": current_model,
        }
    return {"strategy": "targeted_patch", "reason": "single localized error"}


def code_fingerprint(code: str) -> str:
    """Normalized SHA-256 fingerprint to detect repeated/no-op repair attempts."""
    normalized = "\n".join(line.rstrip() for line in (code or "").strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def detect_repeated_attempt(candidate_code: str, prior_hashes: Sequence[str]) -> bool:
    """Return True if candidate_code matches an already-failed normalized attempt."""
    if not candidate_code or not prior_hashes:
        return False
    return code_fingerprint(candidate_code) in set(prior_hashes)


def build_structured_reasoning_prompt(
    *,
    role: str,
    objective: str,
    constraints: Sequence[str] = (),
    examples: Sequence[str] = (),
) -> str:
    """Build a concise, high-signal system/task protocol tailored for 7-9B local models."""
    clean_constraints = [c.strip() for c in constraints if isinstance(c, str) and c.strip()][:6]
    clean_examples = [e.strip() for e in examples if isinstance(e, str) and e.strip()][:2]
    lines = [
        f"Role: {role} (TEL99 autonomous agent).",
        "Protocol (internalize silently, output ONLY the requested deliverable):",
        "1. Understand the exact objective and contract interfaces.",
        "2. Check all constraints and edge cases (None, empty, types, security).",
        "3. Plan minimal modular structure before writing.",
        "4. Self-check syntax, imports, return schema and security before finishing.",
        f"Objective: {objective.strip()}",
    ]
    if clean_constraints:
        lines.append("Constraints:\n- " + "\n- ".join(clean_constraints))
    if clean_examples:
        lines.append("Validated reference pattern:\n" + "\n---\n".join(clean_examples))
    return "\n\n".join(lines)


def _bound_text(text: str, limit: int) -> str:
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", " ", str(text or "")).strip()
    if len(clean) > limit:
        return clean[: limit - 3].rstrip() + "..."
    return clean


def diagnose_error_pattern(exact_error: str, previous_code: str = "") -> str:
    """Return a concise, generalizable root-cause repair hint for recurring Python/web error classes."""
    err = str(exact_error or "")
    low = err.lower()
    hints: list[str] = []

    if "expected bytes or bytearray, but got 'str'" in low or ("hmac" in low and "bytes" in low):
        hints.append(
            "Encode str inputs to bytes first (e.g. `k = secret.encode('utf-8') if isinstance(secret, str) else secret`) before `hmac.new`/`hashlib`."
        )
    if "unboundlocalerror" in low:
        hints.append(
            "Initialize local variables before conditional branches (never reference a variable that is only assigned inside an `if` branch)."
        )
    if (
        "true" in low or "false" in low or "assert false" in low
    ) and (
        "bool" not in (previous_code or "")
        or "isinstance(" in (previous_code or "")
        or "assert false" in low
    ):
        if "assert false" in low or ", true)" in low or ", false," in low or "(true," in low or "bool" in low:
            hints.append(
                "Python `bool` subclasses `int` (`isinstance(True, int)` is True and `False == 0` is True): ALWAYS check `if isinstance(x, bool):` FIRST before `int`/`float` or `== 0` checks."
            )
    if "syntaxerror" in low and any(tok in low for tok in ("never closed", "unterminated", "eof")):
        hints.append(
            "Output was truncated or had an unclosed delimiter: remove ALL docstrings, comments, and example blocks and keep the file concise."
        )
    if "unbalanced braces" in low:
        hints.append(
            "Output had unbalanced CSS/JS braces (likely truncated): remove ALL comments (`/* ... */`, `// ...`) and write compact rules with matching `{` and `}`."
        )
    if "baserequesthandler" in low or "raw_requestline" in low or ("magicmock" in low and "bytes" in low):
        hints.append(
            "NEVER instantiate a BaseHTTPRequestHandler directly with MagicMock(). Start a real loopback HTTPServer(('127.0.0.1', 0), Handler) in a daemon thread and call it with urllib.request / http.client.HTTPConnection('127.0.0.1', srv.server_port), or test pure data functions directly."
        )
    if "innerhtml" in low:
        hints.append(
            "NEVER use `.innerHTML` (not even `el.innerHTML = ''`). Clear containers with `el.replaceChildren()` or `while (el.firstChild) el.removeChild(el.firstChild);`, and build DOM with `document.createElement` + `textContent`."
        )
    if "repeated_attempt" in low:
        hints.append(
            "Your previous attempt produced identical code: change the actual logic causing the failed check rather than re-emitting the same implementation."
        )
    if "semver" in low or ("must start with" in low and "valueerror" in low):
        hints.append(
            "Check optional prefixes carefully (e.g. `'v?X.Y.Z'` means leading `'v'` is OPTIONAL, not mandatory)."
        )
    return " ".join(hints[:2])[:320]


def build_smart_repair_prompt(
    *,
    previous_code: str,
    exact_error: str,
    passed_checks: Sequence[str] = (),
    failed_checks: Sequence[str] = (),
    contract_constraints: Sequence[str] = (),
    prior_attempts: Sequence[dict] = (),
    memory_lessons: Sequence[str] = (),
    previous_diff: str = "",
    target_file: str = "",
    role: str = "tel99-dev",
) -> str:
    """Build a bounded, anti-repetition repair prompt combining full diagnostic signal."""
    parts = [
        "TARGETED REPAIR REQUIRED (do NOT repeat any previously tried solution):",
        f"Exact verifier error: {_bound_text(exact_error, MAX_ERROR_CHARS)}",
    ]
    root_hint = diagnose_error_pattern(exact_error, previous_code)
    if root_hint:
        parts.append(f"Root-cause diagnostic hint: {root_hint}")
    if passed_checks:
        parts.append("Checks already PASSING (preserve intact): " + ", ".join(str(c) for c in passed_checks[:12]))
    if failed_checks:
        parts.append("Checks FAILED (must fix): " + ", ".join(str(c) for c in failed_checks[:8]))
    if contract_constraints:
        parts.append("Contract constraints:\n- " + "\n- ".join(_bound_text(c, 160) for c in contract_constraints[:5]))
    if prior_attempts:
        hist_lines = []
        for row in list(prior_attempts)[-MAX_PRIOR_ATTEMPTS:]:
            num = row.get("attempt", "?")
            err = _bound_text(row.get("error") or "failed", 120)
            fp = str(row.get("code_sha256") or "")[:10]
            hist_lines.append(f"Attempt {num} [{fp}]: {err}")
        parts.append("Already-tried approaches (DO NOT REPEAT):\n- " + "\n- ".join(hist_lines))
    if previous_diff and previous_diff.strip():
        parts.append("Previous diff (what changed last time):\n" + previous_diff.strip()[:1000])
    if memory_lessons:
        parts.append(
            "Relevant verified memory lessons:\n- "
            + "\n- ".join(_bound_text(item, 220) for item in list(memory_lessons)[:MAX_LESSONS])
        )
    if previous_code and previous_code.strip():
        snippet = previous_code.strip()
        if len(snippet) > MAX_CODE_CHARS:
            snippet = snippet[:MAX_CODE_CHARS] + "\n# [truncated for 8k context]"
        parts.append("Previous code to repair:\n" + snippet)
    if target_file:
        parts.append(build_self_critique_checklist(role, target_file))
    parts.append(
        "Fix the exact failed check while keeping all passing checks green. "
        "Output ONLY the complete corrected file."
    )
    return "\n\n".join(parts)
