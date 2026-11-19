# Integration plan — issue 123
Spec: owner mandate 2026-11-19 and canonical CRITERES_DE_FIN.md.
Base main 44ca6bd900505b587220244a15e14e789a8b501a.
Reuse PR119 Supervisor and FileStore/Inbox; PR120 native free provider; PR121 project memory; PR122 evaluation controls.
1. Preserve Kilo dirty worktree evidence locally without modification.
2. Import only existing dependencies at pinned refs; no branch merge.
3. Add Runtime(Supervisor) adapter: approved durable synthetic registry, content seal anchored by trusted operator file, CAS per mission, persistent states.
4. Tests first: two tasks, duplicate ACK, real multiprocessing, interrupted running fail closed, recover receipt without reexecution, red verdict, unavailable network/provider/verifier, STOP and persistent results.
5. Real restricted specialist via CLI if verified confinement; otherwise existing anonymous free provider with only synthetic prompts. Independent deterministic subprocess verifier.
6. Windows start/status/stop launcher; bounded run count/duration/call budgets; no service.
7. Independent review, tests, checkpoint and draft PR if checks pass. Backlog tasks require live acceptance, never infer from documentary todo.
Crash between side effect and durable receipt is uncertain: AWAITING_HUMAN, never automatic second provider call.
