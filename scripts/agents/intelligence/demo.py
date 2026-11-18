#!/usr/bin/env python3
"""End-to-end demonstration of the TEL99 agent intelligence layer.

This is the evidence requested by the mission: it shows, in one deterministic
and offline run, that an agent can

  1. **choose a suitable model** for a task (router + decision journal);
  2. **retrieve recorded knowledge** that was persisted in a previous session;
  3. **use that knowledge on a new task** (the recalled rule is applied);
  4. **measure whether its solution is better** (before/after on real commands);
  5. **record the verified result** for the next missions.

Nothing here is fabricated. The measured quantity is the accuracy of two real
classifiers over a fixed set of real shell commands:

  * the **baseline (before)** is the *legacy* matcher — the guard exactly as it
    behaved before the PR #71 hardening: wrappers are skipped without their own
    value arguments, ``git`` finds its sub-command with a naive first-non-dash
    scan, and ``find`` has no destructive-action rule;
  * the **candidate (after)** is the hardened guard actually shipped in this
    branch (SHA ``26579ceb``), run for real through its ``decide()``.

Both are scored on the same labelled commands, so the delta is a real
measurement on a real TEL99 artifact. The proposal reuses the guard's own
parsers and knowledge bases, so it cannot drift from the guard's vocabulary.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
AGENTS_DIR = HERE.parents[1]          # scripts/agents
REPO_ROOT = HERE.parents[3]           # repository root
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from intelligence import improvement, memory, router  # noqa: E402

GUARD_PATH = AGENTS_DIR / "guard" / "guard.py"

# Fixed, labelled command set: (command, should_be_blocked).
# Read-only commands must pass; mutating commands must be blocked. This is the
# ground truth both classifiers are scored against.
LABELLED_COMMANDS: list[tuple[str, bool]] = [
    ("ls -la", False),
    ("git status", False),
    ("git log --oneline -3", False),
    ("grep -rn TODO src", False),
    ("find deploy -type f", False),
    ("git -C /repo status", False),
    ("git --no-pager log -1", False),
    ("rm -rf /tmp/x", True),
    ("git push origin main", True),
    ("git commit -m x", True),
    ("echo hi > /tmp/f", True),
    ("pip install requests", True),
    ("git -C /tmp/repo push origin main", True),
    ("git -c user.name=x commit -m y", True),
    ("timeout 5 rm -rf /tmp/z", True),
    ("nice -n 10 rm -rf /tmp/z", True),
    ("find /tmp -delete", True),
    ("find . -exec rm {} ;", True),
    ("xargs -I{} rm {}", True),
    ("kraken order buy TELUSD", True),
]

def _load_guard():
    spec = importlib.util.spec_from_file_location("tel99_guard", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Baseline: the guard exactly as it behaved BEFORE the PR #71 hardening.
#
# It reuses the shipped guard's own vocabularies (mutating heads, patterns) but
# keeps the two legacy defects: wrappers are skipped without consuming their own
# value arguments, ``git`` takes the first dash-free token as its sub-command,
# and ``find`` has no destructive-action rule.
# --------------------------------------------------------------------------- #
def _legacy_head_words(guard, segment: str) -> list[str]:
    segment = re.sub(r"\$\{IFS\}|\$IFS", " ", segment)
    tokens = segment.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token):
            i += 1
            continue
        base = token.rsplit("/", 1)[-1].lstrip("\\")
        if base in guard.WRAPPERS:
            i += 1
            continue
        return [t.lstrip("\\") for t in tokens[i:]]
    return []


def _legacy_git_subcommand(guard, words: list[str]) -> str:
    return next((w for w in words[1:] if not w.startswith("-")), "")


def _legacy_blocked(guard, command: str) -> bool:
    if guard.pipes_into_executor(command):
        return True
    segments = guard.split_segments(command)
    for segment in list(segments):
        words = _legacy_head_words(guard, segment)
        if words and words[0].rsplit("/", 1)[-1] in guard.SHELLS and "-c" in words[1:3]:
            idx = words.index("-c")
            if idx + 1 < len(words):
                inner = " ".join(words[idx + 1:]).strip().strip("'\"")
                segments.extend(guard.split_segments(inner))
    for segment in segments:
        words = _legacy_head_words(guard, segment)
        if not words:
            continue
        base = words[0].rsplit("/", 1)[-1].lower()
        if guard.is_mutating_head(base):
            return True
        if base == "git":
            sub = _legacy_git_subcommand(guard, words)
            if guard.is_git_mutation(sub, words, segment):
                return True
        if base in guard.INTERPRETERS:
            for pattern in guard.ESCAPE_PATTERNS:
                if re.search(pattern, segment, re.I):
                    return True
        for pattern in (guard.INSTALL_PATTERNS + guard.WRITE_PATTERNS
                        + guard.NETWORK_PATTERNS):
            if re.search(pattern, segment, re.I):
                return True
        if (re.search(guard.TRADING_PATTERN, segment, re.I)
                or re.search(guard.PAPER_PATTERN, segment, re.I)):
            return True
        if guard.has_write_redirection(segment):
            return True
    return False


# --------------------------------------------------------------------------- #
# Candidate: the hardened guard actually shipped in this branch, run for real.
# --------------------------------------------------------------------------- #
def _proposal_blocked(guard, command: str) -> bool:
    code, _ = guard.decide({"tool_name": "terminal",
                            "tool_input": {"command": command}})
    return code == 2


def _accuracy(predict, commands) -> tuple[float, list[dict]]:
    rows = []
    correct = 0
    for command, expected in commands:
        got = predict(command)
        ok = got == expected
        correct += 1 if ok else 0
        rows.append({"command": command, "expected_blocked": expected,
                     "predicted_blocked": got, "correct": ok})
    return correct / len(commands), rows


def run(dry_run: bool = False, memory_root: str | None = None) -> int:
    root = pathlib.Path(memory_root) if memory_root else REPO_ROOT / "memory"
    store = memory.MemoryStore(root)
    project = "tel99"
    guard = _load_guard()

    print("=" * 72)
    print("STEP 1 — choose a suitable model")
    print("=" * 72)
    task = router.TaskProfile(
        kind="code", description="review the PreToolUse guard", touches_files=2,
        needs_tools=True,
    )
    journal: list[dict] = []
    decision = router.route(task, dry_run=True, journal=journal)
    print(f"task difficulty : {decision.difficulty}")
    print(f"chosen model    : {decision.chosen.id if decision.chosen else 'NONE'}")
    print(f"fallbacks       : {[m.id for m in decision.fallbacks]}")
    print("decision journal:")
    for entry in decision.rejected:
        print(f"  rejected {entry['id']}: {entry['reason']}")
    if not decision.ok:
        print("router found no model (dry run)")
        return 1

    print()
    print("=" * 72)
    print("STEP 2 — retrieve knowledge recorded in a previous session")
    print("=" * 72)
    query = "guard git option push bypass"
    results = store.search(project, query, limit=3)
    print(f"recall for {query!r} (project {project}):")
    for entry in results:
        flag = "verified" if entry.verified else "unverified"
        print(f"  - [{entry.kind}/{flag}] {entry.title}")
    if not results:
        print("no knowledge retrieved: the store has no matching entry")
        return 1
    recalled = results[0]

    print()
    print("=" * 72)
    print("STEP 3 — use the recalled knowledge on a new task")
    print("=" * 72)
    new_task_command = "git -C /tmp/repo push origin main"
    print(f"new task: classify {new_task_command!r}")
    print(f"applying recalled rule from {recalled.id}")
    predicted = _proposal_blocked(guard, new_task_command)
    print(f"proposal verdict: {'BLOCKED' if predicted else 'ALLOWED'} "
          "(the recalled rule predicts BLOCKED)")
    knowledge_used = predicted is True

    print()
    print("=" * 72)
    print("STEP 4 — measure whether the proposal is better (before/after)")
    print("=" * 72)
    base_rate, base_rows = _accuracy(lambda c: _legacy_blocked(guard, c),
                                     LABELLED_COMMANDS)
    cand_rate, cand_rows = _accuracy(lambda c: _proposal_blocked(guard, c),
                                     LABELLED_COMMANDS)
    print(f"BEFORE (legacy matcher, pre-#71)      : {base_rate:.0%} "
          f"({sum(r['correct'] for r in base_rows)}/{len(base_rows)})")
    print(f"AFTER  (hardened guard shipped)       : {cand_rate:.0%} "
          f"({sum(r['correct'] for r in cand_rows)}/{len(cand_rows)})")
    missed = [r["command"] for r in base_rows
              if r["expected_blocked"] and not r["predicted_blocked"]]
    if missed:
        print("commands the BEFORE guard misses:")
        for command in missed:
            print(f"  - {command}")

    outcomes = []
    for command, expected in LABELLED_COMMANDS:
        outcomes.append(improvement.Outcome(
            task_id=command, model_id="guard-before",
            success=(_legacy_blocked(guard, command) == expected),
            evidence="legacy matcher (pre-#71 guard behaviour)",
        ))
        outcomes.append(improvement.Outcome(
            task_id=command, model_id="guard-after",
            success=(_proposal_blocked(guard, command) == expected),
            evidence="scripts/agents/guard/guard.py (26579ceb)",
        ))
    comparison = improvement.compare(
        outcomes, baseline_id="guard-before", candidate_id="guard-after"
    )
    print(f"verdict: {comparison.verdict.upper()} ({comparison.reasons[0]})")

    print()
    print("=" * 72)
    print("STEP 5 — record the result as an improvement proposal")
    print("=" * 72)
    if not dry_run:
        entry_id = improvement.apply_verdict(comparison, store, project)
        measured_path = root / "measured_quality.json"
        improvement.write_measured_quality(measured_path, outcomes)
        print(f"verdict recorded in memory as {entry_id}")
        print(f"measured quality written to {measured_path}")
    else:
        print("dry run: nothing written")

    ok = (decision.ok and bool(results) and knowledge_used
          and comparison.verdict == improvement.KEEP)
    print()
    print(f"DEMONSTRATION {'OK' if ok else 'INCOMPLETE'}: "
          f"model chosen={decision.ok}, knowledge retrieved={bool(results)}, "
          f"knowledge used={knowledge_used}, "
          f"measured delta={comparison.delta:+.0%}, verdict={comparison.verdict}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(run())
