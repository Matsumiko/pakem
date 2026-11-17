# Pakem Agent Identity v1

Pakem identity v1 uses Ed25519 public-key signatures for agent attestations and scoped delegation tokens.

- Public keys and revocation metadata live in `.pakem/identity/registry.json`.
- Private keys live outside the repository under the user's Pakem config directory and are written with owner-only permissions where supported.
- Signed envelopes cover canonical JSON, the agent ID, public-key fingerprint, and payload digest.
- Delegation tokens bind a subject to an audience, a finite action list, issue time, expiry, and unique token ID. Maximum lifetime is 24 hours.
- Revocation is checked against the project's public registry at verification time.
- `identity rotate` creates a new key ID and retains the retired public key/fingerprint metadata; old signatures no longer verify as active identity. The old private-key file remains in the local config directory for operator-controlled retirement.

The optional `cryptography` Python package is required for Ed25519 operations (`python -m pip install cryptography`). The rest of Pakem continues to work without it.

**Trust boundary:** signature verification proves possession of a registered private key at signing time. It does not authenticate a network connection, prove that an agent process is uncompromised, prevent replay by itself, or bind a claim to a real OS process. A trusted host must verify tokens, enforce audience/actions/expiry/revocation, bind the token to the caller, and apply its own replay policy.
