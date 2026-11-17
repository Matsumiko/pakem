<div align="center">

<img src="assets/banner.svg" alt="Pakem: Agents may change; pakem stays." width="100%">

<br>

![protocol](https://img.shields.io/badge/protocol-v1.0-d4af37?style=flat-square&labelColor=0b0a14)
![python](https://img.shields.io/badge/python-3.10+-c9a7ff?style=flat-square&labelColor=0b0a14)
![deps](https://img.shields.io/badge/core-stdlib_only-ffb3d9?style=flat-square&labelColor=0b0a14)
![license](https://img.shields.io/badge/license-MIT-f3dd9a?style=flat-square&labelColor=0b0a14)

**Language: [English](README.md) | [Bahasa Indonesia](README-ID.md)**

<a href="https://github.com/Matsumiko/pakem">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=20&pause=1200&color=FF8FB1&center=true&vCenter=true&width=700&lines=%E2%9C%A6+A+working-discipline+layer+for+coding+agents+%E2%9C%A6;Not+a+library%2C+not+a+framework.;Agents+may+change%3B+pakem+stays.+%F0%9F%8C%B8" alt="typing animation" />
</a>

<br>

Pakem makes agent work **consistent** 🌙, **resumable** 🔁, and **provably finished** ✅.

</div>

<img src="assets/divider.svg" alt="" width="100%">

## 📖 Table of Contents

| Arc | Chapter |
|---|---|
| 🌅 **Prologue** | [Problems it solves](#-prologue-problems-it-solves) |
| ⚔️ **Arc 1: Awakening** | [Install](#-arc-1--awakening-install) · [Daily usage](#-arc-2--daily-quest-daily-usage) |
| 🔮 **Arc 2: Protocol** | [Protocol & machine interface](#-arc-3--the-protocol--machine-interface) · [Stable protocol](#-stable-operating-protocol-pakem-10) · [MCP](#-mcp-adapter-mcp-2026-07-28) |
| 🛡️ **Arc 3: Guardians** | [Worktree](#-git-worktree-isolation) · [Runtime](#-autonomous-runtime-v1-080) · [Rule-change warnings](#-rule-change-warnings) |
| 📜 **Arc 4: Scrolls** | [Config](#-configuration-pakemprojectmd) · [Spec & plan](#-spec--plan-optional) · [Sources of truth](#-sources-of-truth-so-nothing-is-duplicated) |
| 🔍 **Arc 5: Trials** | [Audit](#-artifact-audit-pakem-audit) · [Gates](#-gates-pakem-finish-and-pakem-check) · [Evidence](#-evidence-and---strict) |
| 🌌 **Arc 6: Ascension** | [1.1.0 foundations](#-production-orchestration-foundations-110) · [Multi-agent](#-multi-agent-coordination-v090) |
| 🌙 **Epilogue** | [Limitations](#-honest-limitations) · [Roadmap](#-roadmap) · [License](#-license-and-distribution) |

<img src="assets/divider.svg" alt="" width="100%">

## 🌅 Prologue: Problems it solves

> *Every hero has a weakness. These are the ones agents face, and what Pakem puts in place.* (◕‿◕)♡

| 💢 Real problem | ✨ What Pakem puts in place |
|---|---|
| Agents forget project conventions in every new session | `CONTEXT.md` (routing) + `PROJECT.md` |
| Work stops mid-way, tomorrow starts from zero | `.pakem/sessions/*.json` with `lastPosition` + `nextStep` |
| An agent says "done" but it might not be | `pakem finish`: a gate that can fail (exit code 1) |
| The same bug gets fixed repeatedly | `BUG-HISTORY.md` |
| Architecture decisions get re-debated | `DECISIONS.md` + `docs/adr/` |
| Claude, Cursor, Codex each have different rules | adapters generated from one source |
| Project files are still full of placeholders | placeholder gate |
| Module docs are stale and mention deleted files | drift gate |
| Unclear which files/docs should exist | `pakem audit`: REQUIRED / RECOMMENDED / NOT NEEDED, without creating empty files |
| Agents start coding without an approved spec | `pakem spec` + `spec --approve`; `spec` gate |
| Large work is not broken down and drifts easily | `pakem plan`: 2–5 minute tasks + files + verify; `plan` gate |
| Agents drift outside the plan | `pakem reconcile` + `scope` gate (out-of-scope code fails; docs/config are reported) |
| A spec is "approved" while acceptance criteria are unproven | `acceptance` gate (at `finish`) rejects unchecked boxes |
| Agents/tools need the same work contract | Pakem Protocol v1.0 + JSON Schema |
| Agents need workflow context without parsing Markdown | `pakem context --json` |
| Gates can be run by a CLI the agent has modified | `pakem.py` manifest + `pakem_core/*` pinned at `start`; `pakem integrity` + `finish --strict` |
| The seal key exists on only one host | `--key` / `PAKEM_SEAL_KEY` + `identity import` for hosts without the private key |
| HANDOVER.md is filled in but from an old commit | HEAD stamp + `handover` gate, `--check`/`--stamp` |
| Worktrees pile up after tasks finish | `plan done` cleans up merged, clean worktrees and reports the rest |
| No work numbers that can be defended | `pakem report`: duration, steps, tasks, verify evidence, ledger status |
| Session notes can be edited without a trace | hash chain (`events --verify`) + Ed25519 seal (`events --sign`) |
| Cross-module changes are hard to map | `pakem graph` + `pakem impact` |
| Lifecycle history is hard to audit across tools | append-only JSONL event ledger + `pakem events` |
| Agent workflows are hard to standardize and recover | `pakem runtime`: state machine, checkpoints, recovery metadata |
| Risky actions need limits across agents | `POLICY.json`, one-shot approvals, lifecycle hooks |
| Several agents work on the same project without coordination | `pakem team`: task dependencies, leases, handover, shared board, independent review |
| Tool/model integrations keep changing | Pakem Protocol v1.0 stable + capability negotiation |
| Agents need a universal tool interface | MCP stateless stdio adapter; read-only by default, write tools bound to the host agent |
| Agents edit the same files from a shared working tree | Git worktree isolation per task/agent; no implicit merge/push |
| Agents drift inside a worktree and then it gets merged | `worktree` gate + `pakem worktree scope` compares the worktree diff with the task scope |
| Agent identity is just a metadata ID | Ed25519 public identity, signed attestations, revocation, and scoped delegation tokens |
| Local board/events need atomic state+audit transactions | local SQLite backend with board+event transactions and online backup |
| Protocol implementations need repeatable compatibility evidence | Pakem Conformance Profile v1 with regression tests |

<img src="assets/divider.svg" alt="" width="100%">

## ⚔️ Arc 1 · Awakening (Install)

This folder is a skill. Put it in as `pakem/` inside your agent's skills folder (e.g. `.claude/skills/pakem/` or `~/.claude/skills/pakem/`). For other agents, just run the CLI directly.

Requires **Python 3.10+**. The base CLI/Core uses only the standard library. Ed25519 identity operations are optional and require `python -m pip install cryptography`.

```bash
cd proyek-kamu
python3 /path/ke/pakem/scripts/pakem.py init --type app
```

`--type`: `app` (default), `library`, `oneoff`, `research`.
Extras: `--verify "npm test && npm run lint"`, `--adapter claude,codex,cursor,gemini,copilot` (or `none`), `--hook`.

After init, the CLI and the Pakem Core modules are copied into `.pakem/` so the project is self-contained. Core is split from the CLI so other runtimes can use the intelligence capabilities.

<img src="assets/divider.svg" alt="" width="100%">

## 🍡 Arc 2 · Daily Quest (Daily usage)

```bash
python3 .pakem/pakem.py start "build a todo web app"      # or resume an interrupted session
python3 .pakem/pakem.py step "model done" --next "build the endpoint"
python3 .pakem/pakem.py adr "Choose SQLite"               # when an architecture decision appears
python3 .pakem/pakem.py bug "Crash on empty input" --symptom "..." --cause "..." --fix "..." --prevent "..."
python3 .pakem/pakem.py spec "Export feature"            # fill, then: pakem spec --approve
python3 .pakem/pakem.py plan add "write the parser" --files "src/parser.ts,tests/parser.test.ts" --verify "npm test -- parser"
python3 .pakem/pakem.py plan done T1     # runs the task verify + stores evidence
python3 .pakem/pakem.py audit                            # which files/docs are worth having (read-only)
python3 .pakem/pakem.py finish --summary "todo CRUD works, tests pass"   # add --fixed-bug / --strict when needed
```

**🗡️ Other commands:** `status`, `context --json`, `events --json`, `graph [--json]`, `impact --files FILE...`, `protocol info`, `protocol negotiate --peer-version 1.0`, `protocol validate-event FILE`, `protocol validate-session FILE`, `mcp serve`, `worktree create/list/scope/remove`, `events --verify/--sign`, `report [--json] [--session ID] [--limit N]`, `handover [--stamp] [--check]`, `integrity [--re-pin --reason ...]`, `worktree cleanup [--dry-run]`, `identity create/list/sign/verify/issue/rotate/revoke`, `team storage info/migrate/backup`, `check [--skip-verify]`, `audit [--json] [--strict]`, `spec`, `plan`, `handover`, `doctor`, `prune`, `ci`, `upgrade`, `adapt`, `hook install`, `runtime`, `policy`, `team`.

> 🪟 **Windows:** replace `python3` with `python` or `py -3`. The adapters and `CONTEXT.md` already explain this to agents, and the git hook looks for an interpreter that actually runs. Windows support is written carefully but **not tested on Windows**.

<img src="assets/divider.svg" alt="" width="100%">

## 🔮 Arc 3 · The Protocol & Machine Interface

Pakem Protocol v1.0 separates the workflow contract from the CLI, AI model, language, and transport. The event envelope and session v1.0 compatibility are frozen; additional features are negotiated through capabilities. The spec and JSON Schema live in `.pakem/protocol/v1/`; the distribution source lives in `protocol/v1/`.

```bash
python3 .pakem/pakem.py protocol info
python3 .pakem/pakem.py protocol negotiate --peer-version 1.0 --capability events.v1 --capability context.snapshot.v1 --capability coordination.v1 --json
python3 .pakem/pakem.py context --json       # compact snapshot for agents/tools
python3 .pakem/pakem.py events --json        # structured event history
python3 .pakem/pakem.py events --verify      # verify the ledger hash chain
python3 .pakem/pakem.py events --sign --identity backend  # seal the ledger with Ed25519
python3 .pakem/pakem.py report --json       # roll-up of sessions, tasks, evidence, ledger
python3 .pakem/pakem.py events --session <session-id>
python3 .pakem/pakem.py protocol validate-event event.json
python3 .pakem/pakem.py protocol validate-session session.json

# Intelligent Core: dependency graph and change impact
python3 .pakem/pakem.py graph --json
python3 .pakem/pakem.py graph --json --output .pakem/dependency-graph.json
python3 .pakem/pakem.py impact --files src/auth.py tests/test_auth.py --json
python3 .pakem/pakem.py impact --base main --json
python3 .pakem/pakem.py impact --staged --strict --json
```

### 🕸️ Graph & Impact

`pakem graph` builds a static graph from local imports, including `paths`/`baseUrl` aliases in `tsconfig.json`/`jsconfig.json` (following `extends`, ignoring JSONC comments). Imports that cannot be resolved appear in `unresolved_imports` with the reason, and dependency cycles appear in `circular_dependencies`. `pakem impact` walks direct/transitive dependents, possibly affected tests, and risk signals.

The analysis is advisory and best-effort: dynamic imports, reflection, framework routing, code generation, and runtime wiring can be missed. `impact` includes `graph_health`: if any import is unresolved, the result is marked incomplete and its recommendation says to check aliases/baseUrl or verify manually. `--strict` returns exit 1 when the risk heuristic is HIGH; the command does not run tests and does not replace real review or verification. The scanner is read-only unless `graph --output` is explicitly requested.

### 📼 Event Ledger

Session and task lifecycle is recorded automatically as JSONL in `.pakem/events/` (local, gitignored by default). Events are appended and serialized with a Pakem lock. The ledger makes audit/handover easier, but it is **not cryptographically signed** and is not proof that the work is correct; verify results are still stored separately as evidence.

### 🧿 Context Snapshot

`context --json` provides project metadata, the active session, spec/plan progress, read-only gate results (without running verify), blockers, recommended next steps, and runtime/policy status when installed. It does not send source code content, verify commands, or secrets.

<img src="assets/divider.svg" alt="" width="100%">

## 🌠 Stable Operating Protocol (Pakem 1.0+)

Pakem Protocol v1.0 is a stable contract separate from the CLI, MCP, model, language, and provider versions. The event envelope shape and session v1.0 compatibility rules are frozen. New features are declared through capability negotiation; a capability is not authorization to perform side effects.

```bash
python3 .pakem/pakem.py protocol info
python3 .pakem/pakem.py protocol negotiate --peer-version 1.0 \
  --capability events.v1 --capability context.snapshot.v1 --capability coordination.v1 --json
```

> ⚠️ `actor.name`, agent IDs on the team board, and MCP `clientInfo` are attribution metadata. None of them proves identity. Runtime hosts must bind the caller to a trusted identity through an appropriate process/credential/transport boundary.

<img src="assets/divider.svg" alt="" width="100%">

## 🔌 MCP Adapter (MCP 2026-07-28)

Pakem ships an MCP server over stdio with no external dependencies. The adapter targets modern stateless MCP: protocol version and client capabilities are sent on every request via `params._meta`; `server/discover` advertises version/capabilities, while `tools/list` and `tools/call` expose Pakem functions.

```bash
# Read-only, default
python3 .pakem/pakem.py mcp serve

# Board mutation only when the host explicitly grants agent binding and write access
python3 .pakem/pakem.py mcp serve --agent-id backend --allow-write
```

Read-only tools: context, Protocol info, team status/events, graph, impact, and policy check. Write mode exposes claim, heartbeat, submit, review, and assign according to the registered agent's role. The actor ID comes from the server's `--agent-id`, not from a tool argument. Tools do not run arbitrary shell, deployments, merges, pushes, or policy changes.

> ⚠️ MCP `clientInfo` is self-reported; binding security only holds if a trusted host launches the process with the right identity and privileges. Do not expose the stdio server as a network service without additional authz/authn.

<img src="assets/divider.svg" alt="" width="100%">

## 🌿 Git Worktree Isolation

```bash
python3 .pakem/pakem.py worktree create T1 --agent backend --base main
python3 .pakem/pakem.py worktree list --json
python3 .pakem/pakem.py worktree scope T1--backend --strict
python3 .pakem/pakem.py worktree remove .pakem/worktrees/T1--backend
```

`worktree scope` compares the contents of a worktree (committed work on the branch, uncommitted changes, and untracked files) with the `<task>` in its name. The `worktree` gate runs the same check for every active worktree at `check`/`finish`; out-of-scope code there will end up on the branch that later gets merged, so this gate closes the "isolation = safety" gap.

Worktrees live in `.pakem/worktrees/` on branches named `pakem/<task>/<agent>`. Removal refuses a dirty worktree unless `--force`; branches are not deleted automatically. The feature isolates the working tree; it does not do task assignment, verification, merge, push, or automatic conflict resolution. Per-worktree scope checks live in `worktree scope`/the `worktree` gate, and everything else remains the operator's responsibility.

<img src="assets/divider.svg" alt="" width="100%">

## 🤖 Autonomous Runtime v1 (0.8.0)

`pakem init` installs `.pakem/POLICY.json`, the Runtime/Policy schemas, and the Core runtime modules. Local workflow state is stored in `.pakem/runtime/` and gitignored by default.

```bash
# Start and monitor the runtime workflow
python3 .pakem/pakem.py runtime init "implementasi OAuth"
python3 .pakem/pakem.py runtime status --json
python3 .pakem/pakem.py runtime transition ready --reason "spec dan plan disetujui"
python3 .pakem/pakem.py runtime transition executing --task-id T1

# Checkpoint and recovery metadata
python3 .pakem/pakem.py runtime checkpoint --label "sebelum refactor" --json
python3 .pakem/pakem.py runtime recover --json

# Lifecycle hooks and policy
python3 .pakem/pakem.py runtime hook task.before --payload-file action.json --json
python3 .pakem/pakem.py policy show --json
python3 .pakem/pakem.py policy check --category deploy --risk high --target staging --json
python3 .pakem/pakem.py policy approve --category deploy --risk high --target staging --reason "user approved staging"
```

The state machine rejects illegal transitions. A checkpoint stores workflow metadata and a snapshot of git HEAD/status. `recover` only returns workflow metadata to the `recovering` state; it does **not** check out, reset, revert, or modify source code. Always review the git diff before continuing.

**🎚️ Policy modes**

| Mode | Behavior |
|---|---|
| `manual` | requires approval for every action other than read |
| `assisted` | allows ordinary edits, but requires approval for medium/high commands and sensitive categories |
| `guarded_autonomous` | allows actions up to `maxAutonomousRisk`, except categories that always require approval |

`deniedCategories` are rejected even with approval.

Local approvals are one-shot, expire, and are bound to the workflow, category, risk level, and target. This is **not secure human authentication**: the CLI cannot prove who ran `policy approve`. The agent host must stop the action and ask the user for confirmation through a trusted channel; an agent must not approve itself. Do not put secrets or full commands into hook targets/payloads.

**🪝 Standard hooks:** `session.start`, `task.before`, `task.after`, `verification.before`, `session.finish`, `handover`. `runtime hook` returns `allow`, `require_approval`, or `deny` and records a receipt without storing the raw payload. The runtime host must enforce this decision; Pakem does not execute commands, deploys, or agents.

<img src="assets/divider.svg" alt="" width="100%">

## 🚨 Rule-change warnings

Gates can be bypassed if an agent quietly loosens the rules. That is why `start` snapshots `rule.*`, `verify`, `sensitive`, `exposure`, `deploy`, `handover`, and a manifest hash of `.pakem/pakem.py` plus every `.pakem/pakem_core/*.py`. At `check`, `finish`, and `audit`, later changes show up as:

```
[WARN] rules-changed: rule.tests relaxed: required -> skip
[WARN] rules-changed: verify changed: 'npm test' -> 'true'
[WARN] rules-changed: exposure downgraded: public -> private
[WARN] rules-changed: deploy downgraded: production -> none
[WARN] rules-changed: .pakem/pakem.py modified during this session
```

`finish` also prints risky gaps based on the flags:

```
[WARN] risk: deploy=production but no CI yet
[WARN] risk: deploy=production but no RUNBOOK.md yet
WARNING: 2 risks unresolved (advisory, non-blocking).
```

This does not block (sometimes the change was requested by the user), but it is recorded in the session and the agent is required to report it. Pakem makes loosening *visible*; it cannot stop a determined agent from cheating.

<img src="assets/divider.svg" alt="" width="100%">

## 🧭 Checking repo state on resume

On every `start` and `step`, Pakem records the HEAD commit and the list of changed files (outside `.pakem/`). When `start` finds an interrupted session, it compares that with the current state:

```
CHECK: repo state changed since the last record:
  - HEAD changed (2 new commits)
  - changed since the last record: M src/api.py; ?? scratch.txt
```

So a stale `nextStep` or work that never got recorded is immediately visible. Only active in git repos.

Session files are written atomically (write to a temp file, `fsync`, then rename), so a power loss mid-write cannot leave half a JSON file. All `.pakem/*.md`/ADR/BUG-HISTORY writes use the atomic path too, and session/document mutations are locked across processes (`pakem_lock`). If a session file is nonetheless corrupt, `status`/`start`/`check`/`finish` print `[WARN] corrupt session ignored: ...`, so no more silent loss.

<img src="assets/divider.svg" alt="" width="100%">

## 🏯 What `init` creates

```
.pakem/
├── CONTEXT.md        entry point + routing: read this first
├── PROJECT.md        config (verify, rule.*) + stack + conventions
├── MODULE-MAP.md     module map (app/library)
├── DECISIONS.md      decision index (app/library/research)
├── BUG-HISTORY.md    bug history (app/library)
├── pakem.py          standalone CLI per project
├── POLICY.json       autonomy and approval policy (project-managed)
├── pakem_core/       Core modules (intelligence + autonomous runtime)
├── protocol/v1/      event/session contract
├── intelligence/v1/  graph/impact output schemas
├── runtime/v1/       workflow/checkpoint/lifecycle hook schemas
├── policy/v1/        policy schema
├── sessions/         per-session JSON (gitignored by default)
├── events/           local event ledger (gitignored by default)
└── runtime/          workflow, checkpoints, approvals, hook receipts (gitignored)
docs/adr/             only when the adr rule is active (new project)
tests/                only when tests rule = required (new project)
CLAUDE.md, AGENTS.md, .cursor/rules/pakem.mdc   adapters (marked blocks, existing content preserved)
```

**Conditional scaffolding:** `oneoff` only gets `CONTEXT.md` and `PROJECT.md`. Existing repos are detected automatically and **not rewritten**; only `.pakem/` and adapters are added.

<img src="assets/divider.svg" alt="" width="100%">

## 📜 Configuration (`.pakem/PROJECT.md`)

The top of the file holds configuration, one `key: value` per line:

```
type: app
sensitive: false
exposure: private
deploy: none
handover: false
verify: npm test && npm run lint
rule.tests: required
rule.adr: when-decision
rule.research: skip
reason.research: stack sudah ditentukan user, tidak ada eksplorasi
rule.modular: required
```

`rule.*` values: `required`, `skip`, `when-decision`, `when-needed`. Every `skip` **must** have a `reason.*`. Gates do not fail because a folder is missing, but they fail if a rule is skipped silently.

**🚩 Risk flags** (read by `pakem audit`, not gates):

| Flag | Values | Effect on audit |
|---|---|---|
| `exposure` | `private` / `public` | public → suggests LICENSE, CONTRIBUTING, SECURITY, PR/issue templates |
| `deploy` | `none` / `staging` / `production` | deploy → suggests CI, DEPLOYMENT, RUNBOOK |
| `handover` | `true` / `false` | true → suggests HANDOVER, access, known issues, tech debt |
| `sensitive` | `true` / `false` | true → suggests SECURITY, threat model, secret scan |

`start` snapshots all four flags; lowering them mid-session produces `[WARN] rules-changed`. Audit remains read-only and never creates files.

<img src="assets/divider.svg" alt="" width="100%">

## 📝 Spec & plan (optional)

For multi-file features/changes, don't start coding right away. For a typo or a one-file edit, skip it.

```bash
python3 .pakem/pakem.py spec "Export feature"     # create .pakem/SPEC.md
# fill Problem / Non-goals / Acceptance / Approach
python3 .pakem/pakem.py spec --approve          # all [FILL] placeholders must be filled

python3 .pakem/pakem.py plan add "write the parser" \
  --files "src/parser.ts,tests/parser.test.ts" \
  --verify "npm test -- parser"
python3 .pakem/pakem.py plan list
python3 .pakem/pakem.py plan done T1     # runs the task verify + stores evidence
python3 .pakem/pakem.py plan drop T2 --reason "no longer relevant"
```

- 📄 `SPEC.md` stays `draft` until `spec --approve`; while it is a draft, `check`/`finish` fail at the `spec` gate.
- 🗒️ Every task carries `files` and `verify`; while any `[ ]` remains, `check`/`finish` fail at the `plan` gate. `plan drop` marks a task done with a reason.
- ✅ The Acceptance section of `SPEC.md` must be checked (`- [x]`) before `finish` passes the `acceptance` gate; `check` only requires approval, since the spec is approved before work starts.
- 🧾 Every `[x]` task needs valid verify evidence: `plan done` runs that task's `--verify` and records the exit code, output hash, and scope-file fingerprint in `.pakem/verify/tasks.json`. If a scope file changes after verification, the `task-verify` gate rejects until the evidence is refreshed. Exceptions must be explicit: `--no-verify --reason "..."`, and the waiver is always named on the gate line. Dropped tasks are not claimed as done, so they require no evidence.
- 🎯 **Code** changes outside the `--files` of all tasks fail the `scope` gate; non-code files (docs, config, lockfiles) are only reported. The baseline is HEAD at session `start`, so already-committed changes and deleted files remain visible, and `git diff HEAD` alone is not enough. `pakem reconcile` shows both before `finish`.
- 🌿 The `worktree` gate repeats that check for each managed worktree: branch diff + uncommitted changes + untracked files compared against the task scope in the worktree name, and tasks with no file scope are reported too.
- ⏱️ Task target: 2–5 minutes, one small change that can be verified.
- 👀 `start`/`status` show spec status and plan progress; `doctor` warns when either is still draft/pending.

<img src="assets/divider.svg" alt="" width="100%">

## 🗝️ Sources of truth (so nothing is duplicated)

| File | Role | Don't put here |
|---|---|---|
| `PROJECT.md` | project facts + config (`verify`, `rule.*`, flags) | task history |
| `CONTEXT.md` | routing: what to read first; the protocol block is generated | feature specs |
| `SPEC.md` | why/what + acceptance for one piece of work | task list |
| `PLAN.md` | task order (how) for that work | problems/non-goals |
| session JSON | what actually happened (`steps`, `nextStep`) | intent/plans |
| `MODULE-MAP.md` | module structure | work status |
| `DECISIONS.md` + `docs/adr/` | decision index + details | bugs/work history |
| `BUG-HISTORY.md` | fixed bugs | still-open bugs |
| `HANDOVER.md` | final snapshot: access, contacts, remaining work, risks | passwords/secrets |
| `references/` | generic guidance | project-specific facts |

Rule: **don't copy content**, point to the source file. `CONTEXT.md` and the adapters use a protocol generated from one source; `pakem upgrade` syncs the blocks, `doctor` warns when they are stale.

| Command | Role |
|---|---|
| `status` | read-only summary |
| `check` | gates that can fail |
| `reconcile` | read-only report: git changes vs task scope (plan/board) vs acceptance (`--json`, `--strict`) |
| `finish` | gates + verify evidence + close the session |
| `audit` | artifact inventory, advisory |
| `doctor` | setup diagnosis (config/git/hook/adapter/session) |
| `spec` / `plan` | workflow state, not verification gates |

<img src="assets/divider.svg" alt="" width="100%">

## 🔍 Artifact audit (`pakem audit`)

Pakem does not chase file completeness. `audit` sorts artifacts by `type`, `exposure`, `deploy`, `handover`, `sensitive`, and repo contents:

```
AUDIT  your-project
configuration: type=app exposure=private deploy=none handover=false sensitive=false

REQUIRED - continuity & verification
  [ok]  README.md
  [gap] verify — fill in the test/lint/build command
  [gap] tests/ — logic needs tests run by verify

RECOMMENDED - risk-based; may be deferred with a reason
  [gap] .env.example — code reads the environment
  ...

NOT NEEDED - do not create just for completeness
  [-]   LICENSE — private repo; change exposure: public if it will be released
  [-]   docs/decisions/ — canonical: docs/adr/ — do not keep both
  ...
```

- 👁️ `audit` is **read-only**: it creates no files and changes no configuration.
- 🤖 `--json` for agents; `--strict` exits 1 when any REQUIRED item is missing.
- 🕰️ RECOMMENDED items may be deferred with an honest reason; do not create empty files.
- 🎬 `init` immediately prints an artifact plan summary.
- ⚠️ `finish` prints `[WARN] risk: ...` for gaps whose flags are active (e.g. `deploy=production but no RUNBOOK.md yet`). This is **advisory**: it does not change the exit code, but it must be reported.
- 📦 `pakem handover` creates **one** `HANDOVER.md` (status, access without passwords, contacts, remaining work, risks). Its placeholders are rejected by the gate until filled; don't split it into `ACCESS` + `KNOWN_ISSUES` + `TECH_DEBT` + `HANDOVER` that go stale fast.
- 📚 Per-failure-mode details, canonical choices (e.g. `docs/adr/` rather than `docs/decisions/`), and the list of things that must not be created automatically: `references/artifacts.md`.

<img src="assets/divider.svg" alt="" width="100%">

## 🩺 Diagnosis and maintenance

```bash
python3 .pakem/pakem.py doctor            # check config, placeholders, git, hooks, adapters, sessions
python3 .pakem/pakem.py doctor --verify   # also run the verify command
python3 .pakem/pakem.py prune             # dry-run: show old sessions that can be pruned
python3 .pakem/pakem.py prune --yes       # delete; active sessions and the newest N are kept
python3 .pakem/pakem.py ci                # create .github/workflows/ci.yml
# Run the newest CLI from the skill install, from the project root (including upgrades from 0.6.x)
python3 /path/ke/pakem/scripts/pakem.py upgrade --dry-run
python3 /path/ke/pakem/scripts/pakem.py upgrade
```

- 🩹 `doctor` exits 1 on any **FAIL** (broken config, empty verify, leftover placeholders, corrupt session); WARN is only a suggestion. `--json` for agents. It also warns about draft SPECs and PLANs with open tasks.
- 🧹 `prune` defaults to `--keep 20 --days 90`; active sessions are never deleted, corrupt sessions are left alone.
- 🏗️ `ci` detects Node (npm/pnpm/yarn), Python, Go, or Rust and then runs `pakem check`, so `verify` stays the single source of truth. `--force` overwrites an existing workflow.
- ⬆️ `upgrade` refreshes the CLI, Core modules, protocol/intelligence schemas, new flags, `.gitignore`, and adapters. Manual project-doc content (including `MODULE-MAP.md`/ADRs) is preserved; only the marked Pakem protocol blocks in `CONTEXT.md`/adapters are synced. Run `--dry-run` first and use the newest CLI from the skill install.

<img src="assets/divider.svg" alt="" width="100%">

## 🧪 Evidence and `--strict`

`finish` stores verify evidence in the session (`verifyEvidence`): command, exit code, duration, output hash, and the hash of `.pakem/pakem.py`; when it runs, it prints:

```
[EVIDENCE] verify: pass exit=0 hash=4355a46b19d348dc
```

By default `finish` stays advisory: missing REQUIRED audit items show up as `[WARN] required: ...`. Add `--strict` to make the session **fail** when rules/CLI changed, `verify` is not `pass`, or a REQUIRED audit item is missing. That is what makes "finished" harder to fake, rather than just exit 0.

<img src="assets/divider.svg" alt="" width="100%">

## 👓 Review lens

`references/reviews.md` contains a frontend lens (component/token consistency, loading/empty/error states, responsiveness, a11y) and a backend lens (server-side authorization, boundary validation, parameterized queries, secrets, PII, fail closed). Read it before `finish` when the project has a UI or `sensitive: true`; it is not a gate and does not replace human review.

<img src="assets/divider.svg" alt="" width="100%">

## 🚪 Gates (`pakem finish` and `pakem check`)

| Gate | Fails when |
|---|---|
| session | (`finish` only) no active session or empty `--summary` |
| bug | (`finish --fixed-bug` only) no `pakem bug` entry in this session |
| rules | a `required` rule is unmet, or a `skip` has no reason |
| placeholder | leftover `[FILL`, `[ISI` (legacy), `{{...}}`, `TODO` in `.pakem/*.md` and `docs/adr/*.md` |
| spec | `.pakem/SPEC.md` exists but is not `approved` |
| plan | `.pakem/PLAN.md` exists but tasks are still `[ ]` |
| drift | a backticked path in MODULE-MAP/DECISIONS does not exist in the repo |
| verify | the `verify` command exits non-zero, or is empty without `reason.verify` |

Exit code 1 when anything fails. The verify gate runs **your project's** tests/lint/build: Pakem does not replace tests, it forces them to run. `[WARN] risk:` lines from audit do not change the exit code.

<img src="assets/divider.svg" alt="" width="100%">

## 🛡️ Enforcement

- **Git pre-commit:** `python3 .pakem/pakem.py hook install` (add `--skip-verify` when tests are too slow for every commit). The hook is installed in the folder git actually reads, so `core.hooksPath` and worktrees are supported.
- **Agents:** adapters inject the protocol into `CLAUDE.md`, `AGENTS.md`, etc. For Claude Code you can also install a Stop hook that runs `check`; check the docs for the version you use for the latest format.

<img src="assets/divider.svg" alt="" width="100%">

## 🧫 Tests

The full suite needs two optional dependencies (one test module uses them for Ed25519, another for JSON Schema validation):

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
```

Without those dependencies the suite still runs and stays green; 14 tests skip with the reason shown in the output.

Skill behavior evals (not code) are checked separately:

```bash
python3 scripts/run_evals.py --validate     # struktur evals.json
python3 scripts/run_evals.py --list         # 24 eval
```

Running the evals needs an agent command and a judge command; the contract is in `evals/README.md`.

<img src="assets/divider.svg" alt="" width="100%">

## 🌌 Production Orchestration Foundations (1.1.0)

Pakem 1.1 adds two foundations for stronger coordination. Both are opt-in and preserve the default compatibility of previous versions.

### 🔑 Ed25519 agent identity

Identity public keys are stored and can be shared via `.pakem/identity/registry.json` (public metadata); private keys live in the user config directory (`$XDG_CONFIG_HOME/pakem/identities/` on Linux/macOS or `%APPDATA%/Pakem/identities/` on Windows), not in the repository. Private key files are written with owner-only permissions where the OS supports it.

```bash
# Needs the optional dependency: python -m pip install cryptography
python3 .pakem/pakem.py identity create backend
python3 .pakem/pakem.py identity list --json
python3 .pakem/pakem.py identity sign backend --file receipt.json --output receipt.signed.json
python3 .pakem/pakem.py identity verify receipt.signed.json
python3 .pakem/pakem.py identity rotate backend --reason "scheduled key rotation"

# Delegation tokens are limited by audience, action, and lifetime (30 seconds–24 hours)
python3 .pakem/pakem.py identity issue backend \
  --audience pakem-host://worker-01 \
  --action team.claim --action team.submit --ttl-seconds 900 > delegation.json
python3 .pakem/pakem.py identity verify delegation.json \
  --audience pakem-host://worker-01 --action team.claim

python3 .pakem/pakem.py identity revoke backend --reason "agent retired"
```

`identity rotate` creates a new keypair and keeps the old key's public metadata as retired; old signatures are no longer accepted as the active identity. Signatures verify that the payload is unchanged and was signed by the private key matching the public registry. Delegation tokens check subject, audience, action, expiry, and revocation.

> ⚠️ **This is not transport authentication or a sandbox**: tokens remain bearer credentials and can be replayed while still valid. The host must bind the token to the caller's connection/process, restrict audience/actions, implement anti-replay, keep system time correct, and protect the registry and private keys. Changing the project path yields a different private-key namespace; provisioning keys for other hosts must go through a secure channel.

### 🗄️ SQLite coordination backend

JSON board + JSONL remains the default so existing projects do not change. Migration only happens with an explicit action:

```bash
python3 .pakem/pakem.py team storage info
python3 .pakem/pakem.py team storage migrate --to sqlite
python3 .pakem/pakem.py team storage info --json
python3 .pakem/pakem.py team storage backup --output backups/pakem-team.sqlite3
```

SQLite stores the board and event ledger; every mutation updates both in one transaction. The original `board.json` and `events.jsonl` files are kept as backups and are no longer updated once SQLite becomes authoritative. Online backup uses the SQLite backup API to produce a consistent snapshot.

**Backend limits:** this SQLite database remains local to the project directory and depends on correct SQLite/filesystem locking. Do not rely on it as a distributed database or put the database WAL on a network filesystem that does not guarantee locking. Multi-host coordination needs a separate authenticated backend service, which this release does not provide.

### 📋 Conformance profile

`conformance/v1/README.md` defines implementation obligations and the limits of conformance claims. Executable tests live in `tests/test_release_110.py`. Passing tests does not prove transport authentication, process isolation, distributed consensus, or the correctness of agent work.

<img src="assets/divider.svg" alt="" width="100%">

## 👥 Multi-Agent Coordination (v0.9.0+)

Pakem can manage a shared task board for cooperative agents: role/capability registration, dependency-aware tasks, assignment, exclusive expiring leases, heartbeat, release, handover, submission with evidence references, and independent review. State lives in `.pakem/team/`; a lock file serializes cross-process operations on the local filesystem.

```bash
pakem team init
pakem team register lead --role lead
pakem team register backend --role worker --capability python --capability api
pakem team register reviewer --role reviewer
pakem team add T1 --title "Implement API" --files src/api.py tests/test_api.py --risk medium --capability python
pakem team assign T1 --agent backend --by lead
pakem team claim T1 --agent backend
pakem team heartbeat T1 --agent backend
pakem team submit T1 --agent backend --summary "API implemented and tested" --evidence tests/test_api.py --evidence commit:abc123
pakem team review T1 --reviewer reviewer --decision approve
pakem team status --json

# optional: bind the action to an Ed25519 identity and prove the board was not altered
pakem team submit T1 --agent backend --summary "API implemented" --evidence tests/test_api.py --sign
pakem team review T1 --reviewer reviewer --decision approve --sign
pakem team verify --json
```

A task stays in `review` until a different reviewer approves it. Dependencies become claimable only after their parent tasks are `done`. Expired claims can be reclaimed. Agent IDs/roles are cooperative metadata, not authentication; a trusted host must bind authenticated caller identity to `--agent`.

With an Ed25519 identity installed, `team register` binds its fingerprint to the board, `--sign` seals each submission and review payload, and `pakem team verify` checks the signature, the revocation state, and whether the board still matches what was signed: tamper-evident, not transport authentication. Pakem does not spawn agents, run commands, sandbox file scopes, merge branches, or provide distributed consensus. The coordination event ledger is an audit receipt, not proof that evidence was independently verified. See `.pakem/coordination/v1/README.md` for lifecycle and trust boundaries.

<img src="assets/divider.svg" alt="" width="100%">

## 🌙 Honest limitations

> *Even the strongest protagonist has limits. Better to know them early.* (´･ω･`)

- Not a replacement for tests: gates force tests to run, they do not guarantee the tests are good.
- Not a sandbox: agents can still ignore instructions. Hooks and exit codes narrow the gap, they do not close it.
- Not semantic/vector memory: these are structured files that can be read and diffed.
- Multi-agent coordination is local: Pakem provides a shared board, leases, handover, and independent review, but does not spawn agents, run commands, merge branches, or provide distributed consensus. Working-directory isolation is available via `pakem worktree` (local git worktrees); merge/push remain the operator's responsibility.
- Pakem Protocol v1.0 provides a JSON/JSONL contract, CLI validators, and a local MCP stdio adapter (read-only by default); remote transport and cross-language SDKs are not provided.
- The event ledger is append-only along the CLI path, but it is not immutable storage: a user with filesystem access can still edit it.
- The drift gate only checks backticked paths; it is not code analysis. The dependency graph/impact adds static import analysis, but does not cover every runtime relationship.
- `audit` judges artifact presence and risk flags, not the quality of their contents. Env/CI/lockfile detection is file-pattern based, not deep analysis.
- `verifyEvidence` proves the command ran and its exit/hash, not that the tests are sufficient or correct.
- Cross-process locking depends on `flock`/`msvcrt`; behavior on NFS, read-only containers, and Windows is untested.
- `SPEC.md` and `PLAN.md` are local markers: `spec --approve` / `plan done` can be changed by an agent. Pakem makes that visible and gated, not cryptographically signed.
- Pakem provides the spec container and the rule to ask questions; it is not an automatic interviewer that walks through each spec section.

<img src="assets/divider.svg" alt="" width="100%">

## 🌸 Roadmap

- [ ] Universal runtime lifecycle hooks (Stop/AfterTool according to host agent capabilities)
- [ ] Context retrieval that uses the graph, MODULE-MAP, symbol index, and prior work results
- [ ] Deeper impact analysis (AST/symbol-level, framework routing, path aliases, generated code) and automatic triggers from workflow hooks
- [ ] Verifiable/signable evidence ledger and change provenance
- [ ] Policy engine + guarded autonomy with approvals for risky operations
- [ ] MCP HTTP transport and reference SDKs for Python/TypeScript
- [ ] Authenticated agent identity, remote coordination adapters/database backends, and conflict-aware merge orchestration
- [ ] Deeper documentation drift and audits for API/DB/infra
- [ ] CI templates for GitLab/CircleCI besides GitHub Actions

<img src="assets/divider.svg" alt="" width="100%">

## 📦 License and distribution

MIT, see `LICENSE`.

The structure follows the Agent Skills/skill-creator format: `SKILL.md`, `assets/templates/`, `references/`, `scripts/`, `evals/`, and `tests/`. The contents of `evals/` are run with `python3 scripts/run_evals.py` (see `evals/README.md`). Validate and package:

```bash
python3 ~/.agents/skills/skill-creator/scripts/quick_validate.py .
python3 ~/.agents/skills/skill-creator/scripts/package_skill.py . dist
```

Packaged output: `dist/pakem.zip` (git-ignored).

<img src="assets/divider.svg" alt="" width="100%">

<div align="center">

<img src="assets/footer.svg" alt="Thank you for reading, adventurer. Agents may change; pakem stays." width="100%">

</div>