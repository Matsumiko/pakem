# Pakem Conformance Profile v1

An implementation claiming Pakem Protocol v1.0 conformance must:

1. Preserve the frozen v1 event envelope and session compatibility rules.
2. Negotiate versions and return only the intersection of known capabilities.
3. Treat capability support as descriptive, never as authorization.
4. Reject modified, revoked, expired, wrong-audience, and wrong-action Ed25519 delegation envelopes.
5. Keep private keys outside project source control and restrict local permissions where supported.
6. Preserve JSONL behavior unless the project explicitly migrates storage.
7. In SQLite mode, commit each board state change and matching event in one transaction.
8. Keep task completion gated by a different reviewer and retain the existing state machine invariants.
9. Never execute arbitrary shell commands, deploy, merge, or push as a side effect of protocol handling.

The executable regression profile is `tests/test_release_110.py`. Passing this profile does not certify transport authentication, OS process isolation, distributed consensus, or agent sandboxing.
