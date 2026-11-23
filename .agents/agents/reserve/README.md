# Reserved TEL99 specializations

These OpenHands profiles mirror the remaining roles of `docs/agents/ROLE_CATALOG.md`.
The catalogue documents the availability of each role in the local code pipeline.

The OpenHands SDK only loads top-level `*.md` files from `.agents/agents`, so
nothing in this subdirectory can be triggered as a sub-agent. To activate one,
move its file up one level (`.agents/agents/`) and add its name to
`ACTIVE_AGENTS` in `scripts/agents/team_config.py`.

The reserved profiles have no OpenHands execution permissions until an operator
activates them explicitly.
