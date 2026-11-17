---
name: pakem
description: "Pakem: agent work discipline with finish gates."
license: MIT
compatibility: Python 3.10+; Linux/macOS tested, Windows best-effort
metadata:
  version: "1.2.1"
---

# Pakem

Pakem makes agent work **consistent, resumable, and provably done**, in any agent and in any session. Agents may change; pakem stays.

Pakem **does not chase file completeness**. Only artifacts that support continuity and verification are required; the rest are chosen by risk through `pakem audit`, not created to make the repo look complete.

Pakem is not a sandbox and not a replacement for tests. From 0.8.0, Pakem provides a workflow runtime, policy decisions, lifecycle hooks, checkpoint, and recovery metadata. From 0.9.0, Pakem adds a shared task board, leases, handoff, and independent review for multi-agent coordination. From 1.0.0, Pakem Protocol v1.0 is frozen as a stable contract with capability negotiation, an MCP stateless stdio adapter, and Git worktree isolation. From 1.1.0, Pakem adds Ed25519 agent identity/signed delegation and an opt-in local SQLite coordination backend. From 1.1.1, README is no longer REQUIRED for `oneoff` projects, the reviewer role requirement on `team review` is documented, and per-task `--verify` preserves shell pipes. From 1.1.2, every schema `$id` uses `urn:pakem:...` so validation does not depend on any domain. From 1.1.3, `approvals.json` has a schema (`runtime/v1/approval.schema.json`), `evals/` has a runner (`scripts/run_evals.py`), and the skill `description` is shortened so its trigger is visible in the agent index. From 1.2.0, the `scope` gate compares actual changes against task scope (PLAN.md and board), the `worktree` gate does the same for each managed worktree, the `acceptance` gate (`finish` only) rejects unchecked boxes, `pakem reconcile` reports scope and acceptance read-only (`--json` for tools), and `team submit`/`team review --sign` + `team verify` bind board actions to Ed25519 identities. The runtime does not execute commands, orchestrate model processes, or guarantee OS/process identity; the host agent/runtime must still enforce policy and mediate approval through a trusted channel.

The CLI lives in `scripts/pakem.py` (Python 3.10+, standard library). Ed25519 operations need the optional `cryptography` dependency; other features work without extra dependencies. After `init`, a copy lives in `.pakem/pakem.py` and that is what you use day to day.

Below, `pakem` means `python3 .pakem/pakem.py`. On Windows, replace `python3` with `python` or `py -3`.

## When to use

- Starting a new project, or joining a project that already has `.pakem/`.
- Continuing multi-session work, or recovering a session interrupted after another agent stopped midway.
- Choosing project documents/structure, or when the user asks "what files need to exist".
- Multi-file work that needs an approved spec, a plan, and completion evidence that can fail.
- When the user says "pakem" or ".pakem".
- **Do not** use it for short questions or a trivial single-file edit.

## Ed25519 identity and delegation (1.1.0)

- `pakem identity create <agent>` creates an Ed25519 keypair. The public key and revocation metadata live in `.pakem/identity/registry.json`; the private key is stored in the user config directory, not the repository.
- Never copy the private key into the source tree, commits, logs, transcripts, or shared output.
- `pakem identity sign <agent> --file payload.json` creates a signed envelope; `pakem identity verify` must use the project's trusted public registry. Use `identity rotate` to rotate keys and `identity revoke` to revoke an agent.
- Delegation tokens must be scoped by audience, action, and TTL. The host must check the signature, subject, audience, action, expiry, and revocation, and bind the token to the correct caller.
- Tokens are bearer credentials and can be replayed before they expire. The host must provide anti-replay, rate limiting, and secure token storage.
- A signature proves possession of the private key at signing time and payload integrity; it does not prove the claims are true, that the agent process is secure, or that the transport is authenticated.
- Identity operations need the optional `cryptography` package. A failure of this dependency must not disrupt other Pakem workflows.

## Coordination storage (1.1.0)

- JSON/JSONL stays the default, backward-compatible backend.
- SQLite is used only after the operator explicitly runs `pakem team storage migrate --to sqlite`.
- Migration keeps `board.json` and `events.jsonl` as read-only backups; SQLite becomes authoritative once the backend configuration changes.
- Create a consistent snapshot with `pakem team storage backup --output <file>`.
- The SQLite backend is local-only and depends on reliable filesystem locking/WAL. Do not use it as a distributed coordination service or assume it is safe on arbitrary network filesystems.
- Do not claim multi-host consensus or automatic agent spawning; those features need a trusted server backend and a separate orchestration host.

## Flow A - project does NOT have `.pakem/` yet

1. **Classify** the project (see table). If unsure or the requirements are ambiguous, ask the user one short question; do not guess.
2. Install: `python3 <lokasi-skill>/scripts/pakem.py init --type <jenis>`
   - An existing repo automatically enters "follow the existing pattern" mode: no folder is created or reshaped.
   - Add `--hook` to install a git pre-commit hook that runs `check`.
3. **Fill every `[FILL: ...]`** in `.pakem/*.md` with real project facts (not guesses), and make sure `verify` in `.pakem/PROJECT.md` contains the correct test/lint/build commands. While placeholders remain, the gate refuses.
4. For `oneoff`, README is RECOMMENDED: a `verify` that proves the output is enough. Decide the risk flags at the top of `PROJECT.md`: `exposure` (private/public), `deploy` (none/staging/production), `handover` (true/false), `sensitive` (true/false). Then run `pakem audit` to see which artifacts are worth it. **Do not** create everything recommended; do what is REQUIRED, defer RECOMMENDED with a reason, skip NOT NEEDED.
5. Continue to Flow B.

| Type | Examples | Default rules |
|---|---|---|
| `oneoff` | make a PDF, convert data, automation script | no tests/adr/modular; `verify` = a command that proves real output |
| `app` | web app, API, bot, service | tests required, ADR when there is a decision, modular required |
| `library` | SDK, package, CLI tool | like `app`, plus a public API contract |
| `research` | compare technologies, prototype | `docs/research/` required, tests skipped |

Folders are created only when the rules demand it: `tests/` for projects with logic, `docs/adr/` for decisions with real alternatives (`pakem adr "judul"`), `docs/research/` for exploration whose results get reused. For simple scripts, do not force it.

## Autonomous Runtime and Policy (0.8.0)

After `init`, every project gets `.pakem/POLICY.json` with the default mode `assisted`. The workflow runtime is optional and can be started with:

```bash
pakem runtime init "<goal>"
pakem runtime status --json
pakem runtime transition ready --reason "spec dan plan disetujui"
pakem runtime transition executing --task-id T1
pakem runtime checkpoint --label "sebelum perubahan berisiko"
```

Before running an action, the host agent can call the hook: `pakem runtime hook task.before --payload-file action.json --json`. Continue only when the decision is `allow`; `require_approval` must request user consent from a trusted host channel; `deny` stops the action. The agent must not call `policy approve` to approve its own actions.

Policy modes: `manual` asks for approval on every action except reads; `assisted` allows ordinary edits, but asks for approval on medium/high commands and sensitive categories; `guarded_autonomous` allows commands/actions up to `maxAutonomousRisk`, except sensitive categories, which always ask for approval. `deniedCategories` categories are still denied.

`pakem runtime recover` only restores workflow metadata to `recovering`. It does not restore source code or change the Git working tree. The agent must inspect `git status`/diff before continuing. The runtime provides decisions and receipts; it does not execute commands, deploy, or run agents.

## Pakem Protocol v1.0 Stable Contract (1.0.0)

The session Protocol v1.0 event envelope and compatibility rules are frozen. Additional features are negotiated as capabilities, not by silently changing the shape of v1 events.

```bash
python3 .pakem/pakem.py protocol info
python3 .pakem/pakem.py protocol negotiate --peer-version 1.0 \
  --capability events.v1 --capability context.snapshot.v1 --capability coordination.v1 --json
```

The Pakem protocol version is independent of the MCP, CLI, model, and implementation-language versions. A capability signals contract support, not permission to run side effects. Actor name, local agent ID, and MCP `clientInfo` are attribution metadata, not proof of authentication.

## MCP Adapter (modern stateless stdio)

Pakem provides an MCP stdio adapter without external dependencies. The implementation targets MCP `2026-07-28`: every request carries `protocolVersion` and `clientCapabilities` in `params._meta`, and the server provides `server/discover`, `tools/list`, and `tools/call`.

```bash
# Read-only adalah default
python3 .pakem/pakem.py mcp serve

# Mutasi task board hanya untuk identitas tetap yang diberikan host tepercaya
python3 .pakem/pakem.py mcp serve --agent-id backend --allow-write
```

Read-only tools cover context, Protocol info, team status/events, dependency graph, impact analysis, and policy check. Team mutation tools are exposed only when `--allow-write` and `--agent-id` are used; claim/heartbeat/submit use the server-bound identity, not an ID passed as a tool argument. Reviewers and leads get the tools their board role allows. MCP `clientInfo` is not authenticated by MCP; the host must bind the process to the right agent. Do not expose the stdio adapter as a network service without additional authentication and authorization.

The adapter does not open arbitrary shell execution, raw file writes, deployment, merge, push, or policy edits. stdout carries JSON-RPC only; diagnostics go to stderr.

## Git Worktree Isolation

To isolate the working directory per task/agent, Pakem can create a Git worktree in `.pakem/worktrees/` with the branch `pakem/<task>/<agent>`.

```bash
python3 .pakem/pakem.py worktree create T1 --agent backend --base main
python3 .pakem/pakem.py worktree list --json
python3 .pakem/pakem.py worktree scope T1--backend --strict
python3 .pakem/pakem.py worktree remove .pakem/worktrees/T1--backend
python3 .pakem/pakem.py worktree cleanup [T1] [--dry-run]
```

`worktree scope` compares the worktree content (commits on the branch + uncommitted changes + untracked files) against the task scope recorded in its name. `--strict` exits 1 if there is code outside the scope. The `worktree` gate runs the same check for all active worktrees at `check`/`finish`, so scope creep inside isolation does not vanish when the branch is merged.

`worktree cleanup` removes safe worktrees: clean (no uncommitted changes) and with commits already part of HEAD. A worktree with unmerged commits or uncommitted files is left alone and reported — that is unfinished work, not garbage. `plan done <id>` runs this cleanup for that task and prints `[WT ] ... deleted` or `[WARN] worktree ... left as is: <reason>`.

Removal refuses a dirty worktree unless `--force` is explicit. Branches are not deleted automatically (except by `cleanup`, which uses `git branch -D` only after the worktree is removed). Worktree isolation does not automatically assign tasks, run tests, merge, push, or prove the changes are safe. Merge/conflict orchestration remains the responsibility of the review workflow and the Git operator.

## Flow B - project ALREADY has `.pakem/` (every session)

1. Read `.pakem/CONTEXT.md`, then only the files its routing points to.
2. `pakem start "<goal>"`. If a session was interrupted, this command shows it along with a **repo condition check** (new commits or changed files since the last note). Read the `CHECK` section, verify briefly, then **continue from `nextStep`**; do not start from zero. If the note no longer matches the repo, record the correction through `step`.
3. Work step by step. At every reasonable stopping point:
   `pakem step "<yang baru selesai>" --next "<langkah berikutnya>"`
4. While working, keep the documents alive:
   - module structure changes → update `MODULE-MAP.md`
   - new tests go into the existing test folder; do not create both `test/` and `tests/`
   - choosing a library/pattern/architecture → `pakem adr "<judul>"` then fill in the ADR
   - fixing a bug → check `BUG-HISTORY.md` first, then `pakem bug "<judul>" --symptom ... --cause ... --fix ... --prevent ...` (empty fields become placeholders and are rejected by the gate)
5. When you need to choose documents/structure (before a release, a handover, or when the user asks "what files need to exist"): `pakem audit`. Do what is **REQUIRED**; **RECOMMENDED** may be deferred with a reason; **NOT NEEDED** must not be created.
6. Finish: `pakem finish --summary "<apa yang selesai + bagaimana dibuktikan>"`. Add `--fixed-bug` if this work fixes a bug; the bug gate requires a `pakem bug` entry from this session. `finish` prints `[EVIDENCE] verify: ...` (status/exit/hash) and `[WARN] required:` for audit gaps. Add `--strict` if you want this to fail the session (rules/CLI changed, verify not a pass, or a REQUIRED gap). `finish` also prints `[WARN] risk:` for gaps matching the flags (`deploy`/`sensitive`/`exposure`/`handover`); report them, but they do not block. Before that, `pakem reconcile` shows which files changed outside the plan scope and which acceptance criteria are still unchecked.
7. **Do not say "done" to the user before `finish` exits 0.** If it fails, honestly report which gate failed and fix it.
8. **Report every `[WARN]` line to the user** as-is (see "Rule change warnings").

Other commands: `status` (summary), `check [--skip-verify]` (gates without closing the session), `reconcile [--json] [--strict]` (changes vs plan scope vs acceptance, read-only), `audit [--json] [--strict]` (sort artifacts, read-only), `spec`/`plan` (spec + small tasks), `handover` (create one `HANDOVER.md`), `doctor` (setup diagnosis), `prune` (prune old sessions), `ci` (create a CI workflow), `upgrade` (update CLI/flags/adapters without touching documents), `adapt` (regenerate adapters), `hook install`, `team` (multi-agent coordination).

## Spec & plan (non-trivial work)

For multi-file features/changes, do not start coding immediately. This is optional: for a typo/single-file edit, skip it.

1. **Spec**: `pakem spec "<title>"` creates `.pakem/SPEC.md` (problem, non-goals, acceptance, approach). Fill every `[FILL: ...]`, then `pakem spec --approve`. While the status is still `draft`, `check`/`finish` fail at the `spec` gate.
2. **Plan**: split the work into 2–5 minute tasks:
   `pakem plan add "tulis parser" --files "src/parser.ts,tests/parser.test.ts" --verify "npm test -- parser"`
   ```text
   - [ ] T1 - tulis parser | files: src/parser.ts,tests/parser.test.ts | verify: npm test -- parser
   ```
3. **Work the task**, then `pakem plan done T1` — that command runs the task's `--verify` and stores evidence (exit code, output hash, scope file fingerprints). If verify fails, the task stays open. For exceptions: `pakem plan done T1 --no-verify --reason "..."` (recorded as a waiver, visible at the gate). If a task turns out to be irrelevant: `pakem plan drop T1 --reason "..."`.
4. `pakem plan list` / `pakem status` show progress. `finish` fails at the `plan` gate while any `[ ]` task remains. Tick `- [ ]` → `- [x]` in the `SPEC.md` Acceptance section only when the criterion is actually proven; `finish` fails at the `acceptance` gate while any box is unchecked (`check` does not demand it, because approval happens before work starts).
5. One task = one small verifiable change. Do not put 10 files in one task.
6. Per-task `--verify` is a record, not an execution: only `verify` in `PROJECT.md` is actually run by `check`/`finish`. Write the command as-is; shell pipes are preserved.

## Source of truth

Do not duplicate content:
- `PROJECT.md` = project facts/config; `CONTEXT.md` = routing; `SPEC.md` = why/what + acceptance; `PLAN.md` = task order; session = what actually happened.
- `references/` = generic guidance, not project facts.
- The protocol in `CONTEXT.md` and the adapters are generated from one source; do not edit by hand. `pakem upgrade` syncs them, `doctor` warns about stale blocks.
- `DECISIONS.md` is an index; the details live in `docs/adr/`.
- `BUG-HISTORY.md` for bugs already fixed; still-open risks go into `HANDOVER.md`.

## Project artifacts

`pakem audit` is read-only and sorts artifacts by `type`, `exposure`, `deploy`, `handover`, `sensitive`, and repo content:

| Verdict | Meaning |
|---|---|
| **REQUIRED** | without it the next session guesses, or "done" cannot be proven |
| **RECOMMENDED** | the risk is real, but it may be deferred with an honest reason |
| **NOT NEEDED** | do not create it just for completeness |

Do the REQUIRED ones first. For RECOMMENDED ones, defer while recording the reason; do not create empty files. Create conditional artifacts when their trigger appears (first deploy, public release, first incident, first handover, first personal data). `init` prints the artifact plan; `finish` prints `[WARN] risk:` for gaps whose flags are active. At handover, create **one** `HANDOVER.md` via `pakem handover` (status, access, contacts, remaining work, risks) — do not split it into five files that go stale fast. Per-failure-mode detail and canonical choices: `references/artifacts.md`.

## Universal protocol and machine interface

Pakem Protocol v1.0 is the tool/model-independent contract in `.pakem/protocol/v1/`. At the start of a session, read `CONTEXT.md`, then `pakem context --json` before choosing the next step. Do not assume all agents use the same adapter format; use the JSON contract for integration.

- `pakem context --json` — read the project/session/spec/plan snapshot and the recommended next step before deciding on an action.
- `pakem graph --json` — map local imports/dependencies before cross-module changes or a refactor. Aliases `paths`/`baseUrl` from `tsconfig.json`/`jsconfig.json` (including `extends` and JSONC comments) are read as well; imports that fail to resolve are recorded in `unresolved_imports` with a reason (`relative`/`alias`/`baseUrl`) instead of being dropped, and dependency cycles are reported in `circular_dependencies`.
- `pakem impact --files FILE... --json` — analyze direct/transitive dependents, possibly affected tests, and risk signals before choosing verification scope. Alternative: `--base REF` or `--staged`. The `graph_health` block states whether the graph used is complete; `complete: false` means there are unresolved imports and dependents may be missed.
- `pakem events --json` — read the event ledger; use `--session ID` to limit to one session.
- `pakem events --verify [--json] [--session ID] [--expect-head HEX]` — check the hash chain: a modified event, an event missing in the middle, or a chain rewritten after sealing will fail.
- `pakem handover [--force] [--stamp] [--check]` — create or update `HANDOVER.md`. The document carries the stamp `<!-- pakem:handover head=<sha> at=<iso> -->`; `--check` (exit 1) and the `handover` gate reject a stamp that does not match HEAD, because a stale handover is more dangerous than none. At `check` this mismatch is only `WARN` — an actively committing repo will always be one commit past the stamp, and a gate that keeps firing gets ignored; at `finish` it becomes `FAIL`. After changing the content, run `--stamp`.
- `pakem integrity [--json] [--re-pin --reason "..."]` — compare the hash of `pakem.py` + every `pakem_core/*.py` against what was pinned at `start`. Exit 1 if anything was changed, removed, or added. Re-pinning requires a reason and is recorded as an `integrity.repinned` event. `check` reports it as `[WARN] rules-changed`, `finish --strict` fails on it.
- `pakem report [--json] [--session ID] [--limit N]` — roll-up: sessions (wall-clock duration, steps, events, status), tasks from PLAN.md with verify evidence status, and ledger status. Exit 1 if the ledger chain is broken.
- `pakem events --sign --identity <id> [--key PATH] [--session ID]` — seal the ledger with Ed25519. The signature binds the chain hash at seal time, so rewriting the whole chain is still caught. `--key` (or the `PAKEM_SEAL_KEY` env) uses a private key outside the host config directory — 32 raw bytes or PEM PKCS8 — so CI can seal with a mounted secret without ever putting the key in the repo. Verification only needs the public key from the registry: `pakem identity import <id> --public-key <base64>` registers it on a host that does not hold the key.
- `pakem protocol info` — see the version and the list of supported events.
- `pakem protocol validate-event FILE` — validate a single JSON event against the v1.0 envelope.
- `pakem protocol validate-session FILE` — validate session structure, while still accepting old sessions without `schemaVersion`.

Event lifecycle is recorded automatically to `.pakem/events/*.jsonl`. Events are a trail of activity, not proof of quality; check `verifyEvidence` and the gate results before declaring done. Since 1.2.0 every event carries the hash chain `integrity: {prev, hash}`, and `events --sign` adds an Ed25519 seal over the chain head. The chain detects edits and deletions in the middle; the seal detects rewriting the whole chain. What neither can detect: truncation of the last event — for that, record `head=<hash>` from the `ledger` gate outside the repo and compare it with `--expect-head`.

`pakem report` is the only summary you may quote as work numbers: the reported duration is session wall-clock time (not agent compute time), and `totals.unproven_done` counts `[x]` tasks that have no valid verify evidence. If the numbers look bad, that is what the ledger says.

Dependency graph and impact analysis are static read-only heuristics; `graph_health.unresolved_imports > 0` means the result is definitely incomplete, not merely "maybe". Use the results to prioritize inspection/tests, not as proof that undetected areas are safe or unaffected. Still run the project's real verify and review the changes.

## Diagnosis & maintenance

- `pakem identity create <id> [--key-out PATH]` — the private key defaults to the user config (`~/.config/pakem/identities/<hash-proyek>/`), not the repo; `--key-out` puts it at an explicit path such as a CI secret directory.
- `pakem doctor [--verify] [--json]` — check config, placeholders, `.pakem/pakem.py`, Pakem Core, git, hooks, adapters, corrupt sessions, and REQUIRED gaps. Exit 1 on any FAIL; WARN does not block. When run from the skill-install CLI, `doctor` also compares the project's version and `pakem_core/*` hashes with the skill — a hand-modified Core shows up as WARN instead of staying silent.
- `pakem prune [--keep N] [--days D] [--yes]` — dry-run by default. Active sessions are never deleted; corrupt sessions are not touched.
- `pakem ci` — create `.github/workflows/ci.yml`: `pakem check` (including `verify`), `doctor`, `audit --strict`, and `events --verify`, with setup steps matching the detected stack. `doctor` catches a broken install; `audit --strict` catches REQUIRED gaps; `events --verify` catches an edited ledger.
- Upgrade from the project root using the latest CLI in the skill install: `python3 <lokasi-skill>/scripts/pakem.py upgrade --dry-run`, then repeat without `--dry-run`. **Do not use the 0.6.x `.pakem/pakem.py` CLI to start the upgrade**, because the old version does not know how to install Core modules and Intelligence schemas. Upgrade syncs the CLI, Core, flags, `.gitignore`, schemas, and adapters without overwriting the manual content of project documents; only marked Pakem protocol blocks are synced.

## Gates run by `finish`

| Gate | Fails when |
|---|---|
| session | no active session, or `--summary` is empty/too short |
| bug | (only with `--fixed-bug`) there is no `pakem bug` entry in this session yet |
| rules | `required` is not met (e.g. no test file yet) or `skip` without `reason.*` |
| placeholder | `[FILL`, `[ISI` (legacy), `{{...}}`, or `TODO` still in `.pakem/*.md`, `docs/adr/*.md`, `HANDOVER.md`, and `docs/HANDOVER.md` |
| spec | `.pakem/SPEC.md` exists but `Status` is not `approved` |
| acceptance | (only at `finish`) `- [ ]` still in the `SPEC.md` Acceptance section |
| plan | `.pakem/PLAN.md` exists but has `[ ]` tasks (or no tasks yet) |
| scope | **code files** changed outside the `--files` scope of all tasks, in the plan and the board (non-code files such as documentation/config are only reported, not failed). The anchor is HEAD at session `start`: committed changes and deleted files are checked too |
| task-verify | an `[x]` task has no verify evidence, its verify failed, or files in its scope changed after verify (stale evidence). An explicit waiver (`--no-verify --reason`) passes but is always named on the gate line; a dropped task is not claimed done, so it does not demand evidence |
| worktree | a worktree in `.pakem/worktrees/` has code changes outside its task scope, or the task has not declared a file scope |
| drift | a backticked path in MODULE-MAP/DECISIONS does not exist in the repo (add a `pakem:ignore` comment on the line that is intentionally hypothetical) |
| handover | `HANDOVER.md` exists but its HEAD stamp does not match the current HEAD (the content can mislead the receiver), or `handover=true` without the file. At `check` this is `WARN`, at `finish` it becomes `FAIL`. After updating the content: `pakem handover --stamp` |
| ledger | the event ledger hash chain is broken: content changed, an event missing in the middle, or the chain rewritten after sealing. This gate prints `head=...` as an anchor you can record outside the repo |
| verify | the `verify` command in PROJECT.md exits non-zero, or is empty without `reason.verify` |

## Rule change warnings

`start` stores a snapshot of `rule.*`, `verify`, `sensitive`, `exposure`, `deploy`, `handover`, and a manifest hash of `.pakem/pakem.py` plus every `.pakem/pakem_core/*.py`. If any of them changes during `check`/`finish`/`audit`, the line `[WARN] rules-changed: ...` appears (e.g. `rule.tests relaxed: required -> skip`, `verify changed`, `exposure downgraded: public -> private`, `deploy downgraded: production -> none`, `.pakem/pakem.py modified`). This **does not block**, but it is recorded in the session and you must report it to the user. If the change was requested by the user, say so; if not, revert it.

`finish` also emits `[WARN] required: ...` for REQUIRED audit gaps (advisory; `--strict` fails it), `[WARN] risk: ...` for gaps whose flags are active, and `[EVIDENCE] verify: ...` which records the status/exit/hash of the evidence. All of them must be reported; do not claim done just because of exit 0 without reading the evidence.

## Prohibitions

- Do not edit `scripts/pakem.py`, `.pakem/pakem.py`, or weaken `rule.*`/`verify` just to make `finish` pass. Fix the root cause. Such changes are detected and reported.
- Bypass a legitimate rule only with an honest and specific `skip` + `reason.*` in `PROJECT.md`. Reasons like "not needed" are not enough.
- Do not guess ambiguous requirements. Ask the user, or record the assumption through `step` so it is visible and correctable.
- Do not create empty files/documents to make the structure look complete. If it is not needed yet, do not create it; record the reason.
- Do not lower `sensitive`, `exposure`, `deploy`, or `handover` while a session is running just to make the audit/gates looser. That is detected and reported.
- Do not reshape an old repo structure unless asked. Follow the existing pattern.
- Do not put secrets in code or in `.pakem/`.

## References

For modularization details, when to write an ADR, the BUG-HISTORY format, the security checklist (`sensitive: true` projects), and the definition of done per project type, read `references/conventions.md` only when needed. For choosing project artifacts/documents proportionally, read `references/artifacts.md` when `pakem audit` shows gaps or at handover. For the frontend review lens (consistency, state, a11y) and the backend review lens (authorization, validation, secrets), read `references/reviews.md` before `finish` if the project has a UI or `sensitive: true`.

To run this skill's own behavioral evals: `python3 scripts/run_evals.py --validate`, then `--agent-cmd "<perintah agent>" --judge-cmd "<perintah penilai>"`. The agent and judge contracts are in `evals/README.md`.


## Multi-agent coordination (v0.9.0)

Use `pakem team status --json` to read the coordination board when the project uses several agents. Register each agent with `pakem team register ID --role worker|reviewer|lead|coordinator`; capabilities can be added with `--capability`. Create small tasks through `pakem team add ID --title ...`, include `--depends-on`, `--files`, `--risk`, and the required capabilities. The lead/coordinator does `team assign`; workers do `team claim` and `team heartbeat` while working. Release a claim with `team release`, or hand it over explicitly with `team handoff`.

Results do not become `done` immediately: the worker must `team submit` with a summary and evidence reference, then a different reviewer must run `team review --decision approve`. `team review` requires two things: a registered reviewer role (`--role reviewer`, `lead`, or `coordinator`) **and** an identity different from the implementer. Register reviewers from the start (`pakem team register qa --role reviewer`); without that the task stays stuck in `review` state forever. `rework` returns the task to open. Dependencies are ready only when all parents are done. Leases prevent concurrent claims on a shared local filesystem; a lease is not a distributed lock for network filesystems or multi-host servers. ID/role is not authentication: the host runtime must ensure the caller cannot forge `--agent`. If an agent has an identity (`pakem identity create <id>`), `team register` binds its fingerprint to the board; `team submit --sign` and `team review --sign` sign the action payload, and `pakem team verify` checks the signature, identity revocation, and whether the board content still matches what was signed. This makes the board tamper-evident, not a replacement for transport authentication. The coordination board/events are not a replacement for project `verify`, security review, or the final `pakem finish`. Do not store secrets in task title, description, notes, summary, or evidence.
