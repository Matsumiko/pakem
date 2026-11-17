# Pakem Coordination v1

The local coordination board is a cooperative task-state store. It supports
roles/capabilities, dependency-aware tasks, exclusive expiring leases, handoff,
submission with evidence references, and independent review. A task reaches
`done` only after a reviewer other than its implementer approves it.

The JSON file plus OS advisory lock is intended for a single host/local
filesystem. It is **not a distributed lock or distributed database**; do not
use it as a multi-host coordination backend on an arbitrary network filesystem.

Agent IDs/roles are metadata, not authentication. A trusted host must bind the
caller identity before invoking operations. Event ledger rows are audit
receipts, not cryptographic attestations.
