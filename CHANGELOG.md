## 1.2.1 — 2026-11-17

### Added
- `npx pakem-cli` installer (npm package `pakem-cli`): copies the skill into `~/.claude/skills/pakem` (or `--project` for `./.claude/skills/pakem`, or `--dir` for another skills folder), then delegates any other argument to the bundled Python CLI (`npx pakem-cli init --type app`). The package ships `SKILL.md`, scripts, schemas, references, and assets; it adds no npm dependency to the target project. `npm pack` refuses to build when `package.json` and `scripts/pakem.py` versions differ, and `tests/test_docs.py` guards the same invariant.

### Fixed
- Gate `scope` compared only the working tree (`git diff HEAD`), so an agent that committed its work and then ran `check`/`finish` passed without ever being compared against plan scope. The gate now anchors on the HEAD recorded when the session started (`.pakem/sessions/*.json` → `git.head`) and diffs that commit against the working tree in one pass: commits made during the session, uncommitted edits, and untracked files all count. Without an active session it falls back to `git diff HEAD`, so CI on a clean checkout still needs an explicit base to mean anything.
- `reconcile`/`impact --base REF` used `REF...HEAD`, which lists commits only and hides everything uncommitted. It now runs `git diff REF` (working tree against REF) and adds untracked files, so the manual report and gate `scope` agree.
- Deleted files never appeared: `_git_changed_files` passed `--diff-filter=ACMR`, which drops `D`. A task could delete an out-of-scope module and the report said the change set was aligned. The filter is gone; a deletion is a code change like any other.
- `NEEDS_JSONSCHEMA` guarded only `jsonschema`, while `tests/test_release_110.py` also imports `referencing`. A machine with jsonschema below 4.18 errored instead of skipping. The guard checks both and the skip message names `pip install -r requirements-dev.txt`; `requirements-dev.txt` already pins `jsonschema>=4.20`, which pulls `referencing`.
- `SKILL.md` gate table and `README.md` now state the anchor for gate `scope`, so "code outside scope fails" is not read as working-tree-only.

### Changed
- Generated project documents are English: `PROJECT.md`, `CONTEXT.md`, `MODULE-MAP.md`, `DECISIONS.md`, `BUG-HISTORY.md`, `SPEC.md`, ADRs, `HANDOVER.md`, `PLAN.md`, and the protocol block installed into `CONTEXT.md` and adapters. Placeholders are now `[FILL: ...]`; gate `placeholder` still detects legacy `[ISI`, so projects initialized earlier keep failing until filled. New projects get the English templates; existing documents are not rewritten. `pakem upgrade`/`pakem adapt` rewrites the protocol block, and `doctor` reports an old block as stale until then.
- Legacy documents keep working after that switch: `pakem bug` recognizes `## Entri` and `_Belum ada bug tercatat._`, so a new entry still lands on top and the old empty marker is replaced; `pakem adr` likewise replaces `_Belum ada keputusan tercatat._` instead of leaving it above the index.
- CLI output is English. Status prefixes (`[PASS]`, `[FAIL]`, `[SKIP]`, `[WARN]`), gate names, flags, event names, schema ids, and JSON keys are unchanged, but prose and several labels moved: `[BUKTI]` → `[EVIDENCE]`, `HASIL:` → `RESULT:`, `PERIKSA` → `CHECK`, `REKONSILIASI` → `RECONCILIATION`, audit tiers `wajib`/`disarankan`/`tidak` → `required`/`recommended`/`not-needed`, `[WARN] aturan-berubah` → `[WARN] rules-changed`, `[WARN] wajib`/`risiko` → `[WARN] required`/`risk`. `audit --json` rows use the new tier values (the legacy `wajib_gap`/`disarankan_gap`/`tidak_perlu` summary keys are kept so existing readers do not break). Anything grepping the old prose must be updated; the bracketed prefixes and `pakem.*` identifiers are stable.
- Counted nouns are pluralized (`1 task`, `2 tasks`, `1 new commit`) in the plan, task-verify, report, handover, and resume output instead of printing `1 tasks`.

### Documented
- Documentation is English-first: `README.md` and `SKILL.md` are English, the Indonesian README is preserved as `README-ID.md` and linked from both, and `references/`, `adapters/`, `protocol/v1/README.md`, `evals/README.md`, and schema descriptions are English. CLI output and `evals/evals.json` are English too; the Indonesian README keeps Indonesian prose, but its command blocks and quoted output match the English CLI.
- Source docstrings and code comments are English too (63 docstrings, 27 comment lines across `scripts/pakem.py` and `pakem_core/*`). The pass changes documentation only: executable strings, identifiers, schema ids, event names, flags, and control flow are untouched. Legacy sentinels (`## Entri`, `[ISI`, `_Belum ada bug tercatat._`, `_Belum ada keputusan tercatat._`) remain where the compatibility code expects them.
- `README.md` is now a designed front page (banner, badges, arc-style table of contents, dividers, footer), and `README-ID.md` mirrors the same shell with Indonesian text. Both keep byte-identical command blocks. `tests/test_docs.py` checks that every ToC anchor resolves in both files, that heading outlines stay parallel, and that local `<img>` assets exist.
- `tests/test_docs.py` keeps the README pair honest: identical fenced blocks (a CLI change must land in both), links both ways, and a `SKILL.md` description that stays under the 57-character index budget with the trigger word intact.

### Validation
- 223 tests, all passing in one uninterrupted run with `requirements-dev.txt` installed in a clean venv (jsonschema 4.26, referencing, cryptography). Without optional dependencies the two URN-resolution tests skip instead of erroring.
- Four new regression tests in `tests/test_release_120.py`: committed out-of-scope code fails the gate, committed in-scope code passes, a deleted out-of-scope file is counted, and an untracked new file fails the gate. Before the fix, the committed case printed `[PASS] scope: tidak ada perubahan tertunda` and the deletion was absent from `changed_files`.
- Two legacy-document tests in `tests/test_pakem.py`: a pre-1.2.1 `BUG-HISTORY.md` with `## Entri` still receives a new entry on top without the stale empty marker, and a legacy `DECISIONS.md` placeholder is replaced by the ADR index entry.

## 1.2.0 — 2026-11-10

### Added
- `pakem reconcile [--base REF] [--staged] [--json] [--strict]` and `intelligence/v1/reconciliation.schema.json` (`urn:pakem:intelligence:v1:reconciliation`). The release ledger had nine features that each knew their own artifact — plan tasks declared `--files`, worktrees produced diffs, specs declared acceptance, tests produced results — and nothing compared them. `reconcile` puts Git changes, plan scope, and acceptance in one report. The comparison itself is a pure function in `pakem_core/reconcile.py`: no disk access, no subprocess, so it is testable without a repository.
- Gate `scope`. Code changed outside every plan task's `--files` fails `check` and `finish`, with the offending paths named and the remedy spelled out (`plan add ... --files ...`). Non-code files (docs, config, lockfiles) are reported in the gate line but do not fail: widening scope for a README is not the same failure as silently editing an unrelated module. Scope entries accept an exact path, a directory, or a glob.
- Gate `acceptance`, evaluated only by `finish`. `spec --approve` proves the plan; only checked boxes prove the result. It runs at `finish` and not at `check` because approval necessarily happens before the work that fills those boxes — failing a mid-work `check` on them would be noise, not a signal.
- Gate `handover` is `WARN` during `check` and `FAIL` during `finish`. A handover that lags one commit behind is normal in an active repository; making `check` red for it trains agents to ignore gates. Gates may now also return `warn`, which is reported but does not fail the run.
- `pakem handover` now stamps the document with the HEAD it was written against (`<!-- pakem:handover head=… at=… -->`). `handover --check` exits 1 when HEAD moved, and gate `handover` (check + finish) fails the same way, because a filled-in handover describing an older tree misleads whoever receives it. `handover --stamp` re-stamps after the text is updated; `handover=true` without the file also fails.
- `plan done <id>` now removes the task's worktree when it is clean and its commits are already part of HEAD, printing `[WT ] … dihapus`. Worktrees with unmerged commits or uncommitted files are left alone with `[WARN] … dibiarkan: <reason>` — unmerged work is not garbage. `worktree cleanup [task] [--dry-run]` does the same sweep on demand.
- `pakem ci` now also runs `doctor`, `audit --strict`, and `events --verify` after `check`, so CI catches a broken installation, WAJIB artifact gaps, and a rewritten ledger rather than only failing tests.
- MCP gains `pakem.session.start`, `pakem.session.step`, and `pakem.session.finish`, all behind `--allow-write` + bound `--agent-id`. They call the project's own CLI, so events are recorded, task verify runs, and a failing `finish` returns `ok: false` with the gate lines instead of raising.
- `pakem start` now pins a manifest of `pakem.py` and every `pakem_core/*.py`, not just the CLI hash. Gates live in Core too, and editing one module there used to leave no trace at all. `pakem integrity` compares the manifest with the current tree, reports changed/missing/added files, and exits 1 on drift; `--re-pin --reason "..."` is the only way to accept a change and it records an `integrity.repinned` event. `check` reports drift as `[WARN] aturan-berubah`, `finish --strict` fails on it. `doctor`, when run from the skill installation, compares the project's Core against the skill's own files.
- Private signing keys can live outside the host config: `identity create --key-out PATH`, `events --sign --key PATH` (or `PAKEM_SEAL_KEY`), and PEM PKCS8 as well as Pakem's 32 raw bytes. Verification only needs the public key, so `identity import <id> --public-key ...` registers an identity on a machine that will never hold the private half. `events --sign` warns when the key path points inside the repository, because a key stored next to the ledger proves nothing.
- `pakem report [--json] [--session ID] [--limit N]` prints a work roll-up from artifacts that already exist: sessions (wall-clock duration, steps, events, gate failures, status), every task in `PLAN.md` with its verify outcome and the files whose hashes were recorded, and ledger health with the chain head. `totals.unproven_done` counts `[x]` tasks with no valid evidence — the same ones gate `task-verify` will refuse. Exit code 1 when the ledger chain is broken, so CI can gate on it.
- Report times are session wall clock, not agent compute time. Pakem does not measure the latter and the report says so rather than estimating. Sessions still open are counted up to `generated_at`.
- `runtime/v1/work-report.schema.json` (`urn:pakem:runtime:v1:work-report`) pins the JSON shape; `--session` filters the session list only, and the text output says so instead of implying per-session tasks.
- Event ledger entries are hash-chained: every new event carries `integrity: {prev, hash}`, where `hash` covers the event body plus the previous event's hash. `pakem events --verify` recomputes the chain and reports the exact line that fails. Editing an event breaks its own hash; deleting one in the middle breaks the next event's `prev`. Events written before 1.2.0 have no chain fields and are reported as `pra-rantai` rather than as corruption — the chain simply restarts after them.
- `pakem events --sign --identity <id>` appends a `ledger.sealed` event carrying an Ed25519 envelope over `{ledger, chain_head, event_count, sealed_at}`. `events --verify` checks the signature, the identity's revocation state, and that the chain before the seal still equals the signed head — so an attacker who rewrites the whole chain and recomputes every hash is caught by the seal, not by the chain.
- Gate `ledger` (check + finish) verifies the chain and prints `head=<hash>`. That head is the anchor: record it in CI output or a ticket and `events --verify --expect-head <hash>` later proves the ledger was not rewritten. Truncating the last events is only detectable with such an anchor — a chain cannot see its own end.
- Protocol: `integrity` is a reserved, optional envelope field (capability `events.integrity.v1`) and `ledger.sealed` is a new event type. `protocol/v1/README.md` records this as the one additive exception to the otherwise strict v1 envelope; older ledgers stay valid.
- `plan done <id>` now runs the task's own `--verify` command and records the result in `.pakem/verify/tasks.json` (`runtime/v1/task-evidence.schema.json`): exit code, output hash, duration, and a digest of every file in the task's `--files` scope. A failing verify leaves the task open. Before this, a task was "done" because a box was ticked, while the `--verify` command sat in PLAN.md unused — the only proof was a global check at the end.
- Gate `task-verify`: every `[x]` task needs passing evidence, and the evidence must not be stale (any scope file changed afterwards invalidates it). `plan done` on an already-finished task re-runs verify to refresh. Waivers are allowed but explicit — `--no-verify --reason "..."` — and the gate always names them, so a shortcut is visible in the output instead of silent.
- `plan done` runs the verify command outside the session lock. `flock` is not reentrant: a verify command that itself calls pakem (e.g. `pakem check`) would otherwise wait on a lock its own parent holds, until the timeout.
- `graph` reads `paths` and `baseUrl` from `tsconfig.json`/`jsconfig.json`, following `extends` and ignoring JSONC comments and trailing commas. Before this, `import { u } from "@/lib/util"` was parsed as the scoped npm package `@/lib` and dropped: no edge, no warning, and `impact` would answer "no dependents" with confidence. Import specifiers that still fail are now listed in `unresolved_imports` with a reason (`relative`, `alias`, `baseUrl`) instead of disappearing; bare packages are not reported, so the list stays signal.
- `graph` reports `circular_dependencies` (strongly connected components, Tarjan, iterative) and `circular_dependency_count`. A cycle makes impact analysis transitive in both directions and usually means the "which module owns this" question is unresolved.
- `impact` gains `graph_health` (`alias_rules`, `unresolved_imports`, `circular_dependencies`, `complete`) and says so in its recommendations when the graph it used is incomplete; changed files inside a cycle are named in the risk reasons. The point is that "no dependents found" and "we could not resolve the imports" stop looking identical.
- `pakem worktree scope <name> [--json] [--strict]`: compares a managed worktree against the scope declared for the task in its name. The diff is taken from the merge-base with the root branch, so work already committed on `pakem/<task>/<agent>` is not invisible; untracked files are added from status. `git_worktree.resolve()` accepts `T1--solo`, `T1/solo`, or a path and refuses anything outside `.pakem/worktrees/`.
- Gate `worktree`, run by `check` and `finish`: every managed worktree still on disk is checked the same way. Isolation without this gate only hides the widening — the change shows up at merge time, when nobody attributes it to a task.
- Board tasks (`team add --files`) are now a scope source next to `PLAN.md`, merged per `taskId`. Before this, a team that tracked scope only on the board looked like it had declared no scope at all, and every changed file counted as out of scope.
- `team register` now binds the agent's Ed25519 fingerprint from `.pakem/identity/registry.json` (or an explicit `--fingerprint`), so the board records which key stands behind a name.
- `team submit --sign` and `team review --sign` seal the action payload (submission summary + evidence, review decision + note + implementer) with the agent's key and store the envelope on the board.
- `pakem team verify [--json]` checks three things per signed action: the signature verifies, the identity is not revoked, and the board content still matches the payload that was signed. Any invalid signature exits 1. Unsigned actions are counted separately rather than treated as failures.

### Changed
- Running Pakem from inside a linked worktree now uses the main worktree as the project root. `.pakem` is checked out into every worktree, so a copy of the plan/board existed there while sessions, locks, and worktree bookkeeping did not; agents working in isolation were reading stale state and `worktree scope` could not find its own worktree.
- `coordination.tasks_map()` normalises the board: `status()` returns tasks as a list while every caller needed a map keyed by `taskId`, and two new call sites hit that mismatch immediately.
- `SKILL.md` gate table, `README.md` gate list and quickstart table, and the team section now describe `scope`, `acceptance`, and signed board actions.

### Notes
- Upgrade note: tasks marked `[x]` before 1.2.0 have no evidence, so gate `task-verify` rejects them until you run `plan done <id>` once (or record a waiver). That is deliberate — the alternative is letting old ticks pass as if they had ever been verified.
- Signing makes the board tamper-evident, not authenticated: it proves a payload was not altered after sealing and that the key was not revoked at verification time. Binding a caller to `--agent` remains the host's job.
- `reconcile` is advisory on its own (`--strict` to make it exit 1); what blocks `finish` is the gate, which reads the same reconciliation.

### Validation
- 209 tests, all passing with `requirements-dev.txt`; 61 of them are the new 1.2.0 profile (`tests/test_release_120.py`): seven worktree-scope cases, five graph-resolution cases, five task-evidence cases, seven ledger-integrity cases, six work-report cases, seven handover/worktree/CI/MCP cases, three integrity-pin cases, and four external-key cases.
- `reconcile --json` output validates against its schema; tampering with a signed submission and revoking a signer are both caught by `team verify`.
- Alias resolution, `extends` chains, JSONC comments, cycle detection, missing alias targets, and external packages each have a test; `graph` and `impact` output validate against their schemas.
- Worktree scope was exercised against uncommitted edits, committed branch work, untracked files, a rename-free diff, and a task with no declared scope; the gate fails on the first three and names the missing scope on the last.

## 1.1.3 — 2026-11-09

### Added
- `runtime/v1/approval.schema.json` (`urn:pakem:runtime:v1:approval`). `approvals.json` was the only runtime artifact without a contract, and it is the one hosts read to decide whether an action may run: an unannounced field rename there could let a host treat an expired approval as valid. The schema pins the envelope, every field, the category/risk enums, and the average-case cap of 500 records. Installed by `init` and `upgrade`, checked by `doctor`.
- `scripts/run_evals.py` + `evals/README.md`. `evals/evals.json` had 24 prompts and 103 assertions and no way to execute them. The runner provisions a clean sandbox per eval, feeds the prompt to `--agent-cmd` on stdin, records exit code, transcript, and written files, then hands grading to `--judge-cmd`. Assertions are natural language, so grading needs a judge; without one the runner records but does not pretend to score. A judge that silently skips assertions scores them failed instead of passing by omission.
- `EvalRunnerTests`: 5 tests covering structure validation, record-only mode, pass/fail grading, the skip-detection rule, and surfacing a broken `--agent-cmd` instead of reporting a silent zero-file run.

### Changed
- `SKILL.md` `description` shortened from 506 to 48 characters (`Pakem: disiplin kerja agent dengan gate selesai.`). Agent skill indexes truncate around 57 characters, and the old text pushed the trigger word "pakem" out of view entirely. The removed detail now lives in a `## Kapan dipakai` section at the top of the body, where it is read when the skill actually loads.
- `worktree remove` without `--force` now raises a Pakem message ("worktree masih punya perubahan yang belum di-commit…") instead of forwarding git's raw `fatal:` line.

### Notes
- `format: date-time` is an annotation in JSON Schema 2020-12; validating timestamps requires a format checker. Plain `required`/`enum`/`const`/`pattern` violations are enforced by every validator.

### Validation
- 148 tests: 148 OK with `requirements-dev.txt`, 148 OK (15 skipped) without optional dependencies. Full suite uninterrupted, ~95s.
- `python3 scripts/run_evals.py --validate` reports a healthy 24-eval / 103-assertion file.

## 1.1.2 — 2026-11-09

### Fixed
- Schema `$id` values were split across two schemes: `urn:pakem:...` for runtime/coordination/protocol/policy/intelligence, and `https://pakem.dev/schemas/...` for identity and team storage. `pakem.dev` has no DNS record and belongs to no one, so those identifiers pointed at a domain outside the project's control. A third party registering that domain would decide what any schema-fetching validator trusts. All schema identifiers are now `urn:pakem:...` (`identity:v1:agent-identity`, `identity:v1:identity-registry`, `identity:v1:signed-payload`, `storage:v1:team-storage`).
- `identity/v1/identity-registry.schema.json` referenced `agent-identity.schema.json` relatively. That only resolved because the base was a URL; with a URN base it fails exactly like `checkpoint.schema.json` did in 1.1.1. The reference is now absolute.

### Added
- `SchemaContractTests` guard: every `*.schema.json` in the package must carry a unique `urn:pakem:` `$id`, every non-fragment `$ref` must resolve to one of those ids, and no JSON file may point at a third-party domain. This makes the mixed-scheme regression impossible instead of merely fixed.
- Offline resolution test: a real identity registry document is validated against `identity-registry` using a registry built only from `$id` values, with no network access.

### Notes
- Changing `$id` does not change instance validation, only how schemas are discovered, so this is a patch release. Projects upgrading from 1.1.1 receive the updated identity and storage schemas through `pakem upgrade`.
- Pakem keeps ship-with-the-package schemas as the source of truth. Validation needs no domain, no hosting, and no network.

## 1.1.1 — 2026-11-09

### Fixed
- `plan add --verify` dropped shell pipes. `clean_plan_field` stripped `|` from every field because it separates columns in `PLAN.md`, so `--verify "pytest -q | tail -3"` was stored as `pytest -q   tail -3` with no warning. `verify` is the last column, so it now keeps pipes; newlines are still removed and task text/files are still sanitized.
- `runtime/v1/checkpoint.schema.json` referenced `workflow.schema.json` relatively while its own `$id` is a URN. Relative references cannot resolve against a URN base, so standard validators (jsonschema, ajv) failed with `Unresolvable` on the published contract. The reference is now `urn:pakem:runtime:v1:workflow`.
- The shipped test suite could not go green. `tests/test_pakem.py` asserted `VERSION = "1.0.0"` after an upgrade to the current release (red on every release after 1.0.0), and its legacy-CLI simulation replaced `VERSION = "0.8.0"`, a no-op since 0.8.0 was retired. Both now derive from the source of truth in `scripts/pakem.py`, so a version bump no longer breaks the suite.
- `tests/test_release_110.py` imported `jsonschema` unconditionally and errored instead of skipping, while `test_pakem.py` skipped the same dependency. Both modules now guard optional dependencies and say which one is missing.
- `README.md` "Batasan jujur" still claimed worktree isolation and the MCP server were not provided, contradicting 1.0.0. Corrected.

### Changed
- `pakem audit` treats `README.md` as DISARANKAN for `type: oneoff`. `verify` that proves real output is the evidence a throwaway script needs; demanding a README contradicted "Pakem does not chase file completeness". `app`, `library`, and `research` still require it.
- Added `requirements-dev.txt` (`cryptography`, `jsonschema`) so the full suite is reproducible from the package alone.

### Documented
- `team review` requires both a registered reviewer role (`reviewer`/`lead`/`coordinator`) and a different identity from the implementer. Only the identity rule was documented, so a board of workers could submit and then never complete a task.
- The placeholder gate also scans `HANDOVER.md` and `docs/HANDOVER.md`; the gate table said only `.pakem/*.md` and `docs/adr/*.md`.
- `--verify` per plan task is a record, not an execution. Only `PROJECT.md` `verify` runs, via `check`/`finish`.

### Validation
- **139 tests** in one uninterrupted run: 139 OK with `requirements-dev.txt` installed, 139 OK (13 skipped) without optional dependencies. Runtime ~90s on Python 3.13.
- The 1.1.0 note about a "subprocess-test-harness hang in long combined batches" was a misdiagnosis: the combined suite completes in about 90 seconds. It was red because of the stale version assertion and the unguarded `jsonschema` import, both fixed here.

## 1.1.0 — 2026-11-09

### Added
- Ed25519 agent identity registry: public keys and revocation metadata are project-scoped; private keys are stored outside the repository in the user's Pakem config directory with owner-only permissions where supported.
- Canonical signed payload envelopes with digest and Ed25519 signature verification.
- Short-lived delegation tokens scoped to subject, audience, allowed actions, issue time, expiry, and token ID; verification rejects tampering, wrong audience/action, expired tokens, and revoked identities.
- Explicit Ed25519 key rotation with new key IDs and retained retired public-key metadata.
- Optional local SQLite coordination backend. Explicit migration retains the original JSON board and JSONL event ledger as backups.
- Atomic SQLite board+event writes, WAL mode, FULL synchronous mode, bounded busy timeout, and SQLite online backup command.
- Team storage status/migration/backup CLI and doctor visibility for selected backend.
- Pakem Conformance Profile v1 and release-specific regression suite.

### Compatibility and security notes
- JSON/JSONL remains the default storage backend; existing projects are not migrated automatically.
- Ed25519 operations require the optional `cryptography` package. Core CLI/runtime remains standard-library-only.
- Signed delegation tokens are bearer credentials. This release does not provide network transport authentication, process attestation, replay prevention, distributed consensus, or a multi-host coordination server.
- SQLite coordination is local and requires reliable filesystem locking/WAL semantics.
- Pakem Protocol event/session envelope v1.0 remains unchanged; new functions are advertised through capabilities.

### Validation
- **24 release-specific tests** in `tests/test_release_110.py` passed when executed individually, including cross-process identity creation and SQLite task-claim contention. The 12 release-1.0 tests also passed as a class.
- Python source compilation, JSON parsing for all 17 schema files, fresh-install/upgrade checks, and final packaged-archive smoke tests passed.
- The full legacy suite remains sensitive to a subprocess-test-harness hang in long combined batches; results are reported by targeted/isolated execution rather than claiming one uninterrupted full-suite pass.

## 1.0.0

- **Stable Operating Protocol**: Pakem Protocol v1.0 event envelope dan session compatibility rules dinyatakan frozen; feature extension dilakukan melalui capability negotiation (`protocol negotiate`) dan `capabilities.schema.json`.
- **Protocol capability negotiation**: peer version compatibility, capability intersection, dan unsupported capability reporting tersedia dari Core dan CLI.
- **MCP stateless stdio adapter**: server dependency-free untuk MCP `2026-07-28`, dengan `server/discover`, `tools/list`, dan `tools/call`; setiap request memvalidasi per-request version/capabilities metadata.
- **MCP read-only by default**: context/protocol/team/graph/impact/policy tools tersedia read-only. Team mutation tools hanya terekspos dengan `--allow-write` plus host-bound `--agent-id`; actor ID tidak bisa dioverride lewat tool arguments, dan tool exposure mengikuti role.
- **Git Worktree Isolation**: buat/list/remove worktree task/agent di `.pakem/worktrees/`, branch `pakem/<task>/<agent>`, root/path guard, dirty-removal guard, tanpa merge/push/delete-branch otomatis.
- **Doctor/upgrade/init integration**: module protocol/MCP/worktree, capability schema, dan adapter docs dipasang saat init/upgrade; doctor memeriksa instalasinya; `.pakem/worktrees/` di-ignore.
- **Trust model ditegaskan**: agent IDs, actor names, dan MCP `clientInfo` adalah metadata, bukan autentikasi. Host tetap mengikat caller, menegakkan policy, dan memediasi approval.
- **Test baru**: 12 test spesifik release 1.0.0 untuk compatibility negotiation, init/schema install, MCP discovery/metadata/stdio/role binding, dan Git worktree isolation/removal guards. Seluruh 12 test lulus.

# Changelog

## 0.9.0

- **Multi-Agent Coordination Core**: modul `pakem_core/coordination.py` menyediakan shared task board untuk registrasi agent, role/capability, assignment, dan dependency-aware task.
- **Exclusive expiring leases**: claim diserialisasi dengan cross-process file lock; lease dapat diperpanjang dengan heartbeat dan diambil alih setelah kedaluwarsa.
- **Handoff & recovery**: agent dapat release/handoff task; lead/coordinator dapat reassign task setelah lease pemilik lama kedaluwarsa; task dapat diblock/unblock.
- **Two-phase completion**: worker submit summary/evidence references ke state `review`; agent reviewer berbeda harus approve sebelum task menjadi `done`; keputusan `rework` mengembalikan task ke `open`.
- **Pakem Protocol v1.0 events**: event team memakai envelope yang sama dengan session/runtime events; coordination event schema menjadi subset event protocol v1.0.
- **Machine contracts**: tambah board, status-response, dan coordination-event JSON Schema; CLI `pakem team` menyediakan init/status/register/add/assign/claim/heartbeat/release/handoff/submit/review/block/unblock/events.
- **Integration**: `init`, `upgrade`, `doctor`, `context --json`, adapter protocol, dan `.gitignore` memahami Multi-Agent Coordination.
- **Security boundaries**: agent ID/role adalah metadata kooperatif, bukan autentikasi; Pakem tidak spawn agent, menjalankan command, sandbox file scope, merge branch, atau menyediakan distributed consensus.
- **Tests**: test terarah koordinasi mencakup lease, klaim multi-proses, dependency gate, handoff, independent review, schema, path traversal, context, doctor, dan upgrade. Beberapa kelompok test dijalankan terpisah karena test harness subprocess dapat macet bila dijalankan sebagai satu batch panjang.


## 0.8.0

- **Autonomous Runtime v1**: modul `pakem_core/runtime.py` menyediakan workflow state machine dengan transisi eksplisit, revision tracking, dan lifecycle hooks standar.
- **Checkpoint & recovery**: snapshot atomic berisi workflow + Git HEAD/working-tree state. Recovery hanya mengembalikan metadata ke `recovering`; tidak menjalankan reset/revert/checkout dan tidak mengubah source code.
- **Policy Engine**: `.pakem/POLICY.json` mendefinisikan `manual`, `assisted`, `guarded_autonomous`, max autonomous risk, approval-required categories, denied categories, dan TTL.
- **Approval one-use**: approval terikat pada workflow, kategori, risiko, dan target; memiliki expiry dan tidak dapat digunakan ulang. Host runtime tetap wajib melakukan konfirmasi user tepercaya; CLI bukan mekanisme autentikasi manusia.
- **Lifecycle hooks**: `runtime hook` untuk `session.start`, `task.before`, `task.after`, `verification.before`, `session.finish`, dan `handover`, mengembalikan `allow`, `require_approval`, atau `deny` tanpa mengeksekusi aksi.
- **CLI**: tambah `runtime init/status/transition/checkpoint/recover/hook` dan `policy show/check/approve`; `context --json`, `doctor`, `init`, dan `upgrade` memahami runtime/policy.
- **Protocol events & schemas**: perluas Protocol v1 dengan event runtime/policy; tambah workflow, checkpoint, dan policy JSON Schema.
- **Safety boundary**: state runtime di `.pakem/runtime/` diabaikan Git; hook ledger menyimpan hash payload/target, bukan payload mentah. Runtime tidak mengeksekusi command, deployment, atau agent.
- **Regression tests**: tambah 16 test untuk state transition, recovery, one-use/scope-bound approval, autonomy modes, hook decisions, context snapshot, policy validation, dan upgrade yang menjaga konfigurasi policy pengguna; total suite menjadi 89 test case. Semua test dijalankan dan lulus dalam kelompok/isolasi; full suite belum stabil dijalankan sebagai satu proses karena beberapa batch subprocess test dapat macet.


## 0.7.0

- **Pakem Intelligent Core (first modular boundary)**: `scripts/pakem_core/` memisahkan kemampuan intelligence dari entrypoint CLI; `init`/`upgrade` memasang modul Core secara mandiri di `.pakem/pakem_core/`.
- **Dependency Graph**: `pakem graph [--json] [--output PATH] [--exclude-tests]` memetakan file source dan import lokal yang terdeteksi (Python, JS/TS, Vue/Svelte, Go module lokal, Java/Kotlin).
- **Impact Analysis**: `pakem impact --files FILE...`, `--base REF`, atau `--staged` melaporkan perubahan, direct/transitive dependents, kandidat test terdampak, rekomendasi verification, dan risk signal.
- **Machine-readable contracts**: JSON Schema dan dokumentasi `pakem.dependency-graph/v1` serta `pakem.impact-analysis/v1` dipasang ke `.pakem/intelligence/v1/` dan dapat dipakai runtime selain CLI.
- **Safety boundary**: scanner read-only (kecuali `graph --output` eksplisit), tidak mengeksekusi kode/test/build/network, menolak path impact di luar root; `impact --strict` exit 1 untuk sinyal risiko HIGH.
- **Doctor/upgrade integration**: doctor memeriksa instalasi Core dan schema; upgrade menyinkronkan CLI, Core, schema protocol/intelligence, dan adapter tanpa menimpa dokumen isi proyek.
- **Batas analisis**: graph/impact statis dan heuristik; dynamic import, reflection, alias, generated code, framework routing, dan runtime wiring dapat luput. Hasil bukan bukti tidak ada dampak dan tidak menggantikan verification/review.
- **Test tambahan**: suite kini berisi 73 test case; 10 test baru mencakup dependency Python/TypeScript/Go/Java, direct/transitive impact, kandidat test, path traversal, output JSON, mode strict, dan pemulihan Core/schema melalui upgrade.

## 0.6.0

- **Pakem Protocol v1.0**: kontrak independen dari model/tool untuk event dan session, disertai JSON Schema dan catatan kompatibilitas.
- **Machine context snapshot**: `pakem context --json` merangkum project, sesi aktif, spec/plan, blockers, dan rekomendasi langkah berikutnya tanpa mengirim isi source/secret.
- **Append-only event ledger**: lifecycle sesi, task, approval spec, dan verification dicatat sebagai JSONL di `.pakem/events/`; penulisan diserialisasi oleh lock Pakem.
- **Protocol tooling**: `pakem protocol info`, `pakem protocol validate-event FILE`, `pakem protocol validate-session FILE`, dan `pakem events [--json] [--session ID]`.
- `init` dan `upgrade` memasang/menyinkronkan schema protocol dan mengabaikan direktori event lokal di `.gitignore`; `doctor` memeriksa pemasangan schema dan kesehatan ledger.
- Adapter agent diberi instruksi untuk memakai machine context dan event ledger. Session baru diberi `schemaVersion: 1`; session lama tetap dapat dibaca.
- Batasan: ledger belum immutable/ditandatangani, belum ada MCP server/SDK, dan Pakem belum mengeksekusi atau mengorkestrasi agent.
- Cakupan test menjadi 63 unit test, termasuk validasi kontrak event/session dan pencatatan lifecycle.

## 0.5.0

- **`pakem spec`**: membuat `.pakem/SPEC.md` (masalah, non-goal, acceptance, pendekatan) dengan `Status: draft`; `pakem spec --approve` menolak placeholder dan menandai approved. Gate `spec` menggagalkan `check`/`finish` selama SPEC ada tapi belum approved.
- **`pakem plan`**: mengelola `.pakem/PLAN.md` berisi task kecil (`T1`, `T2`, …) dengan `files` dan `verify`. `plan add`, `plan done T1`, `plan drop T1 --reason ...`, `plan list`. Gate `plan` menggagalkan `check`/`finish` selama masih ada task terbuka.
- **Workflow ditampilkan**: `start`/`status` menunjukkan status SPEC dan progres PLAN; `doctor` memperingatkan SPEC draft / task terbuka.
- **Deduplikasi sumber kebenaran**: protokol `CONTEXT.md` dan adapter digenerate dari satu `PROTOCOL_TEXT` (marker + `upgrade`/`doctor`); checklist keamanan hanya di `conventions.md` (reviews menunjuk ke sana); audit handover cukup satu baris; `plan done/drop` menyinkronkan `nextStep` sesi.
- `SPEC.md` dan `PLAN.md` ikut placeholder gate; `finish --strict` tetap berlaku.
- 53 unit test.

## 0.4.0

- **`finish` menyimpan bukti verify**: perintah, exit code, durasi, hash output, dan hash CLI disimpan di sesi sebagai `verifyEvidence`; dicetak sebagai `[BUKTI] verify: ...`.
- **`finish --strict`**: gagal bila aturan/verify/CLI berubah, `verify` bukan `pass`, atau ada gap audit WAJIB. Default tetap advisory dengan `[WARN] wajib:`.
- **Audit WAJIB selaras dengan `finish`**: README/lockfile/`.env.example` yang kurang sekarang terlihat di `finish`, bukan hanya di `audit`.
- **Atomic untuk semua tulisan**: `.pakem/*.md`, ADR, BUG-HISTORY, adapter, dan config memakai temp + `fsync` + rename, bukan hanya session.
- **Lock antar-proses** (`pakem_lock`) untuk `start`, `step`, `finish`, `bug`, `adr`, dan `prune`; session ID memakai microseconds agar tidak bertabrakan.
- **`pakem upgrade`**: memperbarui CLI, flag baru, `.gitignore`, dan adapter tanpa menyentuh `CONTEXT.md`/`MODULE-MAP.md`/ADR. `--dry-run` tersedia.
- **Perbaikan dari uji Codex**: audit tidak lagi mewajibkan lockfile untuk `package.json` tanpa dependency; `doctor` memperingatkan duplikasi `test/` + `tests/`.
- **Struktur skill sesuai skill-creator**: `templates/` dipindah ke `assets/templates/`, ditambah `LICENSE` (MIT), `compatibility`, dan `metadata.version` di frontmatter; lolos `quick_validate.py` dan `package_skill.py`.

## 0.3.0

- **`pakem audit`** (read-only): memilah artefak proyek menjadi WAJIB / DISARANKAN / TIDAK PERLU berdasarkan `type`, `exposure`, `deploy`, `handover`, `sensitive`, dan isi repo. `--json` untuk agent, `--strict` untuk exit 1 bila WAJIB kurang. Tidak pernah membuat file.
- **Flag risiko** di `PROJECT.md`: `exposure` (private/public), `deploy` (none/staging/production), `handover` (true/false), di samping `sensitive`. Ditampilkan `init`, dibaca `audit`.
- **Peringatan penurunan flag**: `start` memotret flag baru; `check`/`finish`/`audit` memberi `[WARN]` bila `exposure`/`deploy`/`handover`/`sensitive` diturunkan diam-diam.
- **Sesi tahan listrik padam**: `save_session` menulis atomik (temp + `fsync` + rename). File sesi yang korup dilaporkan `[WARN] sesi korup diabaikan`, tidak lagi dilewati diam-diam.
- **`references/artifacts.md`**: panduan memilih artefak per mode kegagalan (listrik padam, onboarding, insiden, rilis, repo publik, data sensitif), pilihan kanonik, dan daftar yang tidak boleh dibuat otomatis.
- **Rencana artefak saat `init`**: langsung mencetak berapa WAJIB belum ada, berapa disarankan, berapa tidak perlu.
- **`finish` memperingatkan gap berisiko**: `[WARN] risiko:` untuk `deploy`/`sensitive`/`exposure`/`handover` yang aktif tapi artefaknya belum ada. Advisory (tidak mengubah exit code), disimpan di sesi sebagai `riskWarnings`.
- **`pakem handover`**: membuat satu `HANDOVER.md` (status, akses tanpa password, kontak, sisa kerja, risiko). Placeholder-nya ikut gate sampai diisi.
- **`references/reviews.md`**: lensa review frontend (konsistensi, state, a11y) dan backend (otorisasi, validasi, secret) — bukan gate, dipakai sebelum `finish` bila relevan.
- **`pakem doctor`**: diagnosis config, placeholder, `.pakem/pakem.py`, git, hook, adapter basi, sesi korup, dan gap WAJIB; `--verify` untuk menjalankan verify, `--json` untuk agent. Exit 1 bila ada FAIL.
- **`pakem prune`**: pangkas riwayat sesi lama; dry-run default, sesi aktif dan sesi korup tidak disentuh.
- **`pakem ci`**: generate `.github/workflows/ci.yml` yang menjalankan `pakem check`; langkah setup mengikuti stack (Node npm/pnpm/yarn, Python, Go, Rust).
- **Perbaikan dari uji Codex**: audit tidak lagi mewajibkan lockfile untuk `package.json` tanpa dependency; `doctor` memperingatkan bila `test/` dan `tests/` dipakai bersamaan.
- Template `PROJECT.md` memuat flag baru; `init` menyarankan `pakem audit`.

## 0.2.1

- **`hook install` memakai folder hooks yang benar-benar dibaca git** (`git rev-parse --git-path hooks`). Sebelumnya hook crash di worktree (`.git` berupa file) dan diam-diam tidak terpakai bila `core.hooksPath` diset. Kini `core.hooksPath` dan worktree didukung, dan path hasil pemasangan dilaporkan.

## 0.2.0

- **Peringatan perubahan aturan.** `start` menyimpan potret `rule.*`, `verify`, `sensitive`, dan hash `.pakem/pakem.py`; `check`/`finish` menampilkan `[WARN]` bila ada yang dilonggarkan atau diubah. Tidak memblokir; tercatat di sesi.
- **Cek kondisi repo saat resume.** `start` dan `step` mencatat HEAD dan file yang berubah; resume melaporkan commit baru atau perubahan sejak catatan terakhir (repo git saja).
- **Perintah `bug`** dan `finish --fixed-bug` (gate bug). Entri BUG-HISTORY dibuat lewat CLI, terbaru di atas; field kosong menjadi placeholder yang ditolak gate.
- **Windows:** protokol memakai shorthand `pakem` dengan catatan interpreter; git hook mencari interpreter yang benar-benar jalan (`python3`, `python`, `py -3`); deteksi `verify` lintas OS. Belum diuji di Windows.
- Perbaikan: parser config tidak lagi memotong tanda kutip penutup di perintah `verify` (mis. `python -c "..."`).
- Template `BUG-HISTORY.md` memakai bagian `## Entri`.

## 0.1.0

- Rilis awal: `init`, `start`, `step`, `status`, `check`, `finish`, `adr`, `adapt`, `hook`; gate session/rules/placeholder/drift/verify; adapter Claude, Codex, Cursor, Gemini, Copilot.

