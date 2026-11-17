# Pakem Autonomous Runtime v1

A deterministic workflow state machine, checkpoint/recovery format, policy decision contract, and lifecycle-hook surface for host coding agents.

## Workflow states

`planning -> ready -> executing -> verifying -> completed`, with `blocked`, `failed`, and `recovering` branches. Only documented transitions are accepted. State changes are atomic and revisioned. Active workflows cannot be replaced by `runtime init --new`; a workflow must first enter `completed` or `failed`.

## Checkpoints and recovery

Checkpoints capture the workflow state plus a Git HEAD/working-tree snapshot. Recovery restores workflow metadata into `recovering` and reports repository drift. It NEVER resets files, checks out commits, reverts changes, reruns commands, or restores source code. A human/host agent must inspect code and repo status before resuming.

## Lifecycle hooks

Standard hooks: `session.start`, `task.before`, `task.after`, `verification.before`, `session.finish`, `handover`. `hook-payload.schema.json` describes input payload metadata and `hook-decision.schema.json` describes the machine-readable output. Hook dispatch evaluates policy and emits a compact receipt. It does not execute the requested action. Receipts hash payload/target content to avoid copying arbitrary prompts, commands, or secrets into the ledger.

## Host integration contract

The host runtime calls `pakem runtime hook <event> --payload-file ... --json` before an action, inspects `decision`, and proceeds only for `allow`. `require_approval` must pause for user confirmation via a trusted host channel, then obtain a one-use approval with `pakem policy approve ...`. `deny` must stop the action. The host must never self-approve on behalf of the agent.

The CLI is an initial reference adapter. Protocols and schemas are language-neutral; other implementations may be written in TypeScript, Rust, or another language.
