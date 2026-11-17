# Ed25519 Identity Adapter v1

Create and manage public identities:

```bash
pakem identity create backend
pakem identity list --json
pakem identity rotate backend --reason "scheduled key rotation"
pakem identity revoke backend --reason "agent retired"
```

Sign a JSON payload and verify it against the project registry:

```bash
pakem identity sign backend --file receipt.json --output receipt.signed.json
pakem identity verify receipt.signed.json
```

Issue a short-lived action-scoped delegation token:

```bash
pakem identity issue backend --audience pakem-host://worker-01 --action team.claim --action team.submit --ttl-seconds 900
pakem identity verify delegation.json --audience pakem-host://worker-01 --action team.claim
```

Private keys are not copied into `.pakem/` and are not included in ZIP release artifacts. Install `cryptography` only if Ed25519 identity operations are needed.
