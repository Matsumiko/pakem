# Pakem Git Worktree Adapter v1

Pakem provides explicit, local Git worktree isolation for multi-agent tasks.
It creates branches named `pakem/<task-id>/<agent-id>` under
`.pakem/worktrees/<task-id>--<agent-id>`.

```bash
pakem worktree create T1 --agent backend --base main
pakem worktree list --json
pakem worktree remove .pakem/worktrees/T1--backend
```

Only worktrees under `.pakem/worktrees/` can be removed by this adapter.
Removal refuses dirty worktrees unless `--force` is explicitly provided.
Force removal can discard uncommitted work. Branches are never deleted
implicitly. Creating worktrees does not assign a Pakem task, run tests, merge,
push, or prove the changes correct.
