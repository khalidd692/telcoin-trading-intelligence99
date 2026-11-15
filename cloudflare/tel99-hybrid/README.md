# TEL99 — Cloudflare + GitHub, phase 1 (not activated)

This is a **read-only audit scheduler**, not a cloud LLM host and not an OpenHands auto-dispatcher.

## Architecture
Cloudflare Cron -> inspect open issues labelled `tel99-mission` -> GitHub `repository_dispatch` -> read-only GitHub Actions audit -> downloadable artifact.

No trading, production write, automatic merge, deployment, or OpenHands usage. This does **not** extend the OpenHands free quota or guarantee hours of LLM work.

## Activation prerequisites (not performed)
1. Review PR and merge the workflow into GitHub's default branch (GitHub repository_dispatch workflows must exist on the default branch). Keep TEL99 product branches untouched.
2. Create a **fine-grained** GitHub token restricted to this repository with only the minimum permissions required to dispatch the event. Store it as Cloudflare Worker secret `GITHUB_DISPATCH_TOKEN`, never in source.
3. Deploy with Wrangler on a verified **free** Cloudflare account.
4. Confirm a manually triggered read-only audit first.
5. Only after explicit operator approval, set `TEL99_ENABLED=true` and add one UTC cron to wrangler config. Cron triggers use UTC; choose an appropriate time for daylight-saving transitions.
6. Check GitHub Actions usage, Cloudflare logs, error paths, and avoid relabelling the test issue #68 as active.

## Limitations
- Cloudflare Free Workers are suitable for short dispatches, not long-running Python or LLM execution.
- GitHub Actions is a job runner, not an LLM. Actual OpenHands agent work remains governed by the existing plugin and its quota/budget/guard checks.
- The Cloudflare schedule is intentionally absent. Nothing in this PR is deployed or enabled.
- The GitHub workflow is read-only; it does not dispatch OpenHands. That extension requires a separate security review and explicit authorization.
