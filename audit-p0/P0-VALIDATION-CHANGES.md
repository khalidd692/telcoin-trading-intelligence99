# P0 provenance — workflow isolation change

Date: 2026-10-20
Branch: `wip/p0-provenance`

## Change made

This note records the workflow-only change made directly on the authorized branch.

1. `.github/workflows/monitor.yml`: removed the `pull_request` trigger. This keeps the operational monitor workflow limited to its existing `push: main`, scheduled, and manual triggers. Its collection, report generation, provenance gate, commit/push, Pages upload, and deployment steps remain conditioned on `github.ref == 'refs/heads/main'` and not a pull request.
2. Added `.github/workflows/p0-validation.yml`: read-only CI for pull requests targeting `main`, pushes to `wip/p0-provenance`, and manual dispatch. It requests only `contents: read` and runs the existing Python application tests, collector tests, dashboard freshness tests, and realtime fail-closed tests. It contains no collection, publishing, git push, or deployment steps.

## Safety and scope

- No change to trading logic, thresholds, strategy, data sources, exchange credentials, or order execution.
- No change to `main`; the changes are on `wip/p0-provenance` only.
- The separate validation workflow is designed to avoid operational side effects and use read-only repository permissions.
- The existing monitor workflow retains its operational capabilities on main; no deployment was initiated by this change.

## Verification status

- Both workflow files were fetched back from GitHub after writing, confirming the committed content.
- The GitHub Actions run lookup for commit `ba4523a3da65187d2b8d5348b91c0115a0f09167` returned no pull-request workflow runs, and the combined commit status returned an empty status list. This does **not** prove the workflow ran or passed.
- Existing local tests were previously reported by Cline on base commit `1b4fdd1ef1a9fa3300a506932837d189785deadc`: 49 tests OK (3 skipped), 14 collector tests OK, dashboard freshness OK, realtime fail-closed tests OK. These results are not a fresh run of the workflow-only commits.
- Fresh CI execution and successful results remain unverified.

## Remaining checks

1. Confirm that GitHub Actions starts `P0 provenance validation` on the next eligible push or pull request.
2. Confirm all four test steps pass on the exact new commit.
3. Inspect any workflow syntax or permission errors from the actual run.
4. Keep the P0 status provisional until fresh CI evidence is available.

Fail-closed invariant remains unchanged: missing, stale, mismatched, or incoherent data must result in `ATTENDRE`. No merge to `main`, deployment, or trade was performed.
