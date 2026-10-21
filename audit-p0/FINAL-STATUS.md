# P0 provenance audit — status and handoff

Date: 2026-10-20
Reviewed base commit: 1b4fdd1ef1a9fa3300a506932837d189785deadc
Branch: wip/p0-provenance
Scope: provenance/coherence only; no trading-rule changes.

## Evidence from Cline's read-only audit

On a detached worktree at the reviewed base commit, Cline reported:
- `python -m unittest discover -s tests -v`: 49 tests OK, 3 skipped
- `python -m unittest discover -s collector -p "test_*.py" -v`: 14 tests OK
- `node tests/test_dashboard.js`: OK
- `node tests/test_realtime.js`: OK

These are results reported by Cline for the base commit; they are not a fresh CI run of this document's commit.

## Confirmed findings

1. The snapshot fingerprint is a deterministic SHA-256 over the normalized stable source data and derived cross-check summary. It is not a hash of every byte of the complete snapshot file. Volatile metadata such as `generated_at`, collection timing, and `request_log` is intentionally excluded.
2. The analysis layer checks collection provenance and recalculates/validates the fingerprint; Cline did not reproduce the alleged analysis-layer bypass.
3. The provenance commit does not include dashboard files. Cline observed local changes to `index.html`, `realtime.js`, and `test_dashboard.js` in the user's checkout; those changes must be preserved and reviewed separately.
4. The current workflow gate was reported to run only on `main`, not on pull requests. The workflow file could not be independently retrieved in this pass, so this finding still needs direct workflow-file verification before editing.
5. The historical `audit-p0/README-AUDIT.txt` and `audit-p0/HEAD.txt` refer to an older checkout and a local Windows path. Keep them as historical evidence; do not treat them as proof of the current branch head.
6. Cline reported stale snapshot, missing snapshot, missing timeframe, and incomplete-source checks in the analysis layer. This does not by itself prove the workflow gate independently validates all those conditions.
7. The inline Python gate in workflow YAML is harder to test in isolation. Prefer a small dedicated script with unit tests when the workflow file is available and the change can be verified.
8. Secret scanning was heuristic only; `NO_SECRET_PATTERNS_FOUND` is not a guarantee that no secret exists. No live GitHub Actions side effects were proven by the local test report.

## Required safety boundaries

- Keep work on `wip/p0-provenance`; do not merge to `main` or deploy without separate authorization.
- Do not place exchange orders or use private exchange credentials.
- Do not change trading thresholds, strategy rules, or the Phase 3 verdict.
- Preserve the user's uncommitted dashboard edits; do not clean or overwrite their working tree.
- Missing, stale, mismatched, or incoherent data must remain fail-closed (`ATTENDRE`).

## Remaining blockers before calling P0 fully finished

- Verify the actual workflow file and its trigger configuration; if confirmed, add pull-request validation without enabling deployment or trading side effects.
- Run the tests and workflow checks on the resulting commit in a clean checkout.
- Regenerate a fresh audit bundle from that exact commit, with no local absolute path and with the exact commit ID and actual command outputs.
- Review the local dashboard changes separately before incorporating any of them.

This status note records the current evidence; it does not claim that all blockers have been fixed.
