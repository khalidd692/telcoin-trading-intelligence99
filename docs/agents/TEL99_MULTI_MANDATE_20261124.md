# TEL99 — validated-controller dispatcher (PR #190)

Reuses the existing TEL99 Runtime, LocalCodeCampaign, CAS, approvals, GitHub receipts, independent Docker verifier and draft PR publisher. No new supervisor or model is introduced.

Safety: controllers #181 and earlier are refused, including completed controller #178. Every new controller requires an owner-authored GitHub mandate, SHA-256 pinned comment, independently approved mission contracts and isolated pinned Git base. No auto-merge or trading.

An owner-prepared local JSON manifest outside the repo must have version=1 and campaigns as a nonempty list (up to 10) of objects with issue (integer >181), mandate_comment (positive integer), mandate_sha256 (64 lowercase hex), base_ref (approved isolated branch), base_sha (40 lowercase hex). No placeholder is a valid authorization.

On each poll, the manifest is reread. A second controller added to it is checked for owner identity and all signed approvals before workers start. Each controller has its own durable state directory. Completed tasks are not reexecuted; uncertain RUNNING worker outcomes remain AWAITING_HUMAN.

PowerShell: use scripts/agents/automation/run_github_multi_mandate.ps1 -Mode Preflight -Manifest <PATH>; then -Mode Run -Manifest <PATH> -Minutes 60 -PollInterval 30. In a second console use -Mode Status or -Mode Stop. Stop writes the parent stop.request AND a stop.request inside every existing campaign ledger; legacy .kilo/STOP is honored too. To resume, the operator must audit and deliberately clear the appropriate STOP markers, never erase any CAS receipts or mission checkpoints.

Tests: python -B -m unittest tests.test_github_hour_queue tests.test_github_multi_mandate_session tests.test_github_local_code_campaign tests.test_autonomy_runtime tests.test_local_code_pr_publisher

Offline tests and CI do not prove a real 60-minute session, two live controllers publishing draft PRs, or cloud autonomy. A controlled real campaign with new owner mandates is still required.