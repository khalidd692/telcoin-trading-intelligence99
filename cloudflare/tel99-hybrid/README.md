# TEL99 — Cloudflare + GitHub, phase 1 (NOT activated)

A **free, read-only clock**, not a cloud LLM host and not an OpenHands auto-dispatcher.

## Architecture
Cloudflare Cron (free) -> inspect open issues labelled `tel99-mission`
-> deterministic oldest-first pick -> GitHub `repository_dispatch`
-> read-only GitHub Actions audit -> downloadable artifact.

No trading, production write, automatic merge, deployment, or OpenHands usage.
This does **not** extend the OpenHands free quota and cannot itself run hours of
LLM work: a free Worker has 10 ms CPU and 128 MB, far below any model runtime.

## What it is for
A reliable scheduler that keeps running when the operator's PC is off, and a
free place to run **deterministic** checks (tests, syntax, config safety) via
GitHub Actions — which is free and unlimited for this **public** repository.

## Tested behaviour (no deploy required)
`node --test "test/*.test.mjs"` runs 9 tests with no dependencies:
disabled-by-default, no-token, oldest-first, PR exclusion, empty queue, lookup
failure, dispatch failure, KV dedup skip, KV dedup record.

## Activation prerequisites (NOT performed)
1. Merge the workflow into GitHub's **default branch** (repository_dispatch
   workflows must exist there). Keep TEL99 product branches untouched.
2. Create a **fine-grained** GitHub token scoped to this repo with only the
   permission needed to dispatch the event. Store it as the Worker secret
   `GITHUB_DISPATCH_TOKEN`. Never commit it.
3. Deploy with Wrangler on a **free** Cloudflare account (see README steps).
4. Run one manual `workflow_dispatch` audit and confirm it is green.
5. Only after explicit operator approval: set `TEL99_ENABLED=true` and add ONE
   UTC cron to `wrangler.jsonc` (e.g. `0 6 * * *` = 07:00 Paris in winter).
6. Optional dedup: create a KV namespace and bind it as `TEL99_DEDUP`.

## Free-tier facts (verified 2026-11-15)
- Cloudflare Workers Free: 100,000 requests/day, 10 ms CPU, 128 MB, 50
  subrequests/request. Cron Triggers are available on the free plan.
- GitHub Actions: **free and unlimited** for public repositories (this repo is
  public). 20-minute job timeout is set here.
- OpenHands Cloud: 20 conversations/day on the current account; credits $0.00.
  The Worker never spends OpenHands quota — only the orchestrator does.

## Limitations
- Cloudflare cannot host Python or an LLM on the free plan.
- The GitHub workflow is read-only and does not dispatch OpenHands. Extending it
  to do so requires a separate security review and explicit authorization.
- The schedule is intentionally absent. Nothing here is deployed or enabled.
