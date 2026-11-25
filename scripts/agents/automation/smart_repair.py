"""Smart bounded repair & concise structured reasoning for local TEL99 agents.

Addresses three measured causes of local agent failure:
1. Blind retries repeating the same patch (prevented via SHA-256 attempt memory).
2. Oversized error dumps overflowing 8k context (errors bounded to <= 300 chars).
3. Verbose prompts hurting 7-9B local models (concise role-specific reasoning steps).
"""
from __future__ import annotations

import hashlib
import re
from typing import Sequence

MAX_ERROR_CHARS = 300
MAX_CODE_CHARS = 2600
MAX_LESSONS = 3
MAX_PRIOR_ATTEMPTS = 4


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


def build_smart_repair_prompt(
    *,
    previous_code: str,
    exact_error: str,
    passed_checks: Sequence[str] = (),
    failed_checks: Sequence[str] = (),
    contract_constraints: Sequence[str] = (),
    prior_attempts: Sequence[dict] = (),
    memory_lessons: Sequence[str] = (),
) -> str:
    """Build a bounded, anti-repetition repair prompt combining full diagnostic signal."""
    parts = [
        "TARGETED REPAIR REQUIRED (do NOT repeat any previously tried solution):",
        f"Exact verifier error: {_bound_text(exact_error, MAX_ERROR_CHARS)}",
    ]
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
    parts.append(
        "Fix the exact failed check while keeping all passing checks green. "
        "Output ONLY the complete corrected file."
    )
    return "\n\n".join(parts)
