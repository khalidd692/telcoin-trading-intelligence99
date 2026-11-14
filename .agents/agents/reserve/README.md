# Reserved TEL99 specializations

These definitions mirror the remaining roles of `docs/agents/ROLE_CATALOG.md`.
They are **prepared but not active**.

The OpenHands SDK only loads top-level `*.md` files from `.agents/agents`, so
nothing in this subdirectory can be triggered as a sub-agent. To activate one,
move its file up one level (`.agents/agents/`) and add its name to
`ACTIVE_AGENTS` in `scripts/agents/team_config.py`.

No reserved role runs, is scheduled, or has any permission until an operator
does that explicitly.
