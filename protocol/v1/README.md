# Pakem Protocol v1.0 — Stable Contract

Pakem Protocol is the tool-, model-, language-, and transport-independent
contract for project workflow state and events. Version **1.0 is frozen** for
its event envelope and session compatibility rules. Future optional features
are discovered through capability negotiation; they do not silently alter the
v1 event envelope.

## Compatibility

- `protocol` is always `pakem`; `protocol_version` is `1.0`.
- Event records are append-only JSON objects, one per line (JSONL).
- Unknown session fields may be preserved. Existing sessions without
  `schemaVersion` remain valid.
- The event envelope is strict. Event-specific extensions belong inside
  `payload` until a later protocol version defines otherwise.
- One exception is reserved and additive: `integrity: {prev, hash}` (capability
  `events.integrity.v1`). It is optional on every event; readers that ignore it
  still parse the ledger, and events written before 1.2.0 remain valid. Strict
  validators must use the current `event.schema.json`. Chain verification and
  sealing are local CLI features, not a new protocol version: `prev` links to the
  previous event's `hash`, and a `ledger.sealed` event carries an Ed25519 envelope
  over the chain head at that point.
- Timestamps are ISO 8601 with an explicit UTC offset.
- `session_id` may be null for project-level events.
- Capability support is not authorization to perform side effects.

## Capability negotiation

`pakem protocol negotiate --peer-version 1.0 --capability events.v1` returns
whether the peer is compatible and the intersection of supported capabilities.
Supported capabilities include `events.v1`, `sessions.v1`,
`context.snapshot.v1`, `runtime.v1`, `intelligence.graph.v1`,
`intelligence.impact.v1`, `coordination.v1`, `coordination.review.v1`,
`git.worktree.v1`, `mcp.stdio.2026-07-28`, `identity.ed25519.v1`,
`identity.delegation.v1`, `coordination.sqlite.v1`, `events.integrity.v1`, and
`conformance.v1`. See
`capabilities.schema.json`. Unknown optional capabilities do not invalidate
an otherwise compatible protocol version; they are reported separately.

## Event envelope

See `event.schema.json`. Every event contains `protocol`, `protocol_version`,
`event_id`, `event`, `occurred_at`, `session_id`, `actor`, and `payload`.

## Session data

See `session.schema.json`. Unknown fields are preserved for forward-compatible
session metadata. Session state is not proof of task correctness.

## Trust and identity

`actor.type` and `actor.name` are attribution fields, not credentials. Agent
IDs in a local coordination board are cooperative metadata, not authenticated
identities. Pakem 1.1 can register Ed25519 public identities and verify signed
attestations/delegation tokens. A host runtime must still bind a verified token
to the actual caller, enforce audience/actions/expiry/revocation, and provide
anti-replay protection. Private keys stay outside the project; public registry
integrity must be rooted in a trusted checkout/commit. MCP `clientInfo` is
self-reported and must not be used for authorization.

## Runtime boundary

Pakem stores workflow state and provides policy decisions. Agent execution,
model selection, deployment, and external side effects belong to the host
agent/runtime and its permission system. `session.finished`, a submitted event,
or an approval receipt does not by itself prove correctness or authorize a
side effect. Verification evidence must be attached to relevant results.
